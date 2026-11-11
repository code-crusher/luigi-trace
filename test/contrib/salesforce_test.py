# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 Simply Measured
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#
# This method will be used by the mock to replace requests.get

"""
Unit test for the Salesforce contrib package
"""

import re

import mock
import pytest
from helpers import unittest

from luigi.contrib.salesforce import QuerySalesforce, SalesforceAPI
from luigi.mock import MockTarget


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, body, status_code):
            self.body = body
            self.status_code = status_code

        @property
        def text(self):
            return self.body

        def raise_for_status(self):
            return None

    result_list = (
        '<result-list xmlns="http://www.force.com/2009/06/asyncapi/dataload"><result>1234</result><result>1235</result><result>1236</result></result-list>'
    )
    return MockResponse(result_list, 200)


class MockPostResponse:
    def __init__(self, json_body=None, text=""):
        self._json_body = json_body
        self.text = text

    def json(self):
        return self._json_body

    def raise_for_status(self):
        return None


SOAP_LOGIN_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns="urn:partner.soap.sforce.com">
  <soapenv:Body>
    <loginResponse>
      <result>
        <sessionId>soap-session-id</sessionId>
        <serverUrl>https://na1.salesforce.com/services/Soap/u/34.0/00D000000000001</serverUrl>
      </result>
    </loginResponse>
  </soapenv:Body>
</soapenv:Envelope>
"""


# Keep open around so we can use it in the mock responses
old__open = open


def mocked_open(*args, **kwargs):
    if re.match("job_data", str(args[0])):
        return MockTarget(args[0]).open(args[1])
    else:
        return old__open(*args)


@pytest.mark.contrib
class TestSalesforceAPI(unittest.TestCase):
    # We patch 'requests.get' with our own method. The mock object is passed in to our test case method.
    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_deprecated_results_warning(self, mock_get):
        sf = SalesforceAPI("xx", "xx", "xx")
        with self.assertWarnsRegex(UserWarning, r"get_batch_results is deprecated"):
            result_id = sf.get_batch_results("job_id", "batch_id")
            self.assertEqual("1234", result_id)

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_result_ids(self, mock_get):
        sf = SalesforceAPI("xx", "xx", "xx")
        result_ids = sf.get_batch_result_ids("job_id", "batch_id")
        self.assertEqual(["1234", "1235", "1236"], result_ids)

    @mock.patch("requests.post")
    def test_start_session_soap_login(self, mock_post):
        mock_post.return_value = MockPostResponse(text=SOAP_LOGIN_RESPONSE)

        sf = SalesforceAPI("user", "pass", "token")
        sf.start_session()

        self.assertEqual("soap-session-id", sf.session_id)
        self.assertEqual("na1.salesforce.com", sf.hostname)
        self.assertEqual(1, mock_post.call_count)
        self.assertEqual("https://login.salesforce.com/services/Soap/u/34.0", mock_post.call_args[0][0])

    @mock.patch("requests.post")
    def test_start_session_oauth_client_credentials(self, mock_post):
        mock_post.return_value = MockPostResponse(json_body={"access_token": "oauth-access-token", "instance_url": "https://na2.salesforce.com"})

        sf = SalesforceAPI("", "", "", client_id="client-id", client_secret="client-secret")
        sf.start_session()

        self.assertEqual("oauth-access-token", sf.session_id)
        self.assertEqual("https://na2.salesforce.com", sf.server_url)
        self.assertEqual("na2.salesforce.com", sf.hostname)

        self.assertEqual(1, mock_post.call_count)
        url = mock_post.call_args[0][0]
        self.assertEqual("https://login.salesforce.com/services/oauth2/token", url)
        self.assertEqual(
            {"grant_type": "client_credentials", "client_id": "client-id", "client_secret": "client-secret"},
            mock_post.call_args[1]["data"],
        )
        # No SOAP login should be attempted when OAuth credentials are configured.
        self.assertNotIn("Soap", url)

    @mock.patch("requests.post")
    def test_start_session_oauth_sandbox(self, mock_post):
        mock_post.return_value = MockPostResponse(json_body={"access_token": "sandbox-token", "instance_url": "https://cs1.salesforce.com"})

        sf = SalesforceAPI("", "", "", sandbox_name="uat", client_id="client-id", client_secret="client-secret")
        sf.start_session()

        self.assertEqual("sandbox-token", sf.session_id)
        self.assertEqual("https://test.salesforce.com/services/oauth2/token", mock_post.call_args[0][0])

    @mock.patch("requests.post")
    def test_start_session_oauth_token_url_override(self, mock_post):
        mock_post.return_value = MockPostResponse(json_body={"access_token": "my-domain-token", "instance_url": "https://my-domain.my.salesforce.com"})

        sf = SalesforceAPI(
            "",
            "",
            "",
            client_id="client-id",
            client_secret="client-secret",
            oauth_token_url="https://my-domain.my.salesforce.com/services/oauth2/token",
        )
        sf.start_session()

        self.assertEqual("https://my-domain.my.salesforce.com/services/oauth2/token", mock_post.call_args[0][0])

    @mock.patch("requests.post")
    def test_start_session_oauth_missing_token(self, mock_post):
        mock_post.return_value = MockPostResponse(json_body={"error": "invalid_client"})

        sf = SalesforceAPI("", "", "", client_id="client-id", client_secret="client-secret")
        with self.assertRaisesRegex(Exception, "Invalid login attempt"):
            sf.start_session()

    def test_oauth_requires_both_client_id_and_secret(self):
        self.assertFalse(SalesforceAPI("u", "p", "t", client_id="client-id").uses_oauth)
        self.assertFalse(SalesforceAPI("u", "p", "t", client_secret="client-secret").uses_oauth)
        self.assertTrue(SalesforceAPI("", "", "", client_id="client-id", client_secret="client-secret").uses_oauth)

    @mock.patch("requests.post")
    def test_oauth_access_token_is_used_for_bulk_and_rest_requests(self, mock_post):
        mock_post.return_value = MockPostResponse(json_body={"access_token": "oauth-access-token", "instance_url": "https://na2.salesforce.com"})

        sf = SalesforceAPI("", "", "", client_id="client-id", client_secret="client-secret")
        sf.start_session()

        # Bulk API 1.0 accepts an OAuth access token as the session id.
        self.assertEqual({"X-SFDC-Session": "oauth-access-token"}, sf._get_session_headers())
        self.assertEqual("Bearer oauth-access-token", sf._get_rest_headers()["Authorization"])

    @mock.patch("luigi.contrib.salesforce.SalesforceAPI")
    @mock.patch("luigi.contrib.salesforce.salesforce")
    def test_query_salesforce_passes_oauth_config(self, mock_config, mock_api):
        mock_config.return_value.username = ""
        mock_config.return_value.password = ""
        mock_config.return_value.security_token = ""
        mock_config.return_value.sb_security_token = ""
        mock_config.return_value.client_id = "client-id"
        mock_config.return_value.client_secret = "client-secret"
        mock_config.return_value.oauth_token_url = ""

        sf = mock_api.return_value
        sf.create_operation_job.return_value = "job-id"
        sf.create_batch.return_value = "batch-id"
        sf.block_on_batch.return_value = {"state": "Completed"}
        sf.get_batch_result_ids.return_value = ["result-id"]
        sf.get_batch_result.return_value = b"data"

        with mock.patch("builtins.open", mock.mock_open()):
            TestQuerySalesforce().run()

        _, kwargs = mock_api.call_args
        self.assertEqual("client-id", kwargs["client_id"])
        self.assertEqual("client-secret", kwargs["client_secret"])


class TestQuerySalesforce(QuerySalesforce):
    def output(self):
        return MockTarget("job_data.csv")

    @property
    def object_name(self):
        return "dual"

    @property
    def soql(self):
        return "SELECT * FROM %s" % self.object_name


@pytest.mark.contrib
class TestSalesforceQuery(unittest.TestCase):
    @mock.patch("builtins.open", side_effect=mocked_open)
    def setUp(self, mock_open):
        MockTarget.fs.clear()
        self.result_ids = ["a", "b", "c"]

        counter = 1
        self.all_lines = "Lines\n"
        self.header = "Lines"
        for i, id in enumerate(self.result_ids):
            filename = "%s.%d" % ("job_data.csv", i)
            with MockTarget(filename).open("w") as f:
                line = "%d line\n%d line" % ((counter), (counter + 1))
                f.write(self.header + "\n" + line + "\n")
                self.all_lines += line + "\n"
                counter += 2

    @mock.patch("builtins.open", side_effect=mocked_open)
    def test_multi_csv_download(self, mock_open):
        qsf = TestQuerySalesforce()

        qsf.merge_batch_results(self.result_ids)
        self.assertEqual(MockTarget(qsf.output().path).open("r").read(), self.all_lines)

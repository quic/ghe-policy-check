# Copyright (c) 2021, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=no-self-use,unused-argument, too-many-public-methods
from unittest import TestCase
from unittest.mock import Mock, call, patch

from requests import HTTPError
from requests.status_codes import codes

from ghe_policy_check.common.github_api import github_instance
from ghe_policy_check.common.github_api.github_instance import (
    GithubAccountSuspendedException,
    GithubBadCredentialsException,
    GithubClientException,
    GitHubInstance,
    GithubNotFoundException,
    GithubRepositoryBlockedException,
    InvalidImpersonationError,
    RateLimitException,
)


class GitHubInstanceTestCase(TestCase):
    def setUp(self):
        self.get_items = [Mock(), Mock()]
        ret_val = Mock(name="ret val", json=lambda: self.get_items)
        mock_get = Mock(name="mock get", return_value=ret_val)
        mock_post = Mock(name="mock post", return_val=Mock())
        mock_put = Mock(name="mock put", return_val=Mock())
        mock_delete = Mock(name="mock delete", return_val=Mock())

        self.github = github_instance.GitHubInstance(["token"], "fakeurl.com")
        self.github.get = mock_get
        self.github.put = mock_put
        self.github.post = mock_post
        self.github.delete = mock_delete

    def test_no_github_tokens(self):
        with self.assertRaises(ValueError):
            github_instance.GitHubInstance([], "fakeurl.com")

    def test_get_next_url_no_link_header(self):
        mock_request = Mock(headers={})
        self.assertIsNone(github_instance.GitHubInstance.get_next_url(mock_request))

    def test_get_next_url_link_header_with_next(self):
        link_header = (
            '<https://github-test.com/api/v3/organizations?since=13>; rel="next", '
            "<https://github-test.com/api/v3/organizations"
            '{?since}>; rel="first"'
        )
        mock_request = Mock(headers={"Link": link_header})
        self.assertEqual(
            github_instance.GitHubInstance.get_next_url(mock_request),
            "https://github-test.com/api/v3/organizations?since=13",
        )

    def test_get_next_url_link_header_without_next(self):
        link_header = '<https://github-test.com/api/v3/organizations{?since}>; rel="first"'
        mock_request = Mock(headers={"Link": link_header})
        self.assertIsNone(github_instance.GitHubInstance.get_next_url(mock_request))

    @patch("ghe_policy_check.common.github_api.github_instance.sleep")
    def test_handle_rate_limit_exception_rotate_token(self, m_sleep):
        github = GitHubInstance(["token1", "token2"], "fakeurl.com")

        ret_val = Mock()
        github.request = Mock(return_value=ret_val)
        github.rotate_token = Mock()
        mock_http_verb = Mock(return_val=Mock())
        fake_url = "test.url.com2"
        self.assertEqual(github._handle_rate_limit_exception(mock_http_verb, fake_url, 0), ret_val)

        m_sleep.assert_not_called()
        github.request.assert_called_once_with(mock_http_verb, fake_url, 1)
        github.rotate_token.assert_called_once()

    @patch("ghe_policy_check.common.github_api.github_instance.sleep")
    def test_handle_rate_limit_exception_sleep(self, m_sleep):
        github = GitHubInstance(["token1", "token2"], "fakeurl.com")

        ret_val = Mock()
        github.request = Mock(return_value=ret_val)

        m_get_rate_limit_reset = Mock(return_value=0)
        github.get_rate_limit_reset = m_get_rate_limit_reset

        mock_http_verb = Mock()
        fake_url = "test.url.com"

        self.assertEqual(github._handle_rate_limit_exception(mock_http_verb, fake_url, 1), ret_val)

        m_sleep.assert_called_once()
        github.request.assert_called_once_with(mock_http_verb, fake_url, 2)

    @patch("ghe_policy_check.common.github_api.github_instance.sleep")
    def test_handle_rate_limit_exception_retry_exceeded(self, m_sleep):
        mock_http_verb = Mock(return_val=Mock(), __name__="test")
        fake_url = "test.url.com2"
        with self.assertRaisesRegex(Exception, "Rate limit retries failed"):
            self.github._handle_rate_limit_exception(mock_http_verb, fake_url, 100)

        m_sleep.assert_not_called()

    @patch("ghe_policy_check.common.github_api.github_instance.GitHubInstance.handle_error")
    def test_request(self, m_handle_error):
        response = Mock()
        mock_http_verb = Mock(return_value=response, __name__="test")
        fake_url = "test.url.com"
        self.assertEqual(self.github.request(mock_http_verb, fake_url), response)
        m_handle_error.assert_called_once_with(response)

    @patch("ghe_policy_check.common.github_api.github_instance.GitHubInstance.handle_error")
    def test_request_rate_limit_exception(self, m_handle_error):
        response = Mock()
        mock_http_verb = Mock(return_value=response, __name__="test")
        fake_url = "test.url.com"
        m_handle_error.side_effect = RateLimitException
        self.github._handle_rate_limit_exception = Mock(return_value=Mock())
        self.assertEqual(
            self.github.request(mock_http_verb, fake_url),
            self.github._handle_rate_limit_exception.return_value,
        )
        m_handle_error.assert_called_once_with(response)
        self.github._handle_rate_limit_exception.assert_called_once_with(
            mock_http_verb, fake_url, 0
        )

    @patch("ghe_policy_check.common.github_api.github_instance.GitHubInstance.handle_error")
    def test_request_bad_credentials_exception(self, m_handle_error):
        response = Mock()
        mock_http_verb = Mock(return_value=response, __name__="test")
        fake_url = "test.url.com"
        m_handle_error.side_effect = [GithubBadCredentialsException, None]
        self.github.get_impersonation_token = Mock(return_value="token")
        self.github.impersonating = "test"
        self.assertEqual(self.github.request(mock_http_verb, fake_url), response)
        m_handle_error.assert_has_calls([call(response)] * 2)
        mock_http_verb.assert_has_calls([call(fake_url, headers=self.github.headers)] * 2)
        self.github.get_impersonation_token.assert_called_once_with(self.github.impersonating)
        self.assertEqual(self.github.tokens, ["token"])
        self.assertEqual(self.github.headers["Authorization"], "Bearer token")

    @patch("ghe_policy_check.common.github_api.github_instance.GitHubInstance.handle_error")
    def test_request_bad_credentials_exception_retry_fail(self, m_handle_error):
        response = Mock()
        mock_http_verb = Mock(return_value=response, __name__="test")
        fake_url = "test.url.com"
        m_handle_error.side_effect = GithubBadCredentialsException
        self.github.get_impersonation_token = Mock(return_value="token")
        self.github.impersonating = "test"
        with self.assertRaises(GithubBadCredentialsException):
            self.github.request(mock_http_verb, fake_url)
        m_handle_error.assert_has_calls([call(response)] * 2)
        mock_http_verb.assert_has_calls([call(fake_url, headers=self.github.headers)] * 2)
        self.github.get_impersonation_token.assert_called_once_with(self.github.impersonating)
        self.assertEqual(self.github.tokens, ["token"])
        self.assertEqual(self.github.headers["Authorization"], "Bearer token")

    @patch("ghe_policy_check.common.github_api.github_instance.GitHubInstance.handle_error")
    def test_request_bad_credentials_exception_not_impersonating(self, m_handle_error):
        response = Mock()
        mock_http_verb = Mock(return_value=response, __name__="test")
        fake_url = "test.url.com"
        m_handle_error.side_effect = GithubBadCredentialsException
        self.github.get_impersonation_token = Mock(return_value="token")
        with self.assertRaises(GithubBadCredentialsException):
            self.github.request(mock_http_verb, fake_url)
        m_handle_error.assert_called_once_with(response)
        mock_http_verb.assert_called_once_with(fake_url, headers=self.github.headers)
        self.github.get_impersonation_token.assert_not_called()

    def test_raise_error_account_suspended(self):
        error = Mock(response=Mock(json=lambda: {"message": "Sorry. Your account was suspended."}))
        with self.assertRaises(GithubAccountSuspendedException):
            GitHubInstance.raise_error(error)

    def test_raise_error_repository_access_blocked(self):
        error = Mock(response=Mock(json=lambda: {"message": "Repository access blocked"}))
        with self.assertRaises(GithubRepositoryBlockedException):
            GitHubInstance.raise_error(error)

    def test_raise_error_bad_credentials(self):
        error = Mock(response=Mock(json=lambda: {"message": "Bad credentials"}))
        with self.assertRaises(GithubBadCredentialsException):
            GitHubInstance.raise_error(error)

    def test_raise_error_rate_limit(self):
        error = Mock(response=Mock(json=lambda: {"message": "rate limit"}))
        with self.assertRaises(RateLimitException):
            GitHubInstance.raise_error(error)

    def test_raise_error_client(self):
        error = Mock(response=Mock(status_code=422))
        with self.assertRaises(GithubClientException):
            GitHubInstance.raise_error(error)

    def test_get_paginated_request(self):
        fake_url = "test.url.com"
        self.github.get_next_url = Mock(return_value=None)

        resp = self.github.get_paginated_response(fake_url)
        for index, item in enumerate(resp):
            self.assertEqual(self.get_items[index], item)

    def test_get_paginated_search_request(self):
        fake_url = "test.url.com"
        self.github.get_next_url = Mock(return_value=None)
        self.github.get.return_value = Mock(json=lambda: {"items": self.get_items})
        resp = self.github.get_paginated_search_response(fake_url)
        for index, item in enumerate(resp):
            self.assertEqual(self.get_items[index], item)

    def test_rotate_tokens(self):
        tokens = ["token1", "token2"]
        github = github_instance.GitHubInstance(tokens, "fakeurl.com")
        self.assertTrue(tokens[0] in github.headers["Authorization"])
        github.rotate_token()
        self.assertTrue("token2" in github.headers["Authorization"])
        self.assertEqual(["token2", "token1"], github.tokens)

    def test_get_repository_topics(self):
        fake_owner = "fake-owner"
        fake_repo = "fake-repo"
        resp = self.github.get_repository_topics(fake_owner, fake_repo)
        for index, item in enumerate(resp):
            self.assertEqual(self.get_items[index], item)

        self.github.get.assert_called_once_with(
            self.github.base_url + f"/repos/{fake_owner}/{fake_repo}/topics"
        )

    def test_set_repository_topics(self):
        fake_owner = "fake-owner"
        fake_repo = "fake-repo"
        fake_topic = Mock()
        self.github.set_repository_topics(fake_owner, fake_repo, [fake_topic])
        self.github.put.assert_called_once_with(
            self.github.base_url + f"/repos/{fake_owner}/{fake_repo}/topics",
            json={"names": [fake_topic]},
        )

    def test_add_repository_topics(self):
        fake_owner = "fake-owner"
        fake_repo = "fake-repo"
        new_topic = Mock("new topic")
        old_topic = Mock("old_topic")
        self.github.get.return_value = Mock(json=lambda: {"names": [old_topic]})
        self.github.add_repository_topics(fake_owner, fake_repo, [new_topic])
        self.github.put.assert_called_with(
            self.github.base_url + f"/repos/{fake_owner}/{fake_repo}/topics",
            json={"names": [new_topic, old_topic]},
        )

    def test_get_repo_by_id(self):
        fake_id = Mock()
        self.github.get_repo_by_id(fake_id)
        self.github.get.assert_called_once_with(
            self.github.base_url + f"/repositories/{fake_id}",
        )

    def test_get_user(self):
        fake_user_name = Mock()
        self.github.get_user(fake_user_name)
        self.github.get.assert_called_once_with(
            self.github.base_url + f"/users/{fake_user_name}",
        )

    def test_get_users(self):
        self.github.get_paginated_response = Mock()
        self.github.get_users()
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/users",
        )

    def test_get_users_since(self):
        self.github.get_paginated_response = Mock()
        self.github.get_users(1)
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/users?since=1",
        )

    def test_get_org(self):
        fake_org_name = Mock()
        self.github.get_org(fake_org_name)
        self.github.get.assert_called_once_with(
            self.github.base_url + f"/orgs/{fake_org_name}",
        )

    def test_get_orgs(self):
        self.github.get_paginated_response = Mock()
        self.github.get_organizations()
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/organizations",
        )

    def test_get_teams(self):
        self.github.get_paginated_response = Mock()
        self.github.get_teams("team")
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/orgs/team/teams",
        )

    def test_get_team_repos(self):
        self.github.get_paginated_response = Mock()
        self.github.get_team_repos("org-id", "team-id")
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/organizations/org-id/team/team-id/repos",
        )

    def test_get_team_members(self):
        self.github.get_paginated_response = Mock()
        self.github.get_team_members("org-name", "team-slug")
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/orgs/org-name/teams/team-slug/members",
        )

    def test_get_orgs_since(self):
        self.github.get_paginated_response = Mock()
        self.github.get_organizations(1)
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/organizations?since=1",
        )

    def test_create_impersonation_token(self):
        username = "fake user"
        scopes = ["fake scope"]
        self.github.create_impersonation_token("fake user", scopes)
        self.github.post.assert_called_once_with(
            self.github.base_url + "/admin/users/{}/authorizations".format(username),
            json={"scopes": scopes},
        )

    def test_delete_impersonation_token(self):
        username = "fake user"
        self.github.delete_impersonation_token("fake user")
        self.github.delete.assert_called_once_with(
            self.github.base_url + "/admin/users/{}/authorizations".format(username),
        )

    @patch("ghe_policy_check.common.github_api.github_instance.get")
    def test_get_impersonation_token(self, m_get):
        m_token = "token"
        m_get.return_value = Mock(raise_for_status=Mock())
        self.github.create_impersonation_token = Mock(
            return_value=Mock(json=lambda: {"token": m_token})
        )

        self.assertEqual(self.github.get_impersonation_token("user"), m_token)
        m_get.assert_called_once_with(
            self.github.base_url + GitHubInstance.Endpoints.RATE_LIMIT,
            headers={"Authorization": f"Bearer {m_token}"},
        )
        self.github.create_impersonation_token.assert_called_once_with(
            "user", GitHubInstance.ALL_SCOPES
        )

    @patch("ghe_policy_check.common.github_api.github_instance.get")
    def test_get_impersonation_token_error(self, m_get):
        m_token = "token"
        m_get.return_value = Mock(
            raise_for_status=Mock(
                side_effect=HTTPError(
                    response=Mock(
                        status_code=codes.not_found,
                    )
                )
            )
        )
        self.github.create_impersonation_token = Mock(
            return_value=Mock(json=lambda: {"token": m_token})
        )

        with self.assertRaises(GithubNotFoundException):
            self.github.get_impersonation_token("user")

        m_get.assert_called_once_with(
            self.github.base_url + GitHubInstance.Endpoints.RATE_LIMIT,
            headers={"Authorization": f"Bearer {m_token}"},
        )
        self.github.create_impersonation_token.assert_called_once_with(
            "user", GitHubInstance.ALL_SCOPES
        )

    def test_get_impersonation_token_suspended_user(self):

        self.github.impersonating = "user"

        with self.assertRaises(InvalidImpersonationError):
            self.github.get_impersonation_token("user")

    def test_impersonate_user(self):
        self.github.get_impersonation_token = Mock(return_value="fake token")
        username = "fake user"

        with self.github.impersonate_user(username) as impersonated_gh:
            self.github.get_impersonation_token.assert_called_once_with(username)
            self.assertIsInstance(impersonated_gh, GitHubInstance)
            self.assertEqual(impersonated_gh.tokens, ["fake token"])
            self.assertEqual(impersonated_gh.impersonating, username)

    def test_impersonate_user_suspened_error(self):
        self.github.get_impersonation_token = Mock(
            side_effect=[GithubAccountSuspendedException, "fake token"]
        )
        username = "fake user"

        with self.github.impersonate_user(username) as impersonated_gh:
            self.github.get_impersonation_token.assert_has_calls(2 * [call(username)])
            self.assertIsInstance(impersonated_gh, GitHubInstance)
            self.assertEqual(impersonated_gh.tokens, ["fake token"])
            self.assertEqual(impersonated_gh.impersonating, username)

    def test_raise_github_exception_repo_blocked(self):
        mock_response = Mock(
            raise_for_status=Mock(side_effect=HTTPError),
            json=lambda: {"message": "Repository access blocked"},
        )

        mock_exception = Mock(response=mock_response)
        with self.assertRaises(GithubRepositoryBlockedException):
            self.github.raise_error(mock_exception)

    def test_raise_github_exception_suspended(self):
        mock_response = Mock(
            raise_for_status=Mock(side_effect=HTTPError),
            json=lambda: {"message": "Sorry. Your account was suspended."},
        )

        mock_exception = Mock(response=mock_response)
        with self.assertRaises(GithubAccountSuspendedException):
            self.github.raise_error(mock_exception)

    def test_raise_github_exception_client(self):
        mock_response = Mock(
            json=lambda: {"message": "doesn't matter"},
            status_code=422,
        )
        mock_exception = Mock(response=mock_response)
        with self.assertRaises(GithubClientException):
            self.github.raise_error(mock_exception)

    def test_raise_exception_no_matching_exception(self):
        mock_exception = HTTPError
        mock_response = Mock(
            json=lambda: {"message": "doesn't matter"},
            status_code=500,
        )
        with self.assertRaises(mock_exception):
            self.github.raise_error(mock_exception(response=mock_response))

    def test_set_organization_memberships(self):
        fake_org_name = Mock()
        fake_username = Mock()
        self.github.set_organization_membership(fake_org_name, fake_username)
        self.github.put.assert_called_once_with(
            self.github.base_url + f"/orgs/{fake_org_name}/memberships/{fake_username}",
            json={"role": "admin"},
        )

    def test_get_authenticated_user_repos(self):
        self.github.get_paginated_response = Mock(return_value=[])
        self.github.get_authenticated_user_repos()
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/user/repos"
        )

    def test_suspend_user(self):
        self.github.put = Mock(return_value=[])
        self.github.suspend_user("test_user", "test_reason")
        self.github.put.assert_called_once_with(
            self.github.base_url + "/users/test_user/suspended", json={"reason": "test_reason"}
        )

    def test_unsuspend_user(self):
        self.github.delete = Mock(return_value=[])
        self.github.unsuspend_user("test_user", "test_reason")
        self.github.delete.assert_called_once_with(
            self.github.base_url + "/users/test_user/suspended", json={"reason": "test_reason"}
        )

    def test_get_org_members(self):
        self.github.get_paginated_response = Mock(return_value=[])
        self.github.get_org_members("dummy_org")
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/orgs/dummy_org/members"
        )

    def test_get_org_admins(self):
        self.github.get_paginated_response = Mock(return_value=[])
        self.github.get_org_admins("dummy_org")
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/orgs/dummy_org/members?role=admin"
        )

    def test_get_repo_collaborators(self):
        self.github.get_paginated_response = Mock(return_value=[])
        self.github.get_org_admins("dummy_org")
        self.github.get_paginated_response.assert_called_once_with(
            self.github.base_url + "/orgs/dummy_org/members?role=admin"
        )

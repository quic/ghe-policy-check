# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=too-many-public-methods
# Bug in pylint https://github.com/PyCQA/pylint/issues/3882
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from time import sleep, time
from typing import Any, Dict, Generator, List, Optional

from django.conf import settings
from requests import HTTPError, Response, delete, get, post, put
from requests.status_codes import codes
from requests.utils import parse_header_links

from ghe_policy_check.common.github_api.types import (
    GitHubObject,
    GitHubOrg,
    GitHubRepo,
    GitHubTeam,
    GitHubUser,
)

logger = logging.getLogger(__name__)


class GithubException(Exception):
    pass


class RateLimitException(GithubException):
    pass


class GithubBadCredentialsException(GithubException):
    pass


class GithubClientException(GithubException):
    pass


class GithubRepositoryBlockedException(GithubException):
    pass


class GithubAccountSuspendedException(GithubException):
    pass


class GithubNotFoundException(GithubException):
    pass


class InvalidImpersonationError(Exception):
    pass


class GitHubInstance:
    ALL_SCOPES = ["repo", "admin:org", "user", "site_admin"]

    class Endpoints:  # pylint: disable=too-few-public-methods
        AUTHENTICATED_USER_REPOS = "/user/repos"
        IMPERSONATE = "/admin/users/{}/authorizations"
        LICENSE_INFO = "/enterprise/settings/license"
        ORGANIZATIONS = "/organizations"
        ORGANIZATIONS_BY_NAME = "/orgs/{}"
        ORGANIZATION_MEMBERS = "/orgs/{}/members"
        ORGANIZATION_REPOS = "/orgs/{}/repos"
        RATE_LIMIT = "/rate_limit"
        REPO = "/repos/{}/{}"
        REPO_BY_ID = "/repositories/{}"
        REPO_COLLABORATORS = "/repos/{}/{}/collaborators"
        REPO_FORKS = "/repos/{}/{}/forks"
        REPO_TOPICS = "/repos/{}/{}/topics"
        SEARCH_REPOS = "/search/repositories"
        SET_ORGANIZATION_MEMBERSHIP = "/orgs/{}/memberships/{}"
        SUSPEND_USER = "/users/{}/suspended"
        TEAMS = "/orgs/{}/teams"
        TEAM_MEMBERS = "/orgs/{}/teams/{}/members"
        TEAM_REPOS = "/organizations/{}/team/{}/repos"
        USERS = "/users"
        USER_BY_NAME = "/users/{}"
        USER_REPOS = "/users/{}/repos"

    @staticmethod
    def get_next_url(response: Response) -> Optional[str]:
        """
        Gets the next url from the Link headers. Used in retreiving paginated data

        :param response: The response to get the next page url for
        :return: The next url if it found
        """
        headers = response.headers
        if "Link" not in headers:
            return None

        parsed_link_headers: List[Dict[str, str]] = parse_header_links(
            headers["Link"]
        )  # type: ignore
        for link_header in parsed_link_headers:
            if link_header["rel"] == "next":
                return link_header["url"]
        return None

    def __init__(
        self,
        tokens: List[str],
        url: str = settings.GITHUB_API_URL,
        headers: Optional[Dict[str, str]] = None,
        impersonating: Optional[str] = None,
    ):
        """
        Creates a GitHub instance, setting default preview headers if no
        other headers are provided
        :param tokens: The API tokens that will be used to access the GitHub API
        :param url: The base url of the GitHub instance, including the api and
        version portion of the url
        :param headers: Optional headers to specify for every request
        :param impersonating: An optional user to indicate the user
        that this instance is impersonating
        """
        if not tokens:
            raise ValueError("At least one github token must be provided")
        self.base_url = url
        self.headers = (
            headers
            if headers
            else {
                "Accept": "application/vnd.github.nebula-preview+json,"
                "application/vnd.github.mercy-preview+json"
            }
        )
        self.tokens = tokens
        self.headers["Authorization"] = f"Bearer {self.tokens[0]}"
        self.impersonating = impersonating

    def rotate_token(self) -> None:
        """
        Rotates to the next provided token in the case that the active token
        has hit its rate limit
        """
        logger.info("Rotating Github API Token")
        old_token = self.tokens.pop(0)
        self.tokens.append(old_token)
        self.headers["Authorization"] = f"Bearer {self.tokens[0]}"

    def get_rate_limit_reset(self) -> int:
        """
        Get the time at which the rate limit for the current token will reset

        :return: The epoch time at which the rate limit will reset
        """
        response = self.get(self.base_url + GitHubInstance.Endpoints.RATE_LIMIT)
        reset_time: int = response.json()["resources"]["core"]["reset"]
        return reset_time

    def _handle_rate_limit_exception(self, verb: Any, url: str, retry: int) -> Response:
        # len - 1 to prevent rotating to token that just expired
        if retry < len(self.tokens) - 1:
            self.rotate_token()
            return self.request(verb, url, retry + 1)

        if retry > 2 * len(self.tokens):
            raise Exception("Rate limit retries failed")
        reset_time = self.get_rate_limit_reset()
        retry_time = datetime.fromtimestamp(reset_time, timezone.utc)
        logger.info("Rate limit reached, retrying at %s", retry_time)

        try:
            sleep((reset_time - time() + 5))
        except ValueError:
            pass
        else:
            logger.warning("All Github tokens rate limited")
        return self.request(verb, url, retry + 1)

    def request(self, verb: Any, url: str, retry: int = 0, **kwargs: Any) -> Response:
        """
        Make a HTTP request with the given HTTP verb, raising any non 2XX
        status codes as errors. Handles :class:`RateLimitException` by waiting
        on retrying the request and :class:`BadCredentialsExceptions` by
        regenerating an impersonation token

        :param verb: The HTTP verb that will be requested
        :param url:  The url to make the request to
        :param retry: A retry count to prevent infinite retry loops
        :param kwargs: kwargs to be passed to the HTTP Request
        :return: :class:`Response` from the given HTTP Request
        """
        logger.debug("Request type %s to url %s. Retry count: %s", verb.__name__, url, retry)
        response: Response = verb(url, headers=self.headers, **kwargs)
        try:
            GitHubInstance.handle_error(response)
        except RateLimitException:
            return self._handle_rate_limit_exception(verb, url, retry)
        except GithubBadCredentialsException:
            if not self.impersonating or retry:
                raise
            # Attempt to fix bad credentials with new user token
            token = self.get_impersonation_token(self.impersonating)
            self.tokens = [token]
            self.headers["Authorization"] = f"Bearer {self.tokens[0]}"
            return self.request(verb, url, 1)

        return response

    @staticmethod
    def raise_error(error: HTTPError) -> None:
        """
        Raise a specific error if the status code or error message is
        recognized, otherwise reraises the error

        :param error: Error response from a GitHub API call
        """
        response = error.response
        message = response.json().get("message")

        if response.status_code == codes.unprocessable_entity:
            raise GithubClientException(message)
        if response.status_code == codes.not_found:
            raise GithubNotFoundException(message)
        if message == "Sorry. Your account was suspended.":
            raise GithubAccountSuspendedException(message)
        if message == "Repository access blocked":
            raise GithubRepositoryBlockedException(message)
        if message == "Bad credentials":
            raise GithubBadCredentialsException(message)
        if "rate limit" in message:
            raise RateLimitException(message)

        raise error

    @staticmethod
    def handle_error(response: Response) -> None:
        """
        Raises an error for non 2XX status codes, providing more specific
        error classes for known error messages and error codes from GitHub

        :param response: The response to check error messages on
        """
        try:
            response.raise_for_status()
        except HTTPError as e:
            GitHubInstance.raise_error(e)

    def delete(self, url: str, **kwargs: Any) -> Response:
        """
        Utility wrapper for a DELETE call utilizing the underlying :func:`request`

        :param url: The url to make the DELETE call at
        :return: A response object from the DELETE call
        """
        return self.request(delete, url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> Response:
        """
        Utility wrapper for a PUT call utilizing the underlying :func:`request`

        :param url: The url to make the PUT call at
        :return: A response object from the PUT call
        """
        return self.request(put, url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        """
        Utility wrapper for a POST call utilizing the underlying :func:`request`

        :param url: The url to make the POST call at
        :return: A response object from the POST call
        """
        return self.request(post, url, **kwargs)

    def get(self, url: str) -> Response:
        """
        Utility wrapper for a GET call utilizing the underlying :func:`request`

        :param url: The url to make the GET call at
        :return: A response object from the GET call
        """
        return self.request(get, url)

    def get_paginated_response(self, url: str) -> Generator[GitHubObject, None, None]:
        """
        Gets all the results for a REST query that has it results paginated
        across one or more pages

        :param url: The url to get the paginated results from
        :return: A generator that will generate responses as it is called
        """
        next_url: Optional[str] = url + "&per_page=100" if "?" in url else url + "?per_page=100"
        while next_url:
            response = self.get(next_url)
            try:
                response.raise_for_status()
            except HTTPError as e:
                logger.exception(e)

            for item in response.json():
                yield item
            next_url = self.get_next_url(response)

    def get_paginated_search_response(self, url: str) -> Generator[Dict[str, Any], None, None]:
        """
        Gets all the results for a search query that has it results paginated
        across one or more pages

        :param url: The url to get the paginated results from
        :return: A generator that will generate responses as it is called
        """
        next_url: Optional[str] = url + "&per_page=100" if "?" in url else url + "?per_page=100"
        while next_url:
            response = self.get(next_url)
            try:
                response.raise_for_status()
            except HTTPError as e:
                logger.exception(e)

            for item in response.json()["items"]:
                yield item
            next_url = self.get_next_url(response)

    def get_organizations(self, since: Optional[int] = None) -> Generator[GitHubOrg, None, None]:
        url = self.base_url + GitHubInstance.Endpoints.ORGANIZATIONS
        if since:
            url += f"?since={since}"
        return self.get_paginated_response(url)  # type:  ignore

    def get_users(self, since: Optional[int] = None) -> Generator[GitHubUser, None, None]:
        url = self.base_url + GitHubInstance.Endpoints.USERS
        if since:
            url += f"?since={since}"
        return self.get_paginated_response(url)  # type:  ignore

    def get_authenticated_user_repos(self, parameters: str = "") -> List[GitHubRepo]:
        return list(
            self.get_paginated_response(  # type:  ignore
                self.base_url + GitHubInstance.Endpoints.AUTHENTICATED_USER_REPOS + parameters
            )
        )

    def get_user_public_repos(self, user: str) -> Generator[GitHubRepo, None, None]:
        return self.get_paginated_response(  # type:  ignore
            self.base_url + GitHubInstance.Endpoints.USER_REPOS.format(user)
        )

    def get_organization_repos(
        self, organization: str, paramaters: str = ""
    ) -> Generator[GitHubRepo, None, None]:
        return self.get_paginated_response(  # type:  ignore
            self.base_url
            + GitHubInstance.Endpoints.ORGANIZATION_REPOS.format(organization)
            + paramaters
        )

    def create_org_repo(self, org_name: str, data: Any) -> Response:
        return self.post(
            self.base_url + GitHubInstance.Endpoints.ORGANIZATION_REPOS.format(org_name), json=data
        )

    def get_repository_topics(self, owner: str, repo: str) -> Any:
        resp = self.get(self.base_url + GitHubInstance.Endpoints.REPO_TOPICS.format(owner, repo))
        return resp.json()

    def set_repository_topics(self, owner: str, repo: str, topics: List[str]) -> Response:
        return self.put(
            self.base_url + GitHubInstance.Endpoints.REPO_TOPICS.format(owner, repo),
            json={"names": topics},
        )

    def get_repository_forks(self, owner: str, repo: str) -> Response:
        return self.get(self.base_url + GitHubInstance.Endpoints.REPO_FORKS.format(owner, repo))

    def add_repository_topics(self, owner: str, repo: str, new_topics: List[str]) -> Any:
        """
        Adds a repository topic by getting the existing topics, adding the new
        topic, then setting the topics to the new set list of topics

        :param owner: The owner of the repository
        :param repo: The name of the repository
        :param new_topics: The topic to add to the given repository
        :return: The response from GitHub from setting the topics
        """
        topics = self.get_repository_topics(owner, repo)["names"]
        return self.set_repository_topics(owner, repo, new_topics + topics).json()

    def get_repo_by_id(self, repo_id: int) -> Response:
        return self.get(self.base_url + GitHubInstance.Endpoints.REPO_BY_ID.format(repo_id))

    def get_user(self, user_name: str) -> Response:
        return self.get(self.base_url + GitHubInstance.Endpoints.USER_BY_NAME.format(user_name))

    def get_repo(self, login: str, repo: str) -> Response:
        return self.get(self.base_url + GitHubInstance.Endpoints.REPO.format(login, repo))

    def get_repo_collaborators(self, login: str, repo: str) -> Generator[GitHubUser, None, None]:
        return self.get_paginated_response(  # type:  ignore
            self.base_url + GitHubInstance.Endpoints.REPO_COLLABORATORS.format(login, repo)
        )

    def get_org(self, org_name: str) -> Response:
        return self.get(
            self.base_url + GitHubInstance.Endpoints.ORGANIZATIONS_BY_NAME.format(org_name)
        )

    def get_org_members(self, org_name: str) -> Generator[GitHubUser, None, None]:
        return self.get_paginated_response(  # type:  ignore
            self.base_url + GitHubInstance.Endpoints.ORGANIZATION_MEMBERS.format(org_name)
        )

    def get_org_admins(self, org_name: str) -> Generator[GitHubUser, None, None]:
        return self.get_paginated_response(  # type:  ignore
            self.base_url
            + GitHubInstance.Endpoints.ORGANIZATION_MEMBERS.format(org_name)
            + "?role=admin"
        )

    def get_teams(self, org_name: str) -> Generator[GitHubTeam, None, None]:
        return self.get_paginated_response(  # type:  ignore
            self.base_url + GitHubInstance.Endpoints.TEAMS.format(org_name)
        )

    def get_team_repos(self, org_id: int, team_id: int) -> Generator[GitHubRepo, None, None]:
        return self.get_paginated_response(  # type:  ignore
            self.base_url + GitHubInstance.Endpoints.TEAM_REPOS.format(org_id, team_id)
        )

    def get_team_members(self, org_name: str, team_slug: str) -> Generator[GitHubUser, None, None]:
        return self.get_paginated_response(  # type:  ignore
            self.base_url + GitHubInstance.Endpoints.TEAM_MEMBERS.format(org_name, team_slug)
        )

    def get_license_info(self) -> Response:
        return self.get(self.base_url + self.Endpoints.LICENSE_INFO)

    def get_impersonation_token(self, username: str) -> str:
        """
        Gets a valid impersonation token for a user by making a simple API
        call to ensure that the returned token is valid, especially to catch
        users that are suspended

        :param username: The user to be impersonated
        :return: Impersonation token for the given user
        """
        if self.impersonating:
            # Can't create a new Github impersonation token with an impersonated instance
            raise InvalidImpersonationError

        response = self.create_impersonation_token(username, GitHubInstance.ALL_SCOPES).json()
        token: str = response["token"]

        # Test token and raise issues with it, especially to catch suspended users
        response = get(
            self.base_url + GitHubInstance.Endpoints.RATE_LIMIT,
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            response.raise_for_status()
        except HTTPError as e:
            GitHubInstance.raise_error(e)

        return token

    def create_impersonation_token(self, username: str, scopes: List[str]) -> Response:
        return self.post(
            self.base_url + GitHubInstance.Endpoints.IMPERSONATE.format(username),
            json={"scopes": scopes},
        )

    def delete_impersonation_token(self, username: str) -> Response:
        return self.delete(self.base_url + GitHubInstance.Endpoints.IMPERSONATE.format(username))

    @contextmanager
    def impersonate_user(self, username: str) -> Any:
        """
        Impersonates a user for the duration of the context manager.
        If the user is suspened, also temporarily unsuspend them

        :param username: The user to be impersonated
        """
        try:
            token = self.get_impersonation_token(username)
        except GithubAccountSuspendedException:
            with self.temporarily_unsuspend_user(
                username,
                "Temporary unsuspension for impersonation",
                "Resuspending after temporary suspension.",
            ):
                # yield from within the with statement to keep the user unsuspended
                token = self.get_impersonation_token(username)
                impersonated_github = GitHubInstance([token], impersonating=username)
                yield impersonated_github
        else:
            impersonated_github = GitHubInstance([token], impersonating=username)
            yield impersonated_github

    def set_organization_membership(self, org: str, username: str) -> Response:
        return self.put(
            self.base_url
            + GitHubInstance.Endpoints.SET_ORGANIZATION_MEMBERSHIP.format(org, username),
            json={"role": "admin"},
        )

    def suspend_user(self, user: str, reason: str) -> Response:
        return self.put(
            self.base_url + GitHubInstance.Endpoints.SUSPEND_USER.format(user),
            json={"reason": reason},
        )

    def unsuspend_user(self, user: str, reason: str) -> Response:
        return self.delete(
            self.base_url + GitHubInstance.Endpoints.SUSPEND_USER.format(user),
            json={"reason": reason},
        )

    @contextmanager
    def temporarily_unsuspend_user(
        self,
        user: str,
        unsuspend_reason: str,
        suspend_reason: str,
    ) -> Generator[Response, None, None]:
        """
        Temporarily suspends a user for the duration of the context manager

        :param user: GitHub username to be impersonated
        :param unsuspend_reason: The reason provided to GitHub for the unsuspension
        :param suspend_reason: The reason provided to GitHub for the suspension
        """
        response = self.unsuspend_user(user, unsuspend_reason)
        try:
            yield response
        finally:
            self.suspend_user(user, suspend_reason)

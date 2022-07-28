# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

from typing import Any, List, Optional

from celery.utils.log import get_task_logger
from django.conf import settings

from ghe_policy_check.common.github_api.types import GitHubRepo
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration  # type: ignore

TIME_FORMAT = "%Y%m%d%H%M%S%f"

logger = get_task_logger(__name__)


class GithubOwnerDoesNotExistError(Exception):
    pass


def get_email(repo: GitHubRepo) -> Any:
    """
    Gets the email for a repo by checking if its owner (Org or User) has its
    email field set. Otherwise returns None

    :param repo: The :class:`ghe_policy_check.api.models.Repo` to retreive the
        email of
    :return: The email of the repo, if it has one
    """
    github = GHEPolicyCheckConfiguration.GitHubInstance(settings.GITHUB_ADMIN_TOKENS)
    owner = repo["owner"]["login"]
    if repo["owner"]["type"] == "User":
        email = github.get_user(owner).json()["email"]
    else:
        email = github.get_org(owner).json().get("email")
    return email


def get_classification(topics: List[str]) -> Optional[str]:
    """
    Retrieves the classification of a Repo from its topics

    :param topics: The List of repo topics
    :return: The classification of the repo if it is in the topic list,
    otherwise None.
    """
    classifications = {classification[1] for classification in settings.CLASSIFICATIONS}
    for topic in topics:
        if topic in classifications:
            return topic
    return None


# Gets the first admin returned from GH that is not the GH admin
# If no such user exists returns the GH admin
def get_org_owner(org: str) -> GHEPolicyCheckConfiguration.User:
    """
    For a given GitHub Org, retrieve its owner. The owner will be the first
    admin that is encountered that is not the Global GitHub Owner Admin
    that is specified by settings.GITHUB_OWNER_USER. If there are no other
    admins of that org the the Gloval GitHub Owner Admin will be returned
    :param org: The org to get the admin of
    :return: The Owner of the provided org
    """
    github = GHEPolicyCheckConfiguration.GitHubInstance([settings.GITHUB_OWNER_TOKEN])
    owners = github.get_org_admins(org)
    for github_owner in owners:
        username = github_owner["login"]
        if username == settings.GITHUB_OWNER_USER:
            continue
        return GHEPolicyCheckConfiguration.User.from_github_user(github_owner)
    try:
        user: GHEPolicyCheckConfiguration.User = GHEPolicyCheckConfiguration.User.objects.get(
            username=settings.GITHUB_OWNER_USER
        )
    except GHEPolicyCheckConfiguration.User.DoesNotExist as e:
        raise GithubOwnerDoesNotExistError from e
    logger.info("Retrieved github org owner as admin for org '%s'", org)
    return user


def get_github_repo(local_repo: GHEPolicyCheckConfiguration.Repo) -> GitHubRepo:
    """
    Gets the :class:`ghe_policy_check.common.github_api.types.GitHubRepo` from
    the given :class:`ghe_policy_check.api.models.Repo`. This will impersonate
    the owner of the repo so that it can retrieve private repos.
    :param local_repo: The database Repo to retieve the remote repo for
    :return: The GitHub Repo
    :rtype: :class:`ghe_policy_check.common.github_api.types.GitHubRepo`
    """
    github = GHEPolicyCheckConfiguration.GitHubInstance(settings.GITHUB_ADMIN_TOKENS)
    with github.impersonate_user(local_repo.owner.username) as impersonated_gh:
        github_repo: GitHubRepo = impersonated_gh.get_repo_by_id(local_repo.github_id).json()
    return github_repo

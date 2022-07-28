# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=too-few-public-methods
import math
from datetime import datetime
from typing import Callable, Optional

from celery.utils.log import get_task_logger
from django.conf import settings
from django.db.models import F, QuerySet

from ghe_policy_check.common.github_api.github_instance import (
    GithubException,
    GithubNotFoundException,
    GithubRepositoryBlockedException,
)
from ghe_policy_check.common.github_api.types import GitHubRepo
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration  # type: ignore
from ghe_policy_check.utils import get_classification, get_github_repo, get_org_owner

logger = get_task_logger(__name__)


def _get_github_repo_and_handle_error(
    local_repo: GHEPolicyCheckConfiguration.Repo,
) -> Optional[GitHubRepo]:
    try:
        return get_github_repo(local_repo)
    except GithubRepositoryBlockedException:
        local_repo.disabled = True
        local_repo.save()
        return None


def get_and_update_repo(
    local_repo: GHEPolicyCheckConfiguration.Repo, last_polling_check: datetime
) -> Optional[GitHubRepo]:
    """
    Get a :class:`ghe_policy_check.common.github_api.types.GitHubRepo` from a
    given :class:`github_automation.api.models.Repo` and update its values
    accordingly.

    This function can be extended or overwritten to customize behavior using
    :class:`GetAndUpdateRepo`
    :param local_repo: The Repo that will be updated
    :param last_polling_check: The timestamp of when this repo is being updated
    :return:
    """
    logger.debug("Updating repo %s", local_repo)

    local_repo.last_polling_check = last_polling_check
    local_repo.save()

    try:
        github_repo = _get_github_repo_and_handle_error(local_repo)
    except GithubNotFoundException:
        # There is no other owner to try with user repos, so they are always deleted
        if not local_repo.org:
            logger.info(
                "Unable to find user repo '%s' with id '%s', deleting",
                local_repo.repo_name,
                local_repo.github_id,
            )
            local_repo.delete()
            return None

        # Org repos can have their owner updated to a current org owner
        local_repo.owner = get_org_owner(local_repo.org.org_name)
        try:
            github_repo = _get_github_repo_and_handle_error(local_repo)
        except GithubNotFoundException:
            # If the new owner can't find the repo then it has been deleted
            logger.info(
                "Unable to find org repo '%s' with id '%s', deleting",
                local_repo.repo_name,
                local_repo.github_id,
            )
            local_repo.delete()
            return None

    if not github_repo:
        return None

    cci_classification = get_classification(github_repo["topics"])

    local_repo.repo_name = github_repo["full_name"]
    local_repo.size = github_repo["size"]
    local_repo.description = github_repo["description"]
    local_repo.set_classification(cci_classification)
    local_repo.visibility = github_repo["visibility"]
    local_repo.disabled = github_repo["disabled"]
    local_repo.html_url = github_repo["html_url"]
    local_repo.save()

    return github_repo


def _update_repo_topics(
    local_repo: GHEPolicyCheckConfiguration.Repo,
    github_repo: GitHubRepo,
    github: GHEPolicyCheckConfiguration.GitHubInstance,
) -> None:
    new_topics = None
    if not local_repo.classification:
        new_topics = [settings.NOT_CLASSIFIED_TOPIC]
    elif local_repo.is_non_compliant:
        new_topics = [settings.NON_COMPLIANT_TOPIC]

    if new_topics:
        try:
            with github.impersonate_user(local_repo.owner.username) as impersonated_gh:
                impersonated_gh.add_repository_topics(
                    github_repo["owner"]["login"], github_repo["name"], new_topics
                )
        except GithubException:
            return


def remind_repo(local_repo: GHEPolicyCheckConfiguration.Repo, github_repo: GitHubRepo) -> None:
    """
    Updates the topics of the repo to remind its users to take an action.

    This function can be extended or overwritten to customize behavior using
    :class:`RemindRepo`.

    :param local_repo: The :class:`github_automation.api.models.Repo` which
        will have its topics updated
    :param github_repo: The :class:`ghe_policy_check.common.github_api.types.GitHubRepo`
        which will have its topics updated
    """
    logger.info("Reminding repo %s", local_repo)

    github = GHEPolicyCheckConfiguration.GitHubInstance(settings.GITHUB_ADMIN_TOKENS)
    _update_repo_topics(local_repo, github_repo, github)


def get_polling_repos() -> QuerySet[GHEPolicyCheckConfiguration.Repo]:
    """
    Determines what set of repos will be polled during every polling period.
    Defaults to dividing repos evenly over the number of polling periods
    in an email reminded period

    :return: The Set of repos to be updated in a single polling period
    """
    repos: QuerySet[
        GHEPolicyCheckConfiguration.Repo
    ] = GHEPolicyCheckConfiguration.Repo.objects.order_by(
        F("last_polling_check").asc(nulls_first=True)
    )

    # Divide repos evenly over the number of polling periods in an email reminded period
    # ie If an email is sent daily and the polling done hourly, break repos into 24 chunks
    repos_per_polling_period = math.ceil(
        repos.count() / (settings.REMINDER_MINUTES // settings.POLLING_PERIOD_MINUTES)
    )
    return repos[:repos_per_polling_period]


class GetPollingRepos:
    """
    A configuration class that is used to set the :func:`get_polling_repos`
    that will be used by ghe_policy_check. Defaults to the provided
    :func:`get_polling_repos`
    """

    get_polling_repos = get_polling_repos

    @classmethod
    def configure(
        cls,
        get_polling_repos: Callable[[], QuerySet[GHEPolicyCheckConfiguration.Repo]],
    ) -> None:
        """
        Sets the :func:`get_polling_repos` that will be used by the
        ghe-policy-check automation

        :param get_polling_repos: The function that will override the existing
        function
        """
        cls.get_polling_repos = get_polling_repos


class RemindRepo:
    """
    A configuration class that is used to set the :func:`remind_repo`
    that will be used by ghe_policy_check. Defaults to the provided
    :func:`remind_repo`
    """

    remind_repo = remind_repo

    @classmethod
    def configure(
        cls,
        remind_repo: Callable[[GHEPolicyCheckConfiguration.Repo, GitHubRepo], None],
    ) -> None:
        """
        Sets the :func:`remind_repo` that will be used by the
        ghe-policy-check automation

        :param remind_repo: The function that will override the existing
        function
        """
        cls.remind_repo = remind_repo  # type: ignore


class GetAndUpdateRepo:
    """
    A configuration class that is used to set the :func:`get_and_update_repo`
    that will be used by ghe_policy_check. Defaults to the provided
    :func:`get_and_update_repo`
    """

    get_and_update_repo = get_and_update_repo

    @classmethod
    def configure(
        cls,
        get_and_update_repo: Callable[
            [GHEPolicyCheckConfiguration.Repo, datetime], Optional[GitHubRepo]
        ],
    ) -> None:
        """
        Sets the :func:`get_and_update_repo` that will be used by the
        ghe-policy-check automation

        :param get_and_update_repo: The function that will override the existing
        function
        """
        cls.get_and_update_repo = get_and_update_repo  # type: ignore

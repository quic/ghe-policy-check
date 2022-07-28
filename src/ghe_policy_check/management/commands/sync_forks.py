# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# type: ignore
import datetime
import logging
from argparse import ArgumentParser
from typing import Any, Dict, List

import pytz
from django.conf import settings
from django.core.management import BaseCommand

from ghe_policy_check.common.github_api.github_instance import (
    GithubClientException,
    GithubNotFoundException,
    GithubRepositoryBlockedException,
)
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration

logger = logging.getLogger(__name__)

SUSPEND_MESSAGE = "Resuspending after temporary suspension."
UNSUSPEND_MESSAGE = "Temporary unsuspension to inventory forks."
ISO_8601_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_iso_8601(time: str) -> datetime.datetime:
    return datetime.datetime.strptime(time, ISO_8601_FORMAT).replace(tzinfo=pytz.UTC)


def _get_forks(
    local_repo: GHEPolicyCheckConfiguration.Repo, github: GHEPolicyCheckConfiguration.GitHubInstance
) -> Any:
    owner, _, repo = local_repo.repo_name.partition("/")
    try:
        with github.impersonate_user(local_repo.owner.username) as impersonated_gh:
            forks = impersonated_gh.get_repository_forks(owner, repo).json()
    except (GithubRepositoryBlockedException, GithubNotFoundException):
        return None

    return forks


def _add_forks(
    local_repo: GHEPolicyCheckConfiguration.Repo, github: GHEPolicyCheckConfiguration.GitHubInstance
) -> None:
    try:
        forks = _get_forks(local_repo, github)
    except GithubClientException:
        forks = _get_forks(local_repo, github)

    if not forks:
        return

    for github_fork in forks:
        try:
            local_fork = GHEPolicyCheckConfiguration.Repo.objects.get(
                repo_name=github_fork["full_name"]
            )
        except GHEPolicyCheckConfiguration.Repo.DoesNotExist:
            logger.exception(
                "Did not find fork '%s' of '%s' in local db",
                github_fork["full_name"],
                local_repo.repo_name,
            )
            continue
        local_fork.fork_source = local_repo
        local_fork.save()


class Command(BaseCommand):
    help = "Syncs all forks from the Github instance locally."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--created",
            nargs=1,
            type=str,
            help="Filter repos before created date (ISO-8601)",
            default=[None],
        )

    def handle(
        self, *args: List[Any], **kwargs: Dict[Any, Any]  # pylint: disable=unused-argument
    ) -> None:
        """
        Syncs the forks of all local repositories against the GitHub instance.
        """
        github = GHEPolicyCheckConfiguration.GitHubInstance(settings.GITHUB_ADMIN_TOKENS)

        created = kwargs["created"][0]
        queryset = GHEPolicyCheckConfiguration.Repo.objects.order_by("created")
        queryset = queryset.filter(created__gte=_parse_iso_8601(created)) if created else queryset

        for repo in queryset.all():
            _add_forks(repo, github)

# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

from typing import Any, Dict, List

from django.conf import settings
from django.core.management import BaseCommand

from ghe_policy_check.common.github_api.github_instance import (
    GithubNotFoundException,
    GithubRepositoryBlockedException,
)
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration  # type: ignore


class Command(BaseCommand):
    help = "Cleans all local repos by updating visibility and removing lost repos"

    def handle(
        self, *args: List[Any], **kwargs: Dict[Any, Any]  # pylint: disable=unused-argument
    ) -> None:
        """
        Updates visibility of repos and deletes local repos that no longer
        exist in the GitHub Instance
        """
        github = GHEPolicyCheckConfiguration.GitHubInstance(settings.GITHUB_ADMIN_TOKENS)
        for repo in GHEPolicyCheckConfiguration.Repo.objects.all():
            login, _, name = repo.repo_name.partition("/")
            with github.impersonate_user(repo.owner.username) as impersonated_gh:
                try:
                    resp = impersonated_gh.get_repo(login, name).json()
                except GithubRepositoryBlockedException:
                    continue
                except GithubNotFoundException:
                    # Delete repos we no longer have access to
                    if resp.get("message") == "Not Found":
                        repo.delete()
                        continue

            repo.visibility = resp["visibility"]
            repo.save()

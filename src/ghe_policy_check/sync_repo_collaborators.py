# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

from datetime import datetime
from typing import List, Optional

import pytz
from celery.utils.log import get_task_logger
from django.conf import settings
from django.utils import timezone
from ilock import ILock

from ghe_policy_check.common.github_api.github_instance import (
    GithubAccountSuspendedException,
    GithubNotFoundException,
    GithubRepositoryBlockedException,
)
from ghe_policy_check.common.github_api.types import GitHubUser
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration  # type: ignore

logger = get_task_logger(__name__)

TIME_FORMAT = "%Y%m%d%H%M%S%f"


def _get_repo_collaborators(
    local_repo: GHEPolicyCheckConfiguration.Repo, retry: int = 0
) -> Optional[List[GitHubUser]]:
    github = GHEPolicyCheckConfiguration.GitHubInstance(settings.GITHUB_ADMIN_TOKENS)
    owner, _, repo_name = local_repo.repo_name.partition("/")
    local_repo.collaborators_synced = timezone.now()
    local_repo.save()
    with github.impersonate_user(local_repo.owner.username) as impersonated_github:
        try:
            return list(impersonated_github.get_repo_collaborators(owner, repo_name))
        except GithubRepositoryBlockedException:
            logger.info("Can't get collaborators for blocked repository '%s'", local_repo.repo_name)
            return None
        except GithubAccountSuspendedException:
            # Since sync collaborators tasks typically run in groups the likelyhood
            # of one task resuspending a user that is being impersonated is increased greatly
            # Retrying the same call will allow for the impersonate_user context manager to
            # unsuspend the user again
            if retry < settings.MAX_SYNC_RETRY:
                return _get_repo_collaborators(local_repo, retry + 1)
    return None


def run_sync_repo_collaborators(github_id: int, sent: str) -> None:
    """
    Syncs the collaborators for a repo from the GitHub instance, adding a
    timestamp of when the action was performed to prevent multiple
    instances of the query from firing

    :param github_id: The id of the desired :class:`ghe_policy_check.api.models.Repo`
    :param sent: The timestamp of when the command was sent
    """
    # Github often fires many webhooks that cause a sync simultaneously
    # Only one sync is needed, so if a sync has been ran after the request to sync was sent
    # That request can safely be ignored
    with ILock(str(github_id) + "-sync-repo-lock"):
        try:
            local_repo = GHEPolicyCheckConfiguration.Repo.objects.get(github_id=github_id)
        except GHEPolicyCheckConfiguration.Repo.DoesNotExist:
            logger.error("Could not find repo with github id %s", github_id)
            return

        if local_repo.collaborators_synced and (
            datetime.strptime(sent, TIME_FORMAT).replace(tzinfo=pytz.UTC)
            < local_repo.collaborators_synced
        ):
            logger.info("Skipping collaborators sync for repo '%s'", local_repo.repo_name)
            return

        local_repo.collaborators_synced = timezone.now()
        local_repo.save()

    logger.info("Syncing collaborators for repo '%s'", local_repo.repo_name)

    try:
        collaborators = _get_repo_collaborators(local_repo)
    except GithubNotFoundException:
        # User repos have no other owner to try
        if not local_repo.org:
            raise

        # Try getting the gh org owner in case the local owner has lost permissions
        local_repo.owner = local_repo.org.owner
        local_repo.save()
        collaborators = _get_repo_collaborators(local_repo)

    if not collaborators:
        logger.info("Could not access collaborators for repo '%s'", local_repo.repo_name)
        return
    local_repo.sync_collaborators(
        GHEPolicyCheckConfiguration.User.objects.filter(
            github_id__in=[github_user["id"] for github_user in collaborators]
        )
    )

    logger.info("Finished syncing collaborators for repo '%s'", local_repo.repo_name)

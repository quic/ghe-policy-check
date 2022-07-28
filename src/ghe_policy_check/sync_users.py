# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

import math
from datetime import datetime

from celery.utils.log import get_task_logger
from django.conf import settings
from django.db.models import F, QuerySet
from django.utils import timezone

from ghe_policy_check.common.github_api.github_instance import GithubNotFoundException
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration  # type: ignore

logger = get_task_logger(__name__)


def _update_user(local_user: GHEPolicyCheckConfiguration.User, last_synced: datetime) -> None:
    logger.info("Syncing user: %s", local_user.username)
    local_user.last_synced = last_synced

    github = GHEPolicyCheckConfiguration.GitHubInstance(settings.GITHUB_ADMIN_TOKENS)
    try:
        github_user = github.get_user(local_user.username).json()
    except GithubNotFoundException:
        # Skip users that have been deleted in GH
        return
    local_user.suspended_at = github_user["suspended_at"]
    local_user.save()


def _get_polling_users() -> QuerySet[GHEPolicyCheckConfiguration.User]:
    users: QuerySet[
        GHEPolicyCheckConfiguration.User
    ] = GHEPolicyCheckConfiguration.User.objects.order_by(F("last_synced").asc(nulls_first=True))

    # Sync users in same time period as repos
    users_per_polling_period = math.ceil(
        users.count() / (settings.REMINDER_MINUTES // settings.POLLING_PERIOD_MINUTES)
    )
    return users[:users_per_polling_period]


def run_sync_users() -> None:
    """
    Syncs all users suspended field in settings.REMINDER_MINUTES by evenly
    dividing users over each settings.POLLING_PERIOD_MINUTES
    """
    # Cannot utilize /users GHE endpoint since it does not contain suspension information
    # Need to query for each user individually to get suspension information
    now = timezone.now()
    for local_user in _get_polling_users():
        _update_user(local_user, now)

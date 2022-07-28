# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

from datetime import datetime

import pytz
from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import IntegrityError
from django.utils import timezone

from ghe_policy_check.common.github_api.github_instance import GithubNotFoundException
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration  # type: ignore
from ghe_policy_check.repo_polling import GetAndUpdateRepo, GetPollingRepos, RemindRepo
from ghe_policy_check.sync_repo_collaborators import run_sync_repo_collaborators
from ghe_policy_check.sync_users import run_sync_users

logger = get_task_logger(__name__)

TIME_FORMAT = "%Y%m%d%H%M%S%f"


# Retry for integrity error in the case that the repo is deleted during this task
@shared_task(autoretry_for=(IntegrityError,), max_retries=1)
def sync_repo_collaborators_task(github_id: int, sent: str) -> None:
    """
    Runs the :func:`ghe_policy_check.sync_repo_collaborators.run_sync_repo_collaborators`
    task with the given parameters, logging 404s

    :param github_id: The github id of the repo to sync
    :param sent: the timestamp of when the task was created
    """
    try:
        run_sync_repo_collaborators(github_id, sent)
    except GithubNotFoundException:
        logger.info("Could not access repo w/ github id '%s'", github_id)


def sync_repo_collaborators(local_repo: GHEPolicyCheckConfiguration.Repo) -> None:
    """
    Wrapper method for :sync_repo_collaborator_task that will automatically
    add the current datetime

    :param local_repo: The :class:`ghe_policy_check.api.models.Repo` to
    sync the collaborators for
    """
    sync_repo_collaborators_task.delay(
        local_repo.github_id, datetime.now(tz=pytz.UTC).strftime(TIME_FORMAT)
    )


@shared_task(
    autoretry_for=(GHEPolicyCheckConfiguration.Repo.DoesNotExist, IntegrityError), retry_backoff=10
)
def delete_repository(github_id: int) -> None:
    """
    Deletes the repository with the given GitHub id. Retries in cases where
    the repo is not found to account for rapid repo creations/deletions possibly
    being received out of order

    :param github_id: The id of the repository to delete
    """
    repo = GHEPolicyCheckConfiguration.Repo.objects.get(github_id=github_id)
    repo_name = repo.repo_name
    repo.delete()
    logger.info("Successfully deleted repo '%s'", repo_name)


@shared_task(
    autoretry_for=(GHEPolicyCheckConfiguration.Team.DoesNotExist, IntegrityError), retry_backoff=10
)
def add_membership(team_github_id: int, user_github_id: int) -> None:
    """
    Add a user to a team

    :param team_github_id: The id of the team to add the member to
    :param user_github_id: The id of the user being added to the team
    """
    user = GHEPolicyCheckConfiguration.User.objects.get(github_id=user_github_id)
    team = GHEPolicyCheckConfiguration.Team.objects.get(github_id=team_github_id)

    team.members.add(user)

    # Add new user to Team's repos since the member webhook is not fired
    for repo in team.repos.all():
        repo.collaborators.add(user)
        repo.save()
    team.save()
    logger.info("Successfully added membership '%s' to team '%s'", user.username, team.team_name)


@shared_task(
    autoretry_for=(GHEPolicyCheckConfiguration.Org.DoesNotExist, IntegrityError), retry_backoff=10
)
def add_org_member(org_github_id: int, user_github_id: int) -> None:
    """
    Adds a user to an org and updates the collaborators for all repos in that
    org to reflect the change

    :param org_github_id:  The GitHub id of the Oog
    :param user_github_id: The  GitHub id of the user
    """
    org = GHEPolicyCheckConfiguration.Org.objects.get(github_id=org_github_id)
    user = GHEPolicyCheckConfiguration.User.objects.get(github_id=user_github_id)
    org.members.add(user)
    org.save()

    for repo in org.repos.all():
        sync_repo_collaborators(repo)

    logger.info("Successfully added member '%s' to org '%s'", user.username, org.org_name)


@shared_task
def sync_users() -> None:
    """
    Runs the :func:`ghe_policy_check.sync_users.run_sync_users` task
    """
    run_sync_users()


@shared_task
def repo_polling() -> None:
    """
    Gets all repos to be updated and reminded in a given session, then
    updates all repos and checks to see which repos should be reminded
    """
    now = timezone.now()
    for local_repo in GetPollingRepos.get_polling_repos():
        logger.info("Syncing repo %s", local_repo.repo_name)

        # Must call is_reminder_candidate before get_and_update_repo updates
        # the last_polling_check timestamp
        needs_reminder = local_repo.is_reminder_candidate
        github_repo = GetAndUpdateRepo.get_and_update_repo(local_repo, now)
        if not github_repo:
            logger.info("Error Updating repo %s", local_repo)
            continue
        if needs_reminder:
            RemindRepo.remind_repo(local_repo, github_repo)

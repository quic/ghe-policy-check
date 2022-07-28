# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=too-few-public-methods
import datetime
import logging
from typing import List, Optional

from django.conf import settings
from django.db import IntegrityError, models
from django.utils import timezone
from django_extensions.db.models import TimeStampedModel

from ghe_policy_check.common.github_api.types import GitHubOrg, GitHubTeam, GitHubUser

logger = logging.getLogger(__name__)


class User(TimeStampedModel):
    """
    Database representation of a GitHub User
    """

    class Meta:
        abstract = True

    username = models.CharField(max_length=255, unique=True)
    github_id = models.IntegerField(unique=True)
    email = models.EmailField(unique=True, null=True)
    suspended_at = models.DateTimeField(null=True)
    last_synced = models.DateTimeField(null=True)

    @classmethod
    def from_github_user(cls, github_user: GitHubUser) -> "User":
        """
        Create and return a User from a :class:`~ghe_policy_check.common.github_api.types.GitHubUser`

        :param github_user: The :class:`~ghe_policy_check.common.github_api.types.GitHubUser`
            to create a User from.
        :type github_user: :class:`~ghe_policy_check.common.github_api.types.GitHubUser`
        :return: A copy of the given .. py:class::GitHubUser
        :rtype: User
        """
        try:
            user: User = cls.objects.get(github_id=github_user["id"])
        except cls.DoesNotExist:
            try:
                user, _ = cls.objects.update_or_create(
                    username=github_user["login"],
                    defaults={
                        "github_id": github_user["id"],
                        "suspended_at": github_user.get("suspended_at"),
                    },
                )
            except IntegrityError:
                # Multiple webhooks might try to create the user simultaneously
                # Check if another webhook created the user and return that
                user = cls.objects.get(github_id=github_user["id"])
        return user

    def __str__(self) -> str:
        return str(self.username)


class Org(TimeStampedModel):
    """
    Database representation of a GitHub Org
    """

    class Meta:
        abstract = True

    org_name = models.CharField(max_length=255, unique=True)
    github_id = models.IntegerField(unique=True)
    owner = models.ForeignKey("BasicUser", related_name="orgs", on_delete=models.CASCADE)

    members = models.ManyToManyField("BasicUser")

    @classmethod
    def from_github_org(cls, github_org: GitHubOrg, owner: "User") -> "Org":
        """
        Create and return an Org from a :class:`~ghe_policy_check.common.github_api.types.GitHubOrg`

        :param github_org: The :class:`~ghe_policy_check.common.github_api.types.GitHubOrg`
            to create an Org from.
        :type github_org: :class:`~ghe_policy_check.common.github_api.types.GitHubOrg`
        :param owner: The owner of the created org
        :type owner: :class:`~ghe_policy_check.common.github_api.types.GitHubUser`
        :return: A copy of the given .. py:class::GitHubOrg
        :rtype: Org
        """
        try:
            org: Org = cls.objects.get(github_id=github_org["id"])
        except cls.DoesNotExist:
            try:
                org = cls.objects.create(
                    github_id=github_org["id"],
                    org_name=github_org["login"],
                    owner=owner,
                )
            except IntegrityError:
                # Multiple webhooks might try to create the org simultaneously
                # Check if another webhook created the org and return that
                org = cls.objects.get(github_id=github_org["id"])
        return org

    def __str__(self) -> str:
        return str(self.org_name)


class Team(TimeStampedModel):
    """
    Database representation of a GitHub Team
    """

    class Meta:
        abstract = True

    github_id = models.IntegerField(unique=True)
    team_name = models.CharField(max_length=255)
    team_slug = models.CharField(max_length=255)

    org = models.ForeignKey("BasicOrg", related_name="teams", on_delete=models.CASCADE)

    members = models.ManyToManyField("BasicUser")

    @classmethod
    def from_github_team(cls, github_team: GitHubTeam, org: Org) -> "Team":
        """
        Create and return a Team from a :class:`~ghe_policy_check.common.github_api.types.GitHubTeam`

        :param github_team: The :class:`~ghe_policy_check.common.github_api.types.GitHubOrg`
            to create an Org from.
        :type github_team: :class:`~ghe_policy_check.common.github_api.types.GitHubOrg`
        :param org: The org the given team is a part of
        :type org: :class:`~ghe_policy_check.common.github_api.types.GitHubOrg`
        :return: A copy of the given .. py:class::GitHubTeam
        :rtype: Team
        """
        try:
            team: "Team" = cls.objects.get(github_id=github_team["id"])
        except cls.DoesNotExist:
            team = cls.objects.create(
                github_id=github_team["id"],
                team_name=github_team["name"],
                team_slug=github_team["slug"],
                org=org,
            )
        return team

    def __str__(self) -> str:
        return str(self.team_name)


class Repo(TimeStampedModel):
    """
    Database representation of a GitHub Repo
    """

    class Meta:
        abstract = True

    repo_name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    github_id = models.IntegerField(unique=True)

    Classification: models.TextChoices = models.TextChoices(
        "Classification", settings.CLASSIFICATIONS
    )

    classification = models.TextField(
        choices=Classification.choices,
        default=None,
        null=True,
    )
    classification_modified = models.DateTimeField(default=timezone.now)

    class Visibility(models.TextChoices):
        PUBLIC = "public"
        INTERNAL = "internal"
        PRIVATE = "private"

    visibility = models.TextField(choices=Visibility.choices, default=Visibility.PRIVATE)

    html_url = models.URLField(unique=True, null=True)

    owner = models.ForeignKey("BasicUser", related_name="repos", on_delete=models.CASCADE)

    # Forks automatically disassociated on delete with SET_NULL
    fork_source = models.ForeignKey(
        "self",
        related_name="forks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    size = models.IntegerField(default=0)

    disabled = models.BooleanField(default=False)

    teams = models.ManyToManyField("BasicTeam", blank=True, related_name="repos")

    org = models.ForeignKey("BasicOrg", related_name="repos", on_delete=models.CASCADE, null=True)

    collaborators = models.ManyToManyField("BasicUser")

    collaborators_synced = models.DateTimeField(null=True)

    last_polling_check = models.DateTimeField(null=True)

    def sync_collaborators(self, local_users: List[User]) -> None:
        """
        Sets the local collaborators to match the passed list of :class:`User`

        :param local_users: The new set of collaborators to replace the old collaborators
        """
        try:
            self.collaborators.clear()
            self.collaborators.add(*local_users)
            self.save()
        except IntegrityError:
            logger.warning("Integrity error with repo '%s'", self.repo_name)

    def set_classification(self, classification: Optional[str]) -> None:
        """
        Sets the classifiction field and the timestamp of when the classification was last modified

        :param classification: The new classification of the repo
        """
        if self.classification == classification:
            return
        self.classification = classification
        self.classification_modified = timezone.now()
        self.save()

    @property
    def is_non_compliant(self) -> bool:
        """
        Placeholder function for defining a condition to determine what is non-compliant
        :return: True if non-compliant, False otherwise
        """
        return False

    @property
    def is_reminder_candidate(self) -> bool:
        """
        A function to determine if a given Repo is a candidate to have its topics
        updated in the GitHub instance
        :return: True if the repo should be updated, False otherwise
        """
        if not self.last_polling_check:
            return True
        current_time = timezone.now()
        # Give a small 30 second buffer time
        reminder_period = datetime.timedelta(
            minutes=settings.REMINDER_MINUTES
        ) - datetime.timedelta(seconds=30)
        return (self.last_polling_check + reminder_period) < current_time  # type: ignore

    def __str__(self) -> str:
        return str(self.repo_name)


class BasicOrg(Org):
    pass


class BasicUser(User):
    pass


class BasicTeam(Team):
    pass


class BasicRepo(Repo):
    pass

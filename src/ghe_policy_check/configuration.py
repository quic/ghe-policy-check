# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# type: ignore
from typing import Optional, Type

from ghe_policy_check.common.github_api.github_instance import GitHubInstance
from ghe_policy_check.models import BasicOrg, BasicRepo, BasicTeam, BasicUser, Org, Repo, Team, User
from ghe_policy_check.serializers import (
    OrgSerializer,
    RepoSerializer,
    TeamSerializer,
    UserSerializer,
)


class ConfigurationError(Exception):
    pass


class GHEPolicyCheckConfiguration:
    """
    A configuration class that allow for overridding important methods and
    models used in the library code with custom written ones. This provides
    the ability to customize the behavior of the policy checking
    """

    Repo = BasicRepo
    Org = BasicOrg
    User = BasicUser
    Team = BasicTeam
    RepoSerializer = RepoSerializer
    OrgSerializer = OrgSerializer
    UserSerializer = UserSerializer
    TeamSerializer = TeamSerializer
    GitHubInstance = GitHubInstance

    @classmethod
    def configure_models(
        cls,
        repo_class: Type[Repo],
        org_class: Type[Org],
        user_class: Type[User],
        team_class: Type[Team],
    ):
        """
        Configures the models to be used by the policy enforcement
        :param repo_class: The class used to represent GitHub Repos as Django
        models.
        :param org_class: The class used to represent GitHub Orgs as Django
        models.
        :param user_class: The class used to represent GitHub Users as Django
        models.
        :param team_class: The class used to represent GitHub Teams as Django
        models.
        """
        if not (
            issubclass(repo_class, Repo)
            and issubclass(org_class, Org)
            and issubclass(user_class, User)
            and issubclass(team_class, Team)
        ):
            raise ConfigurationError("Classes must subclass built in classes")

        if (
            repo_class.Meta.abstract
            or org_class.Meta.abstract
            or user_class.Meta.abstract
            or team_class.Meta.abstract
        ):
            raise ConfigurationError(
                "Class definitions may not be abstract. Subclass built in classes to make them concrete"
            )

        cls.Repo = repo_class
        cls.Org = org_class
        cls.User = user_class
        cls.Team = team_class
        RepoSerializer.Meta.model = repo_class
        OrgSerializer.Meta.model = org_class
        UserSerializer.Meta.model = user_class
        TeamSerializer.Meta.model = team_class

    @classmethod
    def configure_serializers(
        cls,
        repo_class: Optional[Type[RepoSerializer]] = None,
        org_class: Optional[Type[OrgSerializer]] = None,
        user_class: Optional[Type[UserSerializer]] = None,
        team_class: Optional[Type[TeamSerializer]] = None,
    ):
        """
        Configures the serializers to be used by the policy enforcement
        :param repo_class: The class used by drf to serialize repos.
        :param org_class: The class used by drf to serialize orgs.
        :param user_class: The class used by drf to serialize users.
        :param team_class: The class used by drf to serialize teams.
        """
        cls.RepoSerializer = repo_class or GHEPolicyCheckConfiguration.RepoSerializer
        cls.OrgSerializer = org_class or GHEPolicyCheckConfiguration.OrgSerializer
        cls.UserSerializer = user_class or GHEPolicyCheckConfiguration.UserSerializer
        cls.TeamSerializer = team_class or GHEPolicyCheckConfiguration.TeamSerializer

    @classmethod
    def configure_github_instance(cls, github_instance_class: Type[GitHubInstance]):
        cls.GitHubInstance = github_instance_class

# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
from unittest import TestCase

from ghe_policy_check.configuration import ConfigurationError, GHEPolicyCheckConfiguration
from ghe_policy_check.models import BasicOrg, BasicRepo, BasicTeam, BasicUser
from ghe_policy_check.serializers import (
    OrgSerializer,
    RepoSerializer,
    TeamSerializer,
    UserSerializer,
)

# pylint: disable=too-few-public-methods


class ConfigurationTestCase(TestCase):
    def test_configure_models(self):
        GHEPolicyCheckConfiguration.configure_models(BasicRepo, BasicOrg, BasicUser, BasicTeam)
        self.assertEqual(GHEPolicyCheckConfiguration.Repo, BasicRepo)
        self.assertEqual(GHEPolicyCheckConfiguration.Org, BasicOrg)
        self.assertEqual(GHEPolicyCheckConfiguration.User, BasicUser)
        self.assertEqual(GHEPolicyCheckConfiguration.Team, BasicTeam)

    def test_configure_models_abstract(self):
        BasicRepo.Meta.abstract = True
        with self.assertRaisesRegex(ConfigurationError, "abstract"):
            GHEPolicyCheckConfiguration.configure_models(BasicRepo, BasicOrg, BasicUser, BasicTeam)

    def test_configure_models_subclass(self):
        class FakeRepo:
            class Meta:
                pass

        with self.assertRaisesRegex(ConfigurationError, "Classes must subclass built in classes"):
            GHEPolicyCheckConfiguration.configure_models(FakeRepo, BasicOrg, BasicUser, BasicTeam)

    def test_configure_serializers(self):
        class FakeSerializer(RepoSerializer):
            pass

        GHEPolicyCheckConfiguration.configure_serializers(repo_class=FakeSerializer)
        self.assertEqual(GHEPolicyCheckConfiguration.RepoSerializer, FakeSerializer)
        self.assertEqual(GHEPolicyCheckConfiguration.TeamSerializer, TeamSerializer)
        self.assertEqual(GHEPolicyCheckConfiguration.UserSerializer, UserSerializer)
        self.assertEqual(GHEPolicyCheckConfiguration.OrgSerializer, OrgSerializer)

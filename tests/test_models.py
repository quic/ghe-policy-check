# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=no-self-use
from unittest.mock import Mock, call, patch

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from ghe_policy_check.configuration import GHEPolicyCheckConfiguration
from ghe_policy_check.models import BasicOrg, BasicRepo, BasicTeam, BasicUser


class ModelsTestCase(TestCase):
    fixtures = ["test_data"]

    def setUp(self):
        GHEPolicyCheckConfiguration.configure_models(BasicRepo, BasicOrg, BasicUser, BasicTeam)


class ReposTestCase(ModelsTestCase):
    fixtures = ["test_data"]

    @patch("ghe_policy_check.models.timezone")
    def test_set_classification(self, m_timezone):
        m_timezone.now.return_value = timezone.now()
        repo = GHEPolicyCheckConfiguration.Repo.objects.get(pk=1)
        repo.set_classification(GHEPolicyCheckConfiguration.Repo.Classification.LOW)
        self.assertEqual(repo.classification, GHEPolicyCheckConfiguration.Repo.Classification.LOW)
        self.assertEqual(repo.classification_modified, m_timezone.now.return_value)

    @patch("ghe_policy_check.models.timezone")
    def test_set_classification_same_classifcation(self, m_timezone):
        repo = GHEPolicyCheckConfiguration.Repo.objects.get(pk=1)
        repo.set_classification(GHEPolicyCheckConfiguration.Repo.Classification.MEDIUM)
        self.assertEqual(
            repo.classification, GHEPolicyCheckConfiguration.Repo.Classification.MEDIUM
        )
        m_timezone.now.assert_not_called()

    @patch("ghe_policy_check.models.timezone")
    def test_set_classification_none(self, m_timezone):
        m_timezone.now.return_value = timezone.now()
        repo = GHEPolicyCheckConfiguration.Repo.objects.get(pk=1)
        repo.set_classification(None)
        self.assertEqual(repo.classification, None)
        self.assertEqual(repo.classification_modified, m_timezone.now.return_value)


class UserTestCase(ModelsTestCase):
    def setUp(self):
        self.mock_new_gh_user = {
            "id": "2",
            "login": "test",
        }
        self.mock_existing_gh_user = {
            "login": "dummy user",
            "id": 1,
        }

    def test_user_count(self):
        self.assertEqual(GHEPolicyCheckConfiguration.User.objects.count(), 2)

    def test_from_github_user_create(self):
        user = GHEPolicyCheckConfiguration.User.from_github_user(self.mock_new_gh_user)

        self.assertEqual(
            user, GHEPolicyCheckConfiguration.User.objects.get(github_id=user.github_id)
        )
        self.assertEqual(user.username, self.mock_new_gh_user["login"])
        self.assertEqual(user.github_id, self.mock_new_gh_user["id"])

    def test_from_github_user_create_old_user_exists(self):
        user = GHEPolicyCheckConfiguration.User.from_github_user(self.mock_new_gh_user)

        # Set user id to an "old" value to mimic an old instance existing
        user.github_id = -1
        user.save()

        user = GHEPolicyCheckConfiguration.User.from_github_user(self.mock_new_gh_user)

        self.assertEqual(
            user, GHEPolicyCheckConfiguration.User.objects.get(github_id=user.github_id)
        )
        self.assertEqual(user.username, self.mock_new_gh_user["login"])
        self.assertEqual(user.github_id, self.mock_new_gh_user["id"])

    def test_from_github_user_integrity_error(self):
        fake_user = Mock()
        objs = GHEPolicyCheckConfiguration.User.objects
        GHEPolicyCheckConfiguration.User.objects = Mock(
            get=Mock(side_effect=[GHEPolicyCheckConfiguration.User.DoesNotExist, fake_user]),
            update_or_create=Mock(side_effect=IntegrityError),
        )
        user = GHEPolicyCheckConfiguration.User.from_github_user(self.mock_new_gh_user)
        self.assertEqual(user, fake_user)
        GHEPolicyCheckConfiguration.User.objects.update_or_create.assert_called_once()
        GHEPolicyCheckConfiguration.User.objects.get.assert_has_calls(
            [
                call(github_id=self.mock_new_gh_user["id"]),
                call(github_id=self.mock_new_gh_user["id"]),
            ]
        )

        GHEPolicyCheckConfiguration.User.objects = objs


class OrgTestCase(ModelsTestCase):
    def setUp(self):
        self.mock_new_gh_org = {
            "login": "test new org",
            "id": 10,
        }
        self.mock_existing_gh_org = {
            "login": "test-org-1",
            "id": 1,
        }

    def test_org_count(self):
        self.assertEqual(GHEPolicyCheckConfiguration.Org.objects.count(), 2)

    def test_from_github_org(self):
        org = GHEPolicyCheckConfiguration.Org.from_github_org(
            self.mock_new_gh_org, GHEPolicyCheckConfiguration.User.objects.get(pk=1)
        )
        self.assertEqual(
            org, GHEPolicyCheckConfiguration.Org.objects.get(github_id=self.mock_new_gh_org["id"])
        )
        self.assertEqual(org.owner, GHEPolicyCheckConfiguration.User.objects.get(pk=1))

    def test_from_github_org_existing_org(self):
        org = GHEPolicyCheckConfiguration.Org.from_github_org(
            self.mock_existing_gh_org, GHEPolicyCheckConfiguration.User.objects.get(pk=1)
        )
        self.assertEqual(
            org,
            GHEPolicyCheckConfiguration.Org.objects.get(github_id=self.mock_existing_gh_org["id"]),
        )

    def test_from_github_org_integrity_error(self):
        fake_org = Mock()
        objs = GHEPolicyCheckConfiguration.Org.objects
        GHEPolicyCheckConfiguration.Org.objects = Mock(
            get=Mock(side_effect=[GHEPolicyCheckConfiguration.Org.DoesNotExist, fake_org]),
            create=Mock(side_effect=IntegrityError),
        )
        org = GHEPolicyCheckConfiguration.Org.from_github_org(
            self.mock_new_gh_org, GHEPolicyCheckConfiguration.User.objects.get(pk=1)
        )
        self.assertEqual(org, fake_org)
        GHEPolicyCheckConfiguration.Org.objects.create.assert_called_once()
        GHEPolicyCheckConfiguration.Org.objects.get.assert_has_calls(
            [call(github_id=self.mock_new_gh_org["id"]), call(github_id=self.mock_new_gh_org["id"])]
        )

        GHEPolicyCheckConfiguration.Org.objects = objs


class TeamTestCase(ModelsTestCase):
    def setUp(self):
        self.mock_new_gh_team = {
            "slug": "test-team",
            "name": "test team",
            "id": 10,
        }
        self.mock_existing_gh_team = {
            "slug": "test-1",
            "name": "team 1",
            "id": 1,
        }

    def test_team_count(self):
        self.assertEqual(GHEPolicyCheckConfiguration.Team.objects.count(), 2)

    def test_from_github_team(self):
        team = GHEPolicyCheckConfiguration.Team.from_github_team(
            self.mock_new_gh_team, GHEPolicyCheckConfiguration.Org.objects.get(pk=1)
        )
        self.assertEqual(
            team,
            GHEPolicyCheckConfiguration.Team.objects.get(github_id=self.mock_new_gh_team["id"]),
        )

    def test_from_github_team_existing_team(self):
        team = GHEPolicyCheckConfiguration.Team.from_github_team(
            self.mock_existing_gh_team, GHEPolicyCheckConfiguration.Org.objects.get(pk=1)
        )
        self.assertEqual(
            team,
            GHEPolicyCheckConfiguration.Team.objects.get(
                github_id=self.mock_existing_gh_team["id"]
            ),
        )

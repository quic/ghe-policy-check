# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=no-self-use
import json
import os
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from ghe_policy_check.common.github_api.github_instance import GithubNotFoundException
from ghe_policy_check.common.github_api.types import GitHubRepo
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration
from ghe_policy_check.repo_polling import get_and_update_repo, get_polling_repos, remind_repo
from ghe_policy_check.utils import get_classification


class RepoPollingTestCase(TestCase):
    fixtures = ["test_data"]

    def setUp(self):
        self.exit = lambda a, b, c, d: None
        repo_path = os.path.join(os.path.dirname(__file__), "mock_payloads", "repos.json")
        with open(repo_path) as repo_file:
            self.repos = json.load(repo_file)

    def test_remind_repo(self):
        repo = GHEPolicyCheckConfiguration.Repo.objects.create(
            repo_name="test",
            github_id=1000,
            visibility=GHEPolicyCheckConfiguration.Repo.Visibility.PUBLIC,
            size=1,
            owner=GHEPolicyCheckConfiguration.User.objects.get(pk=1),
        )
        m_github_repo = GitHubRepo(owner={"login": "testuser"}, name="testrepo")

        mock_instance = Mock()
        mock_impersonated = Mock()

        mock_instance.impersonate_user = Mock(
            return_value=Mock(__enter__=lambda _: mock_impersonated, __exit__=self.exit),
        )
        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)
        remind_repo(repo, m_github_repo)
        mock_impersonated.add_repository_topics.assert_called_once_with(
            m_github_repo["owner"]["login"], m_github_repo["name"], [settings.NOT_CLASSIFIED_TOPIC]
        )

    def test_get_and_update_repo(self):
        github_repo = self.repos[0]
        local_repo = GHEPolicyCheckConfiguration.Repo.objects.get(github_id=github_repo["id"])
        mock_instance = Mock()
        mock_impersonated = Mock()
        mock_impersonated.get_repo_by_id.return_value = Mock(json=lambda: github_repo)

        mock_instance.impersonate_user = Mock(
            return_value=Mock(__enter__=lambda _: mock_impersonated, __exit__=self.exit),
        )
        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)
        now = timezone.now()
        get_and_update_repo(local_repo, now)

        self.assertEqual(local_repo.repo_name, github_repo["full_name"])
        self.assertEqual(local_repo.size, github_repo["size"])
        self.assertEqual(local_repo.description, github_repo["description"])
        self.assertEqual(local_repo.classification, get_classification(github_repo["topics"]))
        self.assertEqual(local_repo.visibility, github_repo["visibility"])
        self.assertEqual(local_repo.disabled, github_repo["disabled"])
        self.assertEqual(local_repo.html_url, github_repo["html_url"])

    @patch("ghe_policy_check.repo_polling.get_org_owner")
    def test_get_and_update_repo_delete_org(self, m_get_org_owner):
        github_repo = self.repos[0]
        local_repo = GHEPolicyCheckConfiguration.Repo.objects.get(github_id=github_repo["id"])
        mock_instance = Mock()
        mock_impersonated = Mock()
        mock_impersonated.get_repo_by_id.side_effect = GithubNotFoundException

        mock_instance.impersonate_user = Mock(
            return_value=Mock(__enter__=lambda _: mock_impersonated, __exit__=self.exit),
        )
        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)
        m_get_org_owner.return_value = GHEPolicyCheckConfiguration.User.objects.get(github_id=1)
        now = timezone.now()
        self.assertEqual(get_and_update_repo(local_repo, now), None)
        self.assertEqual(
            0, GHEPolicyCheckConfiguration.Repo.objects.filter(github_id=github_repo["id"]).count()
        )

    def test_get_and_update_repo_delete_user(self):
        github_repo = self.repos[2]
        local_repo = GHEPolicyCheckConfiguration.Repo.objects.get(github_id=github_repo["id"])
        mock_instance = Mock()
        mock_impersonated = Mock()
        mock_impersonated.get_repo_by_id.side_effect = GithubNotFoundException

        mock_instance.impersonate_user = Mock(
            return_value=Mock(__enter__=lambda _: mock_impersonated, __exit__=self.exit),
        )
        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)
        now = timezone.now()

        self.assertEqual(get_and_update_repo(local_repo, now), None)
        self.assertEqual(
            0, GHEPolicyCheckConfiguration.Repo.objects.filter(github_id=github_repo["id"]).count()
        )

    def test_get_polling_repos(self):
        repos = get_polling_repos()
        self.assertEqual(4, len(repos))

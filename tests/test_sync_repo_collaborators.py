# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=no-self-use
from unittest.mock import Mock, call

from django.test import TestCase

from ghe_policy_check.common.github_api.github_instance import (
    GithubAccountSuspendedException,
    GithubNotFoundException,
    GithubRepositoryBlockedException,
)
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration
from ghe_policy_check.sync_repo_collaborators import (
    _get_repo_collaborators,
    run_sync_repo_collaborators,
)


class TasksTestCase(TestCase):
    fixtures = ["test_data"]

    def setUp(self):
        self.exit = lambda a, b, c, d: None
        self.m_time = "20210601212915584192"

    def test_sync_repo_collaborators_update_owner_org(self):
        mock_instance = Mock()
        mock_impersonated = Mock()

        mock_impersonated.get_repo_collaborators = Mock(
            side_effect=[GithubNotFoundException, [{"id": 1}]]
        )

        mock_instance.impersonate_user = Mock(
            return_value=Mock(__enter__=lambda _: mock_impersonated, __exit__=self.exit),
        )

        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)

        repo = GHEPolicyCheckConfiguration.Repo.objects.get(pk=1)
        run_sync_repo_collaborators(repo.github_id, self.m_time)

        owner, _, repo_name = repo.repo_name.partition("/")
        mock_impersonated.get_repo_collaborators.assert_has_calls(
            [call(owner, repo_name), call(owner, repo_name)]
        )

        repo.refresh_from_db()
        self.assertEqual(repo.owner, repo.org.owner)
        self.assertTrue(
            GHEPolicyCheckConfiguration.User.objects.get(pk=1) in repo.collaborators.all()
        )

    def test_sync_repo_collaborators_task_suspended_owner_user(self):
        mock_instance = Mock()
        mock_impersonated = Mock()

        mock_impersonated.get_repo_collaborators = Mock(side_effect=GithubNotFoundException)
        mock_instance.impersonate_user = Mock(
            return_value=Mock(__enter__=lambda _: mock_impersonated, __exit__=self.exit),
        )
        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)

        repo = GHEPolicyCheckConfiguration.Repo.objects.get(pk=7)
        with self.assertRaises(GithubNotFoundException):
            run_sync_repo_collaborators(repo.github_id, self.m_time)

        owner, _, repo_name = repo.repo_name.partition("/")
        mock_impersonated.get_repo_collaborators.assert_called_once_with(owner, repo_name)

    def test_get_repo_collaborators_repo_blocked(self):
        mock_instance = Mock()
        mock_impersonated = Mock()

        mock_impersonated.get_repo_collaborators = Mock(
            side_effect=GithubRepositoryBlockedException
        )
        mock_instance.impersonate_user = Mock(
            return_value=Mock(__enter__=lambda _: mock_impersonated, __exit__=self.exit),
        )
        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)

        self.assertIsNone(
            _get_repo_collaborators(GHEPolicyCheckConfiguration.Repo.objects.get(pk=7))
        )

    def test_get_repo_collaborators_account_suspended(self):
        mock_instance = Mock()
        mock_impersonated = Mock()
        mock_return = []
        mock_impersonated.get_repo_collaborators = Mock(
            side_effect=[GithubAccountSuspendedException, mock_return]
        )
        mock_instance.impersonate_user = Mock(
            return_value=Mock(__enter__=lambda _: mock_impersonated, __exit__=self.exit),
        )
        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)

        self.assertEqual(
            _get_repo_collaborators(GHEPolicyCheckConfiguration.Repo.objects.get(pk=7)), mock_return
        )

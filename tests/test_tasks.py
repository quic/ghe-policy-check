# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=no-self-use
from unittest.mock import Mock, call, patch

from django.test import TestCase
from django.utils import timezone

from ghe_policy_check.common.github_api.github_instance import GithubNotFoundException
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration
from ghe_policy_check.repo_polling import GetAndUpdateRepo, GetPollingRepos, RemindRepo
from ghe_policy_check.tasks import (
    add_membership,
    add_org_member,
    delete_repository,
    repo_polling,
    sync_repo_collaborators,
    sync_repo_collaborators_task,
)


class TasksTestCase(TestCase):
    fixtures = ["test_data"]

    def setUp(self):
        self.exit = lambda a, b, c, d: None
        self.m_time = "20210601212915584192"

    def test_sync_repo_collaborators_task(self):
        mock_instance = Mock()
        mock_impersonated = Mock()

        mock_impersonated.get_repo_collaborators = Mock(return_value=[{"id": 1}])

        mock_instance.impersonate_user = Mock(
            return_value=Mock(__enter__=lambda _: mock_impersonated, __exit__=self.exit),
        )
        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)

        repo = GHEPolicyCheckConfiguration.Repo.objects.get(pk=1)
        sync_repo_collaborators_task(repo.github_id, self.m_time)

        owner, _, repo_name = repo.repo_name.partition("/")
        mock_impersonated.get_repo_collaborators.assert_called_once_with(owner, repo_name)

        repo.refresh_from_db()

        self.assertTrue(
            GHEPolicyCheckConfiguration.User.objects.get(pk=1) in repo.collaborators.all()
        )

    @patch("ghe_policy_check.tasks.run_sync_repo_collaborators")
    def test_sync_repo_collaborators_task_404(self, m_run_sync_repo_collaborators):
        m_run_sync_repo_collaborators.side_effect = GithubNotFoundException

        sync_repo_collaborators_task(0, self.m_time)
        m_run_sync_repo_collaborators.assert_called_once_with(0, self.m_time)

    @patch("ghe_policy_check.tasks.sync_repo_collaborators_task")
    def test_sync_repo_collaborators(self, m_sync_repo_collaborators_task):
        m_sync_repo_collaborators_task.delay = Mock()
        repo = GHEPolicyCheckConfiguration.Repo.objects.get(pk=1)
        sync_repo_collaborators(repo)
        m_sync_repo_collaborators_task.delay.assert_called_once()

    def test_delete_repository(self):
        delete_repository(1)
        with self.assertRaises(GHEPolicyCheckConfiguration.Repo.DoesNotExist):
            GHEPolicyCheckConfiguration.Repo.objects.get(github_id=1)

    def test_add_membership(self):
        team_id = 1
        user_id = 1
        add_membership(team_id, user_id)
        local_team = GHEPolicyCheckConfiguration.Team.objects.get(github_id=team_id)

        self.assertTrue(
            GHEPolicyCheckConfiguration.User.objects.get(github_id=user_id)
            in local_team.members.all()
        )
        self.assertEqual(4, local_team.repos.count())
        for repo in local_team.repos.all():
            self.assertTrue(
                GHEPolicyCheckConfiguration.User.objects.get(github_id=user_id)
                in repo.collaborators.all()
            )

    def test_add_membership_no_team(self):
        with self.assertRaises(GHEPolicyCheckConfiguration.Team.DoesNotExist):
            add_membership(9999, 1)

    @patch("ghe_policy_check.tasks.sync_repo_collaborators")
    def test_add_org_membership(self, m_sync_repo_collaborators):
        org_id = 1
        user_id = 1
        org = GHEPolicyCheckConfiguration.Org.objects.get(github_id=org_id)

        add_org_member(org_id, user_id)

        self.assertTrue(
            GHEPolicyCheckConfiguration.User.objects.get(github_id=user_id) in org.members.all()
        )

        for repo in org.repos.all():
            m_sync_repo_collaborators.assert_has_calls([call(repo)])

    def test_add_org_member_no_team(self):
        with self.assertRaises(GHEPolicyCheckConfiguration.Org.DoesNotExist):
            add_org_member(9999, 1)

    @patch("ghe_policy_check.tasks.timezone")
    def test_repo_polling(self, m_timezone):
        m_timezone.now.return_value = timezone.now()
        m_repo_1 = Mock(repo_name="Repo 1", is_reminder_candidate=True)
        m_repo_2 = Mock(repo_name="Repo 2", is_reminder_candidate=False)
        m_repo_3 = Mock(repo_name="Repo 3", is_reminder_candidate=True)
        GetPollingRepos.get_polling_repos = Mock(return_value=[m_repo_1, m_repo_2, m_repo_3])
        m_github_repo = Mock()
        GetAndUpdateRepo.get_and_update_repo = Mock(return_value=m_github_repo)
        RemindRepo.remind_repo = Mock()

        repo_polling()

        GetAndUpdateRepo.get_and_update_repo.assert_has_calls(
            [
                call(m_repo_1, m_timezone.now.return_value),
                call(m_repo_2, m_timezone.now.return_value),
                call(m_repo_3, m_timezone.now.return_value),
            ]
        )
        RemindRepo.remind_repo.assert_has_calls(
            [
                call(m_repo_1, m_github_repo),
                call(m_repo_3, m_github_repo),
            ]
        )

    @patch("ghe_policy_check.tasks.timezone")
    def test_repo_polling_error(self, m_timezone):
        m_timezone.now.return_value = timezone.now()
        m_repo_1 = Mock(repo_name="Repo 1", is_reminder_candidate=True)
        m_repo_2 = Mock(repo_name="Repo 2", is_reminder_candidate=False)
        m_repo_3 = Mock(repo_name="Repo 3", is_reminder_candidate=True)
        GetPollingRepos.get_polling_repos = Mock(return_value=[m_repo_1, m_repo_2, m_repo_3])
        GetAndUpdateRepo.get_and_update_repo = Mock(return_value=None)
        RemindRepo.remind_repo = Mock()

        repo_polling()

        GetAndUpdateRepo.get_and_update_repo.assert_has_calls(
            [
                call(m_repo_1, m_timezone.now.return_value),
                call(m_repo_2, m_timezone.now.return_value),
                call(m_repo_3, m_timezone.now.return_value),
            ]
        )
        RemindRepo.remind_repo.assert_not_called()

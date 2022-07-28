# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

import json
import os
from unittest.mock import Mock, call

from django.test import TestCase

from ghe_policy_check.common.github_api.github_instance import GithubNotFoundException
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration
from ghe_policy_check.sync_users import run_sync_users


class SyncUsersTestCase(TestCase):
    fixtures = ["test_data_with_suspended_user"]

    def setUp(self):
        user_path = os.path.join(os.path.dirname(__file__), "mock_payloads", "users.json")
        with open(user_path) as repo_file:
            self.users = json.load(repo_file)

    def test_sync_users(self):
        mock_instance = Mock()
        # Match order of last_synced field
        mock_instance.get_user.side_effect = [
            Mock(json=lambda: self.users[2]),
            Mock(json=lambda: self.users[1]),
        ]
        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)

        # Create mismatch in suspended status
        user = GHEPolicyCheckConfiguration.User.objects.get(username="Snowtocat")
        user.suspended_at = None
        user.save()

        run_sync_users()
        user = GHEPolicyCheckConfiguration.User.objects.get(username="Snowtocat")
        self.assertIsNotNone(user.suspended_at)

    def test_sync_users_not_found(self):
        mock_instance = Mock()

        mock_instance.get_user.side_effect = [
            GithubNotFoundException(),
            Mock(json=lambda: self.users[1]),
        ]
        GHEPolicyCheckConfiguration.GitHubInstance = Mock(return_value=mock_instance)
        run_sync_users()
        mock_instance.get_user.assert_has_calls([call("Snowtocat"), call("testowner")])

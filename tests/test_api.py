# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=no-self-use,unused-argument
import json

from django.contrib.auth import models as auth_models
from django.test import TestCase
from rest_framework.status import HTTP_200_OK
from rest_framework.test import APIClient

from ghe_policy_check.models import BasicOrg, BasicRepo, BasicTeam, BasicUser


def _get_data(response):
    return json.loads(response.content.decode("utf-8"))["data"]


class RestApiTestCase(TestCase):
    fixtures = ["test_data"]

    def setUp(self):
        self.client = APIClient()
        self.user = auth_models.User.objects.create(username="fakeuser")
        self.client.force_authenticate(self.user)

    def test_repo_get(self):
        response = self.client.get("/api/v1/repos/")
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(len(response.data), len(BasicRepo.objects.all()))

    def test_repo_get_filter_size(self):
        response = self.client.get("/api/v1/repos/", {"size": 0})
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(len(response.data), len(BasicRepo.objects.filter(size=0)))

    def test_user_get(self):
        response = self.client.get("/api/v1/users/")
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(len(response.data), len(BasicUser.objects.all()))

    def test_user_get_filter_github_id(self):
        response = self.client.get("/api/v1/users/", {"github_id": 1})
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_org_get(self):
        response = self.client.get("/api/v1/orgs/")
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(len(response.data), len(BasicOrg.objects.all()))

    def test_org_get_filter_org_name(self):
        response = self.client.get("/api/v1/orgs/", {"org_name": "test-org-2"})
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_team_get(self):
        response = self.client.get("/api/v1/teams/")
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(len(response.data), len(BasicTeam.objects.all()))

    def test_team_get_filter_team_name(self):
        response = self.client.get("/api/v1/teams/", {"team_name": "team 1"})
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

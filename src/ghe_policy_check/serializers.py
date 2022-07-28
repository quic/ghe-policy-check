# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

from rest_framework import serializers

from ghe_policy_check.models import BasicOrg, BasicRepo, BasicTeam, BasicUser

# pylint: disable=too-few-public-methods


class OrgSerializer(serializers.ModelSerializer):
    class Meta:
        model = BasicOrg
        read_only_fields = None
        fields = [
            "id",
            "org_name",
            "github_id",
            "owner",
            "members",
        ]


class RepoSerializer(serializers.ModelSerializer):
    class Meta:
        model = BasicRepo
        read_only_fields = None
        fields = [
            "id",
            "repo_name",
            "description",
            "classification",
            "visibility",
            "github_id",
            "html_url",
            "owner",
            "fork_source",
            "size",
            "disabled",
            "org",
            "collaborators",
            "teams",
        ]


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = BasicTeam
        read_only_fields = None
        fields = [
            "id",
            "team_name",
            "team_slug",
            "github_id",
            "org",
            "members",
        ]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = BasicUser
        read_only_fields = None
        fields = [
            "id",
            "username",
            "email",
            "github_id",
        ]

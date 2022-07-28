# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=unused-import, too-many-ancestors, no-self-use
from typing import Sequence, Type

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.authentication import BaseAuthentication
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from ghe_policy_check.common.github_api.webhook_dispatcher import dispatch_webhook
from ghe_policy_check.configuration import GHEPolicyCheckConfiguration  # type: ignore


@csrf_exempt
def csrf(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"csrfToken": get_token(request)})


class Webhooks(APIView):
    authentication_classes: Sequence[Type[BaseAuthentication]] = []
    permission_classes: Sequence[Type[BasePermission]] = []

    @csrf_exempt
    def post(self, request: Request) -> HttpResponse:
        return dispatch_webhook(request)


class RepoViewSet(ReadOnlyModelViewSet):
    queryset = GHEPolicyCheckConfiguration.Repo.objects.all()
    serializer_class = GHEPolicyCheckConfiguration.RepoSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {
        "repo_name": ["exact", "icontains"],
        "github_id": ["exact"],
        "classification": ["exact"],
        "visibility": ["exact"],
        "html_url": ["exact"],
        "owner__github_id": ["exact"],
        "fork_source": ["exact"],
        "size": ["exact", "gte", "lte"],
        "disabled": ["exact"],
    }
    ordering_fields = [
        "repo_name",
        "github_id",
        "classification",
        "visibility",
        "size",
    ]
    ordering = ["id"]


class UserViewSet(ReadOnlyModelViewSet):
    queryset = GHEPolicyCheckConfiguration.User.objects.all()
    serializer_class = GHEPolicyCheckConfiguration.UserSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["username", "github_id", "email"]
    ordering_fields = ["username", "github_id", "email"]
    ordering = ["id"]


class OrgViewSet(ReadOnlyModelViewSet):
    queryset = GHEPolicyCheckConfiguration.Org.objects.all()
    serializer_class = GHEPolicyCheckConfiguration.OrgSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["org_name", "github_id", "owner__github_id"]
    ordering_fields = ["org_name", "github_id"]
    ordering = ["id"]


class TeamViewSet(ReadOnlyModelViewSet):
    queryset = GHEPolicyCheckConfiguration.Team.objects.all()
    serializer_class = GHEPolicyCheckConfiguration.TeamSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["team_name", "team_slug", "github_id"]
    ordering_fields = ["team_name", "team_slug", "github_id"]
    ordering = ["id"]

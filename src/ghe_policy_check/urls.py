# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
from django.conf.urls import url
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from ghe_policy_check.views import OrgViewSet, RepoViewSet, TeamViewSet, UserViewSet, Webhooks, csrf

# Create a router and register our viewsets with it.
router = DefaultRouter()

router.register("api/v1/orgs", OrgViewSet, "orgs")
router.register("api/v1/repos", RepoViewSet, "repos")
router.register("api/v1/teams", TeamViewSet, "teams")
router.register("api/v1/users", UserViewSet, "users")

urlpatterns = [
    path("csrf/", csrf),
    path("webhooks/", Webhooks.as_view()),
    url(r"^", include(router.urls)),
]

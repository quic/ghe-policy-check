# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

import hmac
import json
import logging
from argparse import ArgumentParser
from hashlib import sha1
from typing import Any, Dict, List

import requests
from django.conf import settings
from django.core.management import BaseCommand
from django.utils.encoding import force_bytes

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Resends a github event."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--url", nargs=1, type=str, help="URL to webhook endpoint")
        parser.add_argument("--path", nargs=1, type=str, help="Absolute path to request body")
        parser.add_argument("--event", nargs=1, type=str, help="Github event type")
        parser.add_argument(
            "--key",
            nargs=1,
            type=str,
            help="Github Webhook Key",
            default=[settings.GITHUB_WEBHOOK_KEY],
        )

    def handle(
        self, *args: List[str], **kwargs: Dict[Any, Any]  # pylint: disable=unused-argument
    ) -> None:
        """
        Resends a GitHub event based on the passed parameter.
        Helpful for debugging a webhook request or replaying it once
        a bug has been fixed
        """
        url = kwargs["url"][0]
        file_path = kwargs["path"][0]
        webhook_key = kwargs["key"][0]
        github_event = kwargs["event"][0]

        with open(file_path) as file:
            body = file.read()

        request_json = json.loads(body)
        request_body = json.dumps(json.loads(body)).encode()
        sha1_hash = hmac.new(
            force_bytes(webhook_key), force_bytes(request_body), digestmod=sha1
        ).hexdigest()
        headers = {"x-hub-signature": f"sha1={sha1_hash}", "x-github-event": github_event}
        resp = requests.post(url=url, headers=headers, json=request_json)
        print(resp.status_code, resp.reason)

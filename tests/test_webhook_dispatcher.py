# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

import hmac
from hashlib import sha1
from unittest import TestCase

from ghe_policy_check.common.github_api.webhook_dispatcher import (
    InvalidSignature,
    OperationNotSupportedException,
    WebhookDispatcher,
)


class GitHubInstanceTestCase(TestCase):
    def setUp(self):
        self.secret = "secret"
        self.dispatcher = WebhookDispatcher(self.secret)

    def test_secure_github_request(self):
        body = b"body"

        sha1_hash = hmac.new(self.secret.encode(), body, digestmod=sha1).hexdigest()
        signature = f"sha1={sha1_hash}"
        self.assertIsNone(self.dispatcher.secure_github_request(signature, body))

    def test_secure_github_request_not_sha1(self):
        body = b"body"

        signature = "sha256=abcd"
        with self.assertRaises(OperationNotSupportedException):
            self.dispatcher.secure_github_request(signature, body)

    def test_secure_github_request_invalid_signature(self):
        body = b"body"

        sha1_hash = hmac.new(("wrong" + self.secret).encode(), body, digestmod=sha1).hexdigest()
        signature = f"sha1={sha1_hash}"
        with self.assertRaises(InvalidSignature):
            self.dispatcher.secure_github_request(signature, body)

    def test_secure_github_request_no_signature(self):
        with self.assertRaises(InvalidSignature):
            self.dispatcher.secure_github_request(None, b"")

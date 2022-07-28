# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

from unittest import TestCase

from ghe_policy_check.utils import get_classification


class TasksTestCase(TestCase):
    def test_get_classification(self):
        self.assertEqual("high", get_classification(["high"]))
        self.assertEqual("low", get_classification(["low"]))
        self.assertEqual("high", get_classification(["high", "medium"]))
        self.assertIsNone(get_classification(["not-a-class"]))
        self.assertIsNone(get_classification(["HIGH"]))

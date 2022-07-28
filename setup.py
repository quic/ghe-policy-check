# Copyright (c) 2021, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

from setuptools import setup, find_packages

requirements = ["github-webhook", "PyGithub", "python-ldap", "requests"]

testing_requirements = ["pytest"]

setup(
    name="ghe_policy_check",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=requirements,
    extras_require={"testing": testing_requirements},
)

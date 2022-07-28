# Copyright (c) 2021, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# pylint: disable=inherit-non-class,too-few-public-methods

from typing import Any, Dict, List, TypedDict, Union


class GitHubUser(TypedDict):
    """
    A representation of the json response that GitHub returns for User objects
    """

    login: str
    id: int
    node_id: str
    avatar_url: str
    gravatar_id: str
    url: str
    html_url: str
    followers_url: str
    following_url: str
    gists_url: str
    starred_url: str
    subscriptions_url: str
    organizations_url: str
    repos_url: str
    events_url: str
    received_events_url: str
    type: str
    site_admin: bool
    ldap_dn: str


class GithubParentRepo(TypedDict):
    owner: GitHubUser
    id: int
    name: str


class GitHubRepo(TypedDict):
    """
    A representation of the json response that GitHub returns for Repo objects
    """

    id: int
    node_id: str
    name: str
    full_name: str
    owner: GitHubUser
    private: bool
    html_url: str
    description: str
    fork: bool
    url: str
    archive_url: str
    assignees_url: str
    blobs_url: str
    branches_url: str
    collaborators_url: str
    comments_url: str
    commits_url: str
    compare_url: str
    contents_url: str
    contributors_url: str
    deployments_url: str
    downloads_url: str
    events_url: str
    forks_url: str
    git_commits_url: str
    git_refs_url: str
    git_tags_url: str
    git_url: str
    issue_comment_url: str
    issue_events_url: str
    issues_url: str
    keys_url: str
    labels_url: str
    languages_url: str
    merges_url: str
    milestones_url: str
    notifications_url: str
    pulls_url: str
    releases_url: str
    ssh_url: str
    stargazers_url: str
    statuses_url: str
    subscribers_url: str
    subscription_url: str
    tags_url: str
    teams_url: str
    trees_url: str
    clone_url: str
    mirror_url: str
    hooks_url: str
    svn_url: str
    homepage: str
    language: str
    forks_count: int
    stargazers_count: int
    watchers_count: int
    size: int
    default_branch: str
    open_issues_count: int
    is_template: bool
    topics: List[str]
    has_issues: bool
    has_projects: bool
    has_wiki: bool
    has_pages: bool
    has_downloads: bool
    archived: bool
    disabled: bool
    visibility: str
    pushed_at: str
    created_at: str
    updated_at: str
    permissions: Dict[str, bool]
    template_repository: Any
    parent: GithubParentRepo


class GitHubOrg(TypedDict):
    """
    A representation of the json response that GitHub returns for Org objects
    """

    login: str
    id: int
    node_id: str
    url: str
    repos_url: str
    events_url: str
    hooks_url: str
    issues_url: str
    members_url: str
    public_members_url: str
    avatar_url: str
    description: str


class GitHubTeam(TypedDict):
    """
    A representation of the json response that GitHub returns for Team objects
    """

    id: int
    node_id: str
    url: str
    html_url: str
    name: str
    slug: str
    description: str
    privacy: str
    permission: str
    members_url: str
    repositories_url: str
    parent: Any
    ldap_dn: str


GitHubObject = Union[GitHubOrg, GitHubRepo, GitHubTeam, GitHubUser]

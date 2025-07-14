#-
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security's commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

import os
import subprocess
from typing import List, Tuple
from src.utils import debug_log, log, error_exit
from src.api.contrast_api_client import FailureCategory
import src.git_handler as legacy_git_handler

class GitHandler:
    """
    Handles all Git and GitHub operations for the SmartFix workflow.
    """
    
    def __init__(self, github_token, github_repository, base_branch):
        """
        Initialize the Git handler with GitHub credentials and configuration.
        
        Args:
            github_token: GitHub token for authentication
            github_repository: The repository in format owner/repo
            base_branch: The base branch to create PRs against
        """
        self.github_token = github_token
        self.github_repository = github_repository
        self.base_branch = base_branch
    
    def get_gh_env(self):
        """
        Returns an environment dictionary with the GitHub token set.
        Used for GitHub CLI commands that require authentication.
        
        Returns:
            dict: Environment variables dictionary with GitHub token
        """
        return legacy_git_handler.get_gh_env()
    
    def configure_git_user(self):
        """Configures git user email and name."""
        legacy_git_handler.configure_git_user()
    
    def get_branch_name(self, remediation_id: str) -> str:
        """
        Generates a unique branch name based on remediation ID.
        
        Args:
            remediation_id: The remediation ID from Contrast
            
        Returns:
            str: A formatted branch name
        """
        return legacy_git_handler.get_branch_name(remediation_id)
    
    def prepare_feature_branch(self, remediation_id: str):
        """
        Prepares a clean repository state and creates a new feature branch.
        
        Args:
            remediation_id: The remediation ID from Contrast
            
        Raises:
            SystemExit: If branch preparation fails
        """
        legacy_git_handler.prepare_feature_branch(remediation_id)
    
    def stage_changes(self):
        """Stages all changes in the repository."""
        legacy_git_handler.stage_changes()
    
    def check_status(self) -> bool:
        """
        Checks if there are changes staged for commit.
        
        Returns:
            bool: True if changes exist
        """
        return legacy_git_handler.check_status()
    
    def generate_commit_message(self, vuln_title: str, vuln_uuid: str) -> str:
        """
        Generates the commit message.
        
        Args:
            vuln_title: The title of the vulnerability
            vuln_uuid: The UUID of the vulnerability
            
        Returns:
            str: A formatted commit message
        """
        return legacy_git_handler.generate_commit_message(vuln_title, vuln_uuid)
    
    def commit_changes(self, message: str):
        """
        Commits staged changes.
        
        Args:
            message: The commit message
            
        Raises:
            SystemExit: If commit fails
        """
        legacy_git_handler.commit_changes(message)
    
    def get_list_changed_files(self) -> List[str]:
        """
        Gets the list of files changed in the current working directory.
        
        Returns:
            List[str]: List of changed file paths
        """
        return legacy_git_handler.get_list_changed_files()
    
    def push_branch(self, branch_name: str):
        """
        Pushes the current branch to the remote repository.
        
        Args:
            branch_name: The name of the branch to push
            
        Raises:
            SystemExit: If push fails
        """
        legacy_git_handler.push_branch(branch_name)
    
    def generate_label_details(self, vuln_uuid: str) -> Tuple[str, str, str]:
        """
        Generates the label name, description, and color.
        
        Args:
            vuln_uuid: The UUID of the vulnerability
            
        Returns:
            tuple[str, str, str]: Label name, description, and color
        """
        return legacy_git_handler.generate_label_details(vuln_uuid)
    
    def ensure_label(self, label_name: str, description: str, color: str) -> bool:
        """
        Ensures the GitHub label exists, creating it if necessary.
        
        Args:
            label_name: The name of the label
            description: Description of the label
            color: Color code for the label
            
        Returns:
            bool: True if label exists or was created, False otherwise
        """
        return legacy_git_handler.ensure_label(label_name, description, color)
    
    def check_pr_status_for_label(self, label_name: str) -> str:
        """
        Checks GitHub for OPEN or MERGED PRs with the given label.
        
        Args:
            label_name: The name of the label to check
            
        Returns:
            str: 'OPEN', 'MERGED', or 'NONE'
        """
        return legacy_git_handler.check_pr_status_for_label(label_name)
    
    def count_open_prs_with_prefix(self, label_prefix: str) -> int:
        """
        Counts the number of open GitHub PRs with labels starting with the given prefix.
        
        Args:
            label_prefix: Prefix to match against PR labels
            
        Returns:
            int: Number of matching PRs
        """
        return legacy_git_handler.count_open_prs_with_prefix(label_prefix)
    
    def generate_pr_title(self, vuln_title: str) -> str:
        """
        Generates the Pull Request title.
        
        Args:
            vuln_title: The title of the vulnerability
            
        Returns:
            str: A formatted PR title
        """
        return legacy_git_handler.generate_pr_title(vuln_title)
    
    def create_pr(self, title: str, body: str, remediation_id: str, base_branch: str, label: str) -> str:
        """
        Creates a GitHub Pull Request.
        
        Args:
            title: The PR title
            body: The PR description body
            remediation_id: The remediation ID from Contrast
            base_branch: The target branch for the PR
            label: Label to apply to the PR
            
        Returns:
            str: The URL of the created PR or empty string on failure
            
        Raises:
            SystemExit: If PR creation fails
        """
        return legacy_git_handler.create_pr(title, body, remediation_id, base_branch, label)
    
    def cleanup_branch(self, branch_name: str):
        """
        Cleans up a git branch by switching back to the base branch and deleting the specified branch.
        
        Args:
            branch_name: Name of the branch to delete
        """
        legacy_git_handler.cleanup_branch(branch_name)
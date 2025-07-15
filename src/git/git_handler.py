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
import json
import tempfile
from typing import List, Tuple
from src.utils import debug_log, log, error_exit, run_command
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
        gh_env = os.environ.copy()
        gh_env["GITHUB_TOKEN"] = self.github_token
        return gh_env
    
    def configure_git_user(self):
        """Configures git user email and name."""
        log("Configuring Git user...")
        run_command(["git", "config", "--global", "user.email", "action@github.com"])
        run_command(["git", "config", "--global", "user.name", "GitHub Action"])
    
    def get_branch_name(self, remediation_id: str) -> str:
        """
        Generates a unique branch name based on remediation ID.
        
        Args:
            remediation_id: The remediation ID from Contrast
            
        Returns:
            str: A formatted branch name
        """
        return f"smartfix/remediation-{remediation_id}"
    
    def prepare_feature_branch(self, remediation_id: str):
        """
        Prepares a clean repository state and creates a new feature branch.
        
        Args:
            remediation_id: The remediation ID from Contrast
            
        Raises:
            SystemExit: If branch preparation fails
        """
        log("Cleaning workspace and creating new feature branch...")
        
        try:
            # Reset any changes and remove all untracked files to ensure a pristine state
            run_command(["git", "reset", "--hard"], check=True)
            run_command(["git", "clean", "-fd"], check=True)  # Force removal of untracked files and directories
            run_command(["git", "checkout", self.base_branch], check=True)
            # Pull latest changes to ensure we're working with the most up-to-date code
            run_command(["git", "pull", "--ff-only"], check=True)
            log(f"Successfully cleaned workspace and checked out latest {self.base_branch}")
            
            branch_name = self.get_branch_name(remediation_id)
            # Now create the new branch
            log(f"Creating and checking out new branch: {branch_name}")
            run_command(["git", "checkout", "-b", branch_name]) # run_command exits on failure
        except subprocess.CalledProcessError as e:
            log(f"ERROR: Failed to prepare clean workspace due to a subprocess error: {str(e)}", is_error=True)
            error_exit(remediation_id, FailureCategory.GIT_COMMAND_FAILURE.value)
    
    def stage_changes(self):
        """Stages all changes in the repository."""
        debug_log("Staging changes made by AI agent...")
        # Run with check=False as it might fail if there are no changes, which is ok
        run_command(["git", "add", "."], check=False)
    
    def check_status(self) -> bool:
        """
        Checks if there are changes staged for commit.
        
        Returns:
            bool: True if changes exist
        """
        status_output = run_command(["git", "status", "--porcelain"])
        if not status_output:
            log("No changes detected after AI agent run. Nothing to commit or push.")
            return False
        else:
            debug_log("Changes detected, proceeding with commit and push.")
            return True
    
    def generate_commit_message(self, vuln_title: str, vuln_uuid: str) -> str:
        """
        Generates the commit message.
        
        Args:
            vuln_title: The title of the vulnerability
            vuln_uuid: The UUID of the vulnerability
            
        Returns:
            str: A formatted commit message
        """
        return f"Automated fix attempt for: {vuln_title[:50]} (VULN-{vuln_uuid})"
    
    def commit_changes(self, message: str):
        """
        Commits staged changes.
        
        Args:
            message: The commit message
            
        Raises:
            SystemExit: If commit fails
        """
        log(f"Committing changes with message: '{message}'")
        run_command(["git", "commit", "-m", message]) # run_command exits on failure
    
    def get_list_changed_files(self) -> List[str]:
        """
        Gets the list of files changed in the current working directory.
        
        Returns:
            List[str]: List of changed file paths
        """
        debug_log("Getting list of changed files...")
        # Use --no-pager to prevent potential hanging
        # Use --name-only to get just the file paths
        # Use check=True because if this fails, something is wrong with the git status
        status_output = run_command(["git", "--no-pager", "status", "--porcelain", "--untracked-files=no"])
        
        changed_files = []
        for line in status_output.splitlines():
            if line and len(line) >= 3:  # Ensure line has enough length to contain a file path
                changed_files.append(line[3:])  # Skip the first 3 characters (status codes)
        
        debug_log(f"Changed files: {changed_files}")
        return changed_files
    
    def push_branch(self, branch_name: str):
        """
        Pushes the current branch to the remote repository.
        
        Args:
            branch_name: The name of the branch to push
            
        Raises:
            SystemExit: If push fails
        """
        log(f"Pushing branch {branch_name} to remote...")
        remote_url = f"https://x-access-token:{self.github_token}@github.com/{self.github_repository}.git"
        run_command(["git", "push", "--set-upstream", remote_url, branch_name]) # run_command exits on failure
    
    def generate_label_details(self, vuln_uuid: str) -> Tuple[str, str, str]:
        """
        Generates the label name, description, and color.
        
        Args:
            vuln_uuid: The UUID of the vulnerability
            
        Returns:
            tuple[str, str, str]: Label name, description, and color
        """
        label_name = f"contrast-vuln-id:VULN-{vuln_uuid}"
        label_description = "Vulnerability identified by Contrast AI SmartFix"
        label_color = "ff0000" # Red
        return label_name, label_description, label_color
    
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
        log(f"Ensuring GitHub label exists: {label_name}")
        if len(label_name) > 50:
            log(f"Label name '{label_name}' exceeds GitHub's 50-character limit.", is_error=True)
            return False
            
        gh_env = self.get_gh_env()
        
        # First try to list labels to see if it already exists
        try:
            list_command = [
                "gh", "label", "list",
                "--repo", self.github_repository,
                "--json", "name"
            ]
            list_output = run_command(list_command, env=gh_env, check=False)
            try:
                labels = json.loads(list_output)
                existing_label_names = [label.get("name") for label in labels]
                if label_name in existing_label_names:
                    log(f"Label '{label_name}' already exists.")
                    return True
            except json.JSONDecodeError:
                debug_log(f"Could not parse label list JSON: {list_output}")
        except Exception as e:
            debug_log(f"Error listing labels: {e}")
        
        # Create the label if it doesn't exist
        label_command = [
            "gh", "label", "create", label_name,
            "--description", description,
            "--color", color,
            "--repo", self.github_repository
        ]
        
        try:
            # Run with check=False to handle the label already existing
            process = subprocess.run(
                label_command, 
                env=gh_env,
                capture_output=True,
                text=True,
                check=False
            )
            
            if process.returncode == 0:
                log(f"Label '{label_name}' created successfully.")
                return True
            else:
                # Check for "already exists" type of error which is OK
                if "already exists" in process.stderr.lower():
                    log(f"Label '{label_name}' already exists.")
                    return True
                else:
                    log(f"Error creating label: {process.stderr}", is_error=True)
                    return False
        except Exception as e:
            log(f"Exception while creating label: {e}", is_error=True)
            return False
    
    def check_pr_status_for_label(self, label_name: str) -> str:
        """
        Checks GitHub for OPEN or MERGED PRs with the given label.
        
        Args:
            label_name: The name of the label to check
            
        Returns:
            str: 'OPEN', 'MERGED', or 'NONE'
        """
        log(f"Checking GitHub PR status for label: {label_name}")
        gh_env = self.get_gh_env()
    
        # Check for OPEN PRs
        open_pr_command = [
            "gh", "pr", "list",
            "--repo", self.github_repository,
            "--label", label_name,
            "--state", "open",
            "--limit", "1", # We only need to know if at least one exists
            "--json", "number" # Requesting JSON output
        ]
        open_pr_output = run_command(open_pr_command, env=gh_env, check=False) # Don't exit if command fails (e.g., no PRs found)
        try:
            if open_pr_output and json.loads(open_pr_output): # Check if output is not empty and contains JSON data
                 debug_log(f"Found OPEN PR for label {label_name}.")
                 return "OPEN"
        except json.JSONDecodeError:
            log(f"Could not parse JSON output from gh pr list (open): {open_pr_output}", is_error=True)
    
    
        # Check for MERGED PRs
        merged_pr_command = [
            "gh", "pr", "list",
            "--repo", self.github_repository,
            "--label", label_name,
            "--state", "merged",
            "--limit", "1",
            "--json", "number"
        ]
        merged_pr_output = run_command(merged_pr_command, env=gh_env, check=False)
        try:
            if merged_pr_output and json.loads(merged_pr_output):
                debug_log(f"Found MERGED PR for label {label_name}.")
                return "MERGED"
        except json.JSONDecodeError:
            log(f"Could not parse JSON output from gh pr list (merged): {merged_pr_output}", is_error=True)
    
        debug_log(f"No existing OPEN or MERGED PR found for label {label_name}.")
        return "NONE"
    
    def count_open_prs_with_prefix(self, label_prefix: str) -> int:
        """
        Counts the number of open GitHub PRs with labels starting with the given prefix.
        
        Args:
            label_prefix: Prefix to match against PR labels
            
        Returns:
            int: Number of matching PRs
        """
        log(f"Counting open PRs with label prefix: '{label_prefix}'")
        gh_env = self.get_gh_env()
    
        # Fetch labels of open PRs in JSON format
        pr_list_command = [
            "gh", "pr", "list",
            "--repo", self.github_repository,
            "--state", "open",
            "--limit", "100", # Adjust if needed, max is 100 for this command without pagination
            "--json", "number,labels" # Get PR number and labels
        ]
    
        try:
            pr_list_output = run_command(pr_list_command, env=gh_env, check=True)
            prs_data = json.loads(pr_list_output)
        except json.JSONDecodeError:
            log(f"Could not parse JSON output from gh pr list: {pr_list_output}", is_error=True)
            return 0 # Assume zero if we can't parse
        except Exception as e:
            log(f"Error running gh pr list command: {e}", is_error=True)
            # Consider if we should exit or return 0. Returning 0 might be safer to avoid blocking unnecessarily.
            return 0
    
        count = 0
        for pr in prs_data:
            if "labels" in pr and isinstance(pr["labels"], list):
                for label in pr["labels"]:
                    if "name" in label and label["name"].startswith(label_prefix):
                        count += 1
                        break # Count this PR once, even if it has multiple matching labels
        
        debug_log(f"Found {count} open PR(s) with label prefix '{label_prefix}'.")
        return count
    
    def generate_pr_title(self, vuln_title: str) -> str:
        """
        Generates the Pull Request title.
        
        Args:
            vuln_title: The title of the vulnerability
            
        Returns:
            str: A formatted PR title
        """
        return f"Fix: {vuln_title[:100]}"
    
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
        log("Creating Pull Request...")
        
        head_branch = self.get_branch_name(remediation_id)
    
        # Set a maximum PR body size (GitHub recommends keeping it under 65536 chars)
        MAX_PR_BODY_SIZE = 32000
        
        # Truncate PR body if too large
        if len(body) > MAX_PR_BODY_SIZE:
            log(f"PR body is too large ({len(body)} chars). Truncating to {MAX_PR_BODY_SIZE} chars.", is_warning=True)
            body = body[:MAX_PR_BODY_SIZE] + "\n\n...[Content truncated due to size limits]..."
    
        # Add disclaimer to PR body
        body += "\n\n*Contrast AI SmartFix is powered by AI, so mistakes are possible.  Review before merging.*\n\n"
        
        # Create a temporary file to store the PR body
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(body)
            debug_log(f"PR body written to temporary file: {temp_file_path}")
        
        try:
            # Check file exists and print size for debugging
            if os.path.exists(temp_file_path):
                file_size = os.path.getsize(temp_file_path)
                debug_log(f"Temporary file exists: {temp_file_path}, size: {file_size} bytes")
            else:
                log(f"Error: Temporary file {temp_file_path} does not exist", is_error=True)
                return ""
                
            gh_env = self.get_gh_env()
            
            # First check if gh is available
            try:
                version_output = subprocess.run(
                    ["gh", "--version"], 
                    check=False, 
                    capture_output=True, 
                    text=True
                )
                debug_log(f"GitHub CLI version: {version_output.stdout.strip() if version_output.returncode == 0 else 'Not available'}")
            except Exception as e:
                log(f"Could not determine GitHub CLI version: {e}", is_error=True)
            
            pr_command = [
                "gh", "pr", "create",
                "--title", title,
                "--body-file", temp_file_path,
                "--base", base_branch,
                "--head", head_branch,
            ]
            if label:
                pr_command.extend(["--label", label])
    
            # Run the command and capture the output (PR URL)
            pr_url = run_command(pr_command, env=gh_env, check=True)
            if pr_url:
                log(f"Successfully created PR: {pr_url}")
            return pr_url
    
        except FileNotFoundError:
            log(f"Error: gh command not found. Please ensure the GitHub CLI is installed and in PATH.", is_error=True)
            error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)
        except Exception as e:
            log(f"An unexpected error occurred during PR creation: {e}", is_error=True)
            error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)
        finally:
            # Clean up the temporary file
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    debug_log(f"Temporary PR body file {temp_file_path} removed.")
                except OSError as e:
                    log(f"Could not remove temporary file {temp_file_path}: {e}", is_error=True)
    
    def cleanup_branch(self, branch_name: str):
        """
        Cleans up a git branch by switching back to the base branch and deleting the specified branch.
        This function is designed to be safe to use even if errors occur (using check=False).
        
        Args:
            branch_name: Name of the branch to delete
        """
        debug_log(f"Cleaning up branch: {branch_name}")
        run_command(["git", "reset", "--hard"], check=False)
        run_command(["git", "checkout", self.base_branch], check=False)
        run_command(["git", "branch", "-D", branch_name], check=False)
        log("Branch cleanup completed.")
        
    def get_last_commit_changed_files(self) -> List[str]:
        """
        Gets the list of files changed in the most recent commit.
        
        Returns:
            List[str]: List of changed file paths
        """
        debug_log("Getting files changed in the last commit...")
        # Use --no-pager to prevent potential hanging
        # Use HEAD~1..HEAD to specify the range (last commit)
        # Use --name-only to get just the file paths
        diff_output = run_command(["git", "--no-pager", "diff", "HEAD~1..HEAD", "--name-only"])
        changed_files = diff_output.splitlines()
        debug_log(f"Files changed in last commit: {changed_files}")
        return changed_files
        
    def amend_commit(self):
        """
        Amends the last commit with currently staged changes, reusing the previous message.
        """
        log("Amending the previous commit with QA fixes...")
        # Use --no-edit to keep the original commit message
        run_command(["git", "commit", "--amend", "--no-edit"]) # run_command exits on failure
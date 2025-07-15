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
import json
import subprocess
from typing import List
from src.utils import run_command, debug_log, log, error_exit
from src.api.contrast_api_client import FailureCategory
from src.config_compat import GITHUB_TOKEN, GITHUB_REPOSITORY, BASE_BRANCH

# NOTE: This module provides legacy git handler functions.
# New code should use the GitHandler class from src.git.git_handler instead.

def get_gh_env():
    """
    Returns an environment dictionary with the GitHub token set.
    
    @deprecated Use GitHandler.get_gh_env() instead
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.get_gh_env()
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    return {
        "GH_TOKEN": GITHUB_TOKEN,
        **os.environ
    }

def configure_git_user():
    """
    Configures the git user name and email for committing changes.
    
    @deprecated Use GitHandler.configure_git_user() instead
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            git_handler_obj.configure_git_user()
            return
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    # Set the git user name and email for committing changes
    run_command(["git", "config", "--global", "user.name", "Contrast Security"])
    run_command(["git", "config", "--global", "user.email", "seceng@contrastsecurity.com"])
    run_command(["git", "config", "--global", "pull.rebase", "false"])

def get_branch_name(remediation_id: str) -> str:
    """
    Returns a branch name for a given remediation ID.
    
    @deprecated Use GitHandler.get_branch_name() instead
    
    Args:
        remediation_id: The ID of the remediation
        
    Returns:
        str: The branch name to use for the remediation
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.get_branch_name(remediation_id)
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    return f"smartfix/remediation-{remediation_id}"

def prepare_feature_branch(remediation_id: str):
    """
    Creates and checks out a feature branch for a remediation.
    
    @deprecated Use GitHandler.prepare_feature_branch() instead
    
    Args:
        remediation_id: The ID of the remediation
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            git_handler_obj.prepare_feature_branch(remediation_id)
            return
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    branch_name = get_branch_name(remediation_id)
    
    # Make sure we're on the base branch before creating a new one
    run_command(["git", "checkout", BASE_BRANCH])
    
    # Delete the branch if it already exists (from a previous run)
    try:
        run_command(["git", "branch", "-D", branch_name])
    except Exception:
        # It's okay if the branch doesn't exist yet
        pass

    # Create a new branch from the base branch
    run_command(["git", "checkout", "-b", branch_name])

def stage_changes():
    """
    Stages all changes in the git repository.
    
    @deprecated Use GitHandler.stage_changes() instead
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            git_handler_obj.stage_changes()
            return
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    run_command(["git", "add", "-A"])

def check_status() -> bool:
    """
    Checks if there are any changes to commit.
    
    @deprecated Use GitHandler.check_status() instead
    
    Returns:
        bool: True if there are changes to commit, False otherwise
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.check_status()
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    result = run_command(["git", "status", "--porcelain"])
    return bool(result.strip())

def get_list_changed_files() -> List[str]:
    """
    Returns a list of all changed files in the git repository.
    
    @deprecated Use GitHandler.get_list_changed_files() instead
    
    Returns:
        List[str]: List of changed file paths
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.get_list_changed_files()
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    result = run_command(["git", "diff", "--name-only", "HEAD"])
    changed_files = [line.strip() for line in result.splitlines() if line.strip()]
    
    # Also include staged but uncommitted files
    staged = run_command(["git", "diff", "--name-only", "--staged"])
    staged_files = [line.strip() for line in staged.splitlines() if line.strip()]
    
    # Also include untracked files
    untracked = run_command(["git", "ls-files", "--others", "--exclude-standard"])
    untracked_files = [line.strip() for line in untracked.splitlines() if line.strip()]
    
    # Combine all files and remove duplicates
    all_files = list(set(changed_files + staged_files + untracked_files))
    
    return all_files

def get_last_commit_changed_files() -> List[str]:
    """
    Returns a list of files changed in the last commit.
    
    @deprecated Use GitHandler.get_last_commit_changed_files() instead
    
    Returns:
        List[str]: List of changed file paths
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.get_last_commit_changed_files()
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    result = run_command(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"])
    return [line.strip() for line in result.splitlines() if line.strip()]

def generate_commit_message(vuln_title: str, vuln_uuid: str) -> str:
    """
    Generates a commit message for a vulnerability fix.
    
    @deprecated Use GitHandler.generate_commit_message() instead
    
    Args:
        vuln_title: The title of the vulnerability
        vuln_uuid: The UUID of the vulnerability
        
    Returns:
        str: The generated commit message
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.generate_commit_message(vuln_title, vuln_uuid)
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    # Limit the title length to avoid overly long commit messages
    title_limit = 50
    truncated_title = vuln_title[:title_limit] if len(vuln_title) > title_limit else vuln_title
    return f"Automated fix attempt for: {truncated_title} (VULN-{vuln_uuid})"

def commit_changes(message: str):
    """
    Commits staged changes with the given message.
    
    @deprecated Use GitHandler.commit_changes() instead
    
    Args:
        message: The commit message
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            git_handler_obj.commit_changes(message)
            return
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    run_command(["git", "commit", "-m", message])

def amend_commit():
    """
    Amends the previous commit with any newly staged changes.
    
    @deprecated Use GitHandler.amend_commit() instead
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            git_handler_obj.amend_commit()
            return
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    run_command(["git", "commit", "--amend", "--no-edit"])

def push_branch(branch_name: str):
    """
    Pushes a branch to the remote repository.
    
    @deprecated Use GitHandler.push_branch() instead
    
    Args:
        branch_name: The name of the branch to push
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            git_handler_obj.push_branch(branch_name)
            return
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    run_command(["git", "push", "-f", "origin", branch_name])

def cleanup_branch(branch_name: str):
    """
    Cleans up a feature branch by switching to the base branch and deleting the feature branch.
    
    @deprecated Use GitHandler.cleanup_branch() instead
    
    Args:
        branch_name: The name of the branch to clean up
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            git_handler_obj.cleanup_branch(branch_name)
            return
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    # Make sure we're not on the branch we're trying to delete
    run_command(["git", "checkout", BASE_BRANCH])
    
    try:
        # Delete the local branch
        run_command(["git", "branch", "-D", branch_name])
    except Exception as e:
        debug_log(f"Warning: Failed to delete local branch {branch_name}: {e}")
    
    try:
        # Delete the remote branch if it exists
        run_command(["git", "push", "origin", "--delete", branch_name])
    except Exception as e:
        debug_log(f"Warning: Failed to delete remote branch {branch_name}: {e}")

def generate_label_details(vuln_uuid: str) -> tuple:
    """
    Generates details for a label to be used in a PR.
    
    @deprecated Use GitHandler.generate_label_details() instead
    
    Args:
        vuln_uuid: The UUID of the vulnerability
        
    Returns:
        tuple: A tuple containing (label_name, description, color)
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.generate_label_details(vuln_uuid)
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    label_name = f"contrast-vuln-id:VULN-{vuln_uuid}"
    description = "Vulnerability ID from Contrast Security"
    color = "ff0000"  # Red
    return (label_name, description, color)

def ensure_label(label_name: str, description: str, color: str) -> bool:
    """
    Ensures that a label exists in the GitHub repository.
    
    @deprecated Use GitHandler.ensure_label() instead
    
    Args:
        label_name: The name of the label
        description: The description of the label
        color: The color of the label (without # prefix)
        
    Returns:
        bool: True if the label was created or already exists, False otherwise
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.ensure_label(label_name, description, color)
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    env = get_gh_env()
    
    # Check if the label already exists
    try:
        result = subprocess.run(
            ["gh", "label", "list", "--json", "name"],
            capture_output=True,
            text=True,
            env=env,
            check=True
        )
        labels = json.loads(result.stdout)
        if any(label["name"] == label_name for label in labels):
            debug_log(f"Label {label_name} already exists")
            return True
    except Exception as e:
        log(f"Error checking if label exists: {e}", is_warning=True)
    
    # Create the label
    try:
        subprocess.run(
            ["gh", "label", "create", label_name, "--description", description, "--color", color],
            capture_output=True,
            env=env,
            check=True
        )
        debug_log(f"Created label {label_name}")
        return True
    except Exception as e:
        log(f"Error creating label: {e}", is_warning=True)
        return False

def check_pr_status_for_label(label_name: str) -> str:
    """
    Checks if there is an open PR with the given label.
    
    @deprecated Use GitHandler.check_pr_status_for_label() instead
    
    Args:
        label_name: The label to check for
        
    Returns:
        str: "OPEN" if there is an open PR, "MERGED" if there is a merged PR,
             "CLOSED" if there is a closed PR, or "NONE" if there is no PR
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.check_pr_status_for_label(label_name)
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    env = get_gh_env()
    
    # Search for PRs with the label
    try:
        # Try to find OPEN PRs first
        result = subprocess.run(
            ["gh", "pr", "list", "--search", f"label:{label_name}", "--json", "state"],
            capture_output=True,
            text=True,
            env=env,
            check=True
        )
        prs = json.loads(result.stdout)
        if prs:
            return "OPEN"
        
        # Check for closed PRs
        result = subprocess.run(
            ["gh", "pr", "list", "--search", f"label:{label_name} is:closed", "--json", "state"],
            capture_output=True,
            text=True,
            env=env,
            check=True
        )
        prs = json.loads(result.stdout)
        if prs:
            # Check if any are merged
            for pr in prs:
                if pr.get("state") == "MERGED":
                    return "MERGED"
            return "CLOSED"
            
        return "NONE"
    except Exception as e:
        log(f"Error checking PR status: {e}", is_warning=True)
        return "NONE"

def count_open_prs_with_prefix(label_prefix: str) -> int:
    """
    Counts the number of open PRs with labels that start with the given prefix.
    
    @deprecated Use GitHandler.count_open_prs_with_prefix() instead
    
    Args:
        label_prefix: The prefix to search for
        
    Returns:
        int: The number of open PRs
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.count_open_prs_with_prefix(label_prefix)
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    env = get_gh_env()
    
    try:
        # Use the GitHub CLI to list open PRs with the label prefix
        result = subprocess.run(
            ["gh", "pr", "list", "--search", f"label:{label_prefix}*", "--json", "number"],
            capture_output=True,
            text=True,
            env=env,
            check=True
        )
        prs = json.loads(result.stdout)
        return len(prs)
    except Exception as e:
        log(f"Error counting open PRs: {e}", is_warning=True)
        return 0

def generate_pr_title(vuln_title: str) -> str:
    """
    Generates a PR title for a vulnerability fix.
    
    @deprecated Use GitHandler.generate_pr_title() instead
    
    Args:
        vuln_title: The title of the vulnerability
        
    Returns:
        str: The generated PR title
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.generate_pr_title(vuln_title)
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    title_limit = 100
    truncated_title = vuln_title[:title_limit] if len(vuln_title) > title_limit else vuln_title
    return f"Fix: {truncated_title}"

def create_pr(title: str, body: str, remediation_id: str, base_branch: str, label: str) -> str:
    """
    Creates a PR with the given title, body, and label.
    
    @deprecated Use GitHandler.create_pr() instead
    
    Args:
        title: The title of the PR
        body: The body of the PR
        remediation_id: The ID of the remediation
        base_branch: The branch to merge into
        label: The label to apply to the PR
        
    Returns:
        str: The URL of the created PR
    """
    try:
        from src.main import git_handler_obj
        if git_handler_obj:
            return git_handler_obj.create_pr(title, body, remediation_id, base_branch, label)
    except (ImportError, AttributeError):
        pass
        
    # Fall back to legacy implementation
    env = get_gh_env()
    branch_name = get_branch_name(remediation_id)
    
    # Make sure we've pushed the branch first
    push_branch(branch_name)
    
    # Create the PR using the GitHub CLI
    try:
        result = subprocess.run(
            [
                "gh", "pr", "create",
                "--title", title,
                "--body", body,
                "--base", base_branch,
                "--label", label
            ],
            capture_output=True,
            text=True,
            env=env,
            check=True
        )
        
        # Extract the PR URL from the output
        url = result.stdout.strip()
        debug_log(f"Created PR: {url}")
        return url
    except Exception as e:
        log(f"Error creating PR: {e}", is_error=True)
        error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)
        return ""
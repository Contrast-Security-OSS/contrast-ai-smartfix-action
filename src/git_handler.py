# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security’s commercial offerings. Even though it is
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
import re
from typing import List, Optional
from src.utils import run_command, debug_log, log, error_exit
from src.contrast_api import FailureCategory
from src.config import get_config
from src.coding_agents import CodingAgents
config = get_config()


def get_gh_env():
    """
    Returns an environment dictionary with the GitHub token set.
    Used for GitHub CLI commands that require authentication.

    Returns:
        dict: Environment variables dictionary with GitHub token
    """
    gh_env = os.environ.copy()
    gh_env["GITHUB_TOKEN"] = config.GITHUB_TOKEN

    return gh_env


def log_copilot_assignment_error(issue_number: int, error: Exception, remediation_label: str):
    """
    Logs a standardized error message for Copilot assignment failures and exits.

    Args:
        issue_number: The issue number that failed assignment
        error: The exception that occurred
        remediation_label: The remediation label to extract ID from
    """
    from src.config import get_config

    log(f"Error: Failed to assign issue #{issue_number} to @Copilot: {error}", is_error=True)
    log("This may be due to:")
    log("  - GitHub Copilot is not enabled for this repository")
    log("  - The PAT (Personal Access Token) was not created by a user with a Copilot license seat")
    log("  - @Copilot user doesn't exist in this repository")
    log("  - Insufficient permissions to assign users")
    log("  - Repository settings restricting assignments")

    # Extract remediation_id from the remediation_label (format: "smartfix-id:REMEDIATION_ID")
    remediation_id = remediation_label.replace("smartfix-id:", "") if remediation_label.startswith("smartfix-id:") else "unknown"

    # Only exit in non-testing mode
    config = get_config()
    if not config.testing:
        error_exit(remediation_id, FailureCategory.GIT_COMMAND_FAILURE.value)
    else:
        log("NOTE: In testing mode, not exiting on Copilot assignment failure", is_warning=True)


def get_pr_changed_files_count(pr_number: int) -> int:
    """Get the number of changed files in a PR using GitHub CLI.

    Args:
        pr_number: The PR number to check

    Returns:
        int: Number of changed files, or -1 if there was an error
    """
    try:
        result = run_command(['gh', 'pr', 'view', str(pr_number), '--json', 'changedFiles', '--jq', '.changedFiles'],
                             env=get_gh_env(), check=False)
        if result is None:
            debug_log(f"Failed to get changed files count for PR {pr_number}")
            return -1

        # Parse the result as an integer
        try:
            count = int(result.strip())
            debug_log(f"PR {pr_number} has {count} changed files")
            return count
        except ValueError:
            debug_log(f"Invalid response from gh command for PR {pr_number}: {result}")
            return -1

    except Exception as e:
        debug_log(f"Error getting changed files count for PR {pr_number}: {e}")
        return -1


def check_issues_enabled() -> bool:
    """Check if GitHub Issues are enabled for the repository.

    Returns:
        bool: True if Issues are enabled, False if disabled
    """
    try:
        # Try to list issues - this will fail if Issues are disabled
        result = run_command(['gh', 'issue', 'list', '--repo', config.GITHUB_REPOSITORY, '--limit', '1'],
                             env=get_gh_env(), check=False)

        # If the command succeeded, Issues are enabled
        if result is not None:
            debug_log("GitHub Issues are enabled for this repository")
            return True
        else:
            debug_log("GitHub Issues appear to be disabled for this repository")
            return False

    except Exception as e:
        error_message = str(e).lower()
        if "issues are disabled" in error_message:
            debug_log("GitHub Issues are disabled for this repository")
            return False
        else:
            # If it's a different error, assume Issues are enabled but there's another problem
            debug_log(f"Error checking if Issues are enabled, assuming they are: {e}")
            return True


def configure_git_user():
    """Configures git user email and name."""
    log("Configuring Git user...")
    run_command(["git", "config", "--global", "user.email", "action@github.com"])
    run_command(["git", "config", "--global", "user.name", "GitHub Action"])


def get_branch_name(remediation_id: str) -> str:
    """Generates a unique branch name based on remediation ID"""
    return f"smartfix/remediation-{remediation_id}"


def prepare_feature_branch(remediation_id: str):
    """Prepares a clean repository state and creates a new feature branch."""
    log("Cleaning workspace and creating new feature branch...")

    try:
        # Reset any changes and remove all untracked files to ensure a pristine state
        run_command(["git", "reset", "--hard"], check=True)
        run_command(["git", "clean", "-fd"], check=True)  # Force removal of untracked files and directories
        run_command(["git", "checkout", config.BASE_BRANCH], check=True)
        # Pull latest changes to ensure we're working with the most up-to-date code
        run_command(["git", "pull", "--ff-only"], check=True)
        log(f"Successfully cleaned workspace and checked out latest {config.BASE_BRANCH}")

        branch_name = get_branch_name(remediation_id)
        # Now create the new branch
        log(f"Creating and checking out new branch: {branch_name}")
        run_command(["git", "checkout", "-b", branch_name])  # run_command exits on failure
    except subprocess.CalledProcessError as e:
        log(f"ERROR: Failed to prepare clean workspace due to a subprocess error: {str(e)}", is_error=True)
        error_exit(remediation_id, FailureCategory.GIT_COMMAND_FAILURE.value)


def stage_changes():
    """Stages all changes in the repository."""
    debug_log("Staging changes made by AI agent...")
    # Run with check=False as it might fail if there are no changes, which is ok
    run_command(["git", "add", "."], check=False)


def check_status() -> bool:
    """Checks if there are changes staged for commit. Returns True if changes exist."""
    status_output = run_command(["git", "status", "--porcelain"])
    if not status_output:
        log("No changes detected after AI agent run. Nothing to commit or push.")
        return False
    else:
        debug_log("Changes detected, proceeding with commit and push.")
        return True


def generate_commit_message(vuln_title: str, vuln_uuid: str) -> str:
    """Generates the commit message."""
    return f"Automated fix attempt for: {vuln_title[:50]} (VULN-{vuln_uuid})"


def commit_changes(message: str):
    """Commits staged changes."""
    log(f"Committing changes with message: '{message}'")
    run_command(["git", "commit", "-m", message])  # run_command exits on failure


def get_last_commit_changed_files() -> List[str]:
    """Gets the list of files changed in the most recent commit."""
    debug_log("Getting files changed in the last commit...")
    # Use --no-pager to prevent potential hanging
    # Use HEAD~1..HEAD to specify the range (last commit)
    # Use --name-only to get just the file paths
    # Use check=True because if this fails, something is wrong with the commit history
    diff_output = run_command(["git", "--no-pager", "diff", "HEAD~1..HEAD", "--name-only"])
    changed_files = diff_output.splitlines()
    debug_log(f"Files changed in last commit: {changed_files}")
    return changed_files


def amend_commit():
    """Amends the last commit with currently staged changes, reusing the previous message."""
    log("Amending the previous commit with QA fixes...")
    # Use --no-edit to keep the original commit message
    run_command(["git", "commit", "--amend", "--no-edit"])  # run_command exits on failure


def push_branch(branch_name: str):
    """Pushes the current branch to the remote repository."""
    log(f"Pushing branch {branch_name} to remote...")
    remote_url = f"https://x-access-token:{config.GITHUB_TOKEN}@github.com/{config.GITHUB_REPOSITORY}.git"
    run_command(["git", "push", "--set-upstream", remote_url, branch_name])  # run_command exits on failure


def generate_label_details(vuln_uuid: str) -> tuple[str, str, str]:
    """Generates the label name, description, and color."""
    label_name = f"contrast-vuln-id:VULN-{vuln_uuid}"
    label_description = "Vulnerability identified by Contrast AI SmartFix"
    label_color = "ff0000"  # Red
    return label_name, label_description, label_color


def ensure_label(label_name: str, description: str, color: str) -> bool:
    """
    Ensures the GitHub label exists, creating it if necessary.

    Returns:
        bool: True if label exists or was successfully created, False otherwise
    """
    debug_log(f"Ensuring GitHub label exists: {label_name}")
    if len(label_name) > 50:
        log(f"Label name '{label_name}' exceeds GitHub's 50-character limit.", is_error=True)
        return False

    gh_env = get_gh_env()

    # First try to list labels to see if it already exists
    try:
        list_command = [
            "gh", "label", "list",
            "--repo", config.GITHUB_REPOSITORY,
            "--json", "name"
        ]
        import json
        list_output = run_command(list_command, env=gh_env, check=False)
        try:
            labels = json.loads(list_output)
            existing_label_names = [label.get("name") for label in labels]
            if label_name in existing_label_names:
                debug_log(f"Label '{label_name}' already exists.")
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
        "--repo", config.GITHUB_REPOSITORY
    ]

    try:
        # Run with check=False to handle the label already existing
        import subprocess
        process = subprocess.run(
            label_command,
            env=gh_env,
            capture_output=True,
            text=True,
            check=False
        )

        if process.returncode == 0:
            debug_log(f"Label '{label_name}' created successfully.")
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


def check_pr_status_for_label(label_name: str) -> str:
    """
    Checks GitHub for OPEN or MERGED PRs with the given label.

    Returns:
        str: 'OPEN', 'MERGED', or 'NONE'
    """
    log(f"Checking GitHub PR status for label: {label_name}")
    gh_env = get_gh_env()

    # Check for OPEN PRs
    open_pr_command = [
        "gh", "pr", "list",
        "--repo", config.GITHUB_REPOSITORY,
        "--label", label_name,
        "--state", "open",
        "--limit", "1",  # We only need to know if at least one exists
        "--json", "number"  # Requesting JSON output
    ]
    open_pr_output = run_command(open_pr_command, env=gh_env, check=False)  # Don't exit if command fails (e.g., no PRs found)
    try:
        if open_pr_output and json.loads(open_pr_output):  # Check if output is not empty and contains JSON data
            debug_log(f"Found OPEN PR for label {label_name}.")
            return "OPEN"
    except json.JSONDecodeError:
        log(f"Could not parse JSON output from gh pr list (open): {open_pr_output}", is_error=True)

    # Check for MERGED PRs
    merged_pr_command = [
        "gh", "pr", "list",
        "--repo", config.GITHUB_REPOSITORY,
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


def count_open_prs_with_prefix(label_prefix: str) -> int:
    """Counts the number of open GitHub PRs with at least one label starting with the given prefix."""
    log(f"Counting open PRs with label prefix: '{label_prefix}'")
    gh_env = get_gh_env()

    # Fetch labels of open PRs in JSON format. Limit might need adjustment if > 100 open PRs.
    # Using --search to filter by label prefix might be more efficient if supported, but --json gives flexibility.
    # Let's try fetching labels and filtering locally first.
    pr_list_command = [
        "gh", "pr", "list",
        "--repo", config.GITHUB_REPOSITORY,
        "--state", "open",
        "--limit", "100",  # Adjust if needed, max is 100 for this command without pagination
        "--json", "number,labels"  # Get PR number and labels
    ]

    try:
        pr_list_output = run_command(pr_list_command, env=gh_env, check=True)
        prs_data = json.loads(pr_list_output)
    except json.JSONDecodeError:
        log(f"Could not parse JSON output from gh pr list: {pr_list_output}", is_error=True)
        return 0  # Assume zero if we can't parse
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
                    break  # Count this PR once, even if it has multiple matching labels

    debug_log(f"Found {count} open PR(s) with label prefix '{label_prefix}'.")
    return count


def generate_pr_title(vuln_title: str) -> str:
    """Generates the Pull Request title."""
    return f"Fix: {vuln_title[:100]}"


def create_pr(title: str, body: str, remediation_id: str, base_branch: str, label: str) -> str:
    """Creates a GitHub Pull Request.

    Returns:
        str: The URL of the created pull request, or an empty string if creation failed (though gh usually exits).
    """
    log("Creating Pull Request...")
    import tempfile
    import os.path
    import subprocess

    head_branch = get_branch_name(remediation_id)

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
            return

        gh_env = get_gh_env()

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
        log("Error: gh command not found. Please ensure the GitHub CLI is installed and in PATH.", is_error=True)
        error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)
    except Exception as e:
        log(f"An unexpected error occurred during PR creation: {e}", is_error=True)
        error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                debug_log(f"Temporary PR body file {temp_file_path} removed.")
            except OSError as e:
                log(f"Could not remove temporary file {temp_file_path}: {e}", is_error=True)


def cleanup_branch(branch_name: str):
    """
    Cleans up a git branch by switching back to the base branch and deleting the specified branch.
    This function is designed to be safe to use even if errors occur (using check=False).

    Args:
        branch_name: Name of the branch to delete
    """
    debug_log(f"Cleaning up branch: {branch_name}")
    run_command(["git", "reset", "--hard"], check=False)
    run_command(["git", "checkout", config.BASE_BRANCH], check=False)
    run_command(["git", "branch", "-D", branch_name], check=False)
    log("Branch cleanup completed.")


def create_issue(title: str, body: str, vuln_label: str, remediation_label: str) -> int:
    """
    Creates a GitHub issue with the specified title, body, and labels.

    Args:
        title: The title of the issue
        body: The body content of the issue
        vuln_label: The vulnerability label (contrast-vuln-id:*)
        remediation_label: The remediation label (smartfix-id:*)

    Returns:
        int: The issue number if created successfully, None otherwise
    """
    log(f"Creating GitHub issue with title: {title}")

    # Check if Issues are enabled for this repository
    if not check_issues_enabled():
        log("GitHub Issues are disabled for this repository. Cannot create issue.", is_error=True)
        return None

    gh_env = get_gh_env()

    # Ensure both labels exist
    ensure_label(vuln_label, "Vulnerability identified by Contrast", "ff0000")  # Red
    ensure_label(remediation_label, "Remediation ID for Contrast vulnerability", "0075ca")  # Blue

    # Format labels for the command
    labels = f"{vuln_label},{remediation_label}"

    # Create the issue first without assignment
    issue_command = [
        "gh", "issue", "create",
        "--repo", config.GITHUB_REPOSITORY,
        "--title", title,
        "--body", body,
        "--label", labels
    ]

    try:
        # Run the command and capture the output (issue URL)
        issue_url = run_command(issue_command, env=gh_env, check=True)
        log(f"Successfully created issue: {issue_url}")

        # Extract the issue number from the URL
        # URL format is typically: https://github.com/owner/repo/issues/123
        try:
            issue_number = int(os.path.basename(issue_url.strip()))
            log(f"Issue number extracted: {issue_number}")

            if config.CODING_AGENT == CodingAgents.CLAUDE_CODE.name:
                debug_log("CLAUDE_CODE agent detected no need to edit issue for assignment")
                return issue_number

            # Now try to assign to @copilot separately
            assign_command = [
                "gh", "issue", "edit",
                "--repo", config.GITHUB_REPOSITORY,
                str(issue_number),
                "--add-assignee", "@copilot"
            ]

            try:
                run_command(assign_command, env=gh_env, check=True)
                debug_log("Issue assigned to @Copilot")
            except Exception as assign_error:
                log_copilot_assignment_error(issue_number, assign_error, remediation_label)

            return issue_number
        except ValueError:
            log(f"Could not extract issue number from URL: {issue_url}", is_error=True)
            return None

    except Exception as e:
        log(f"Failed to create GitHub issue: {e}", is_error=True)
        return None


def find_issue_with_label(label: str) -> int:
    """
    Searches for a GitHub issue with a specific label.

    Args:
        label: The label to search for

    Returns:
        int: The issue number if found, None otherwise
    """
    log(f"Searching for GitHub issue with label: {label}")

    # Check if Issues are enabled for this repository
    if not check_issues_enabled():
        log("GitHub Issues are disabled for this repository. Cannot search for issues.", is_error=True)
        return None

    gh_env = get_gh_env()

    issue_list_command = [
        "gh", "issue", "list",
        "--repo", config.GITHUB_REPOSITORY,
        "--label", label,
        "--state", "open",
        "--limit", "1",  # Limit to 1 result to get the newest/first one
        "--json", "number,createdAt"
    ]

    try:
        issue_list_output = run_command(issue_list_command, env=gh_env, check=False)

        if not issue_list_output:
            debug_log(f"No issues found with label: {label}")
            return None

        issues_data = json.loads(issue_list_output)

        if not issues_data:
            debug_log(f"No issues found with label: {label}")
            return None

        # Get the first (newest) issue
        issue_number = issues_data[0].get("number")
        if issue_number:
            debug_log(f"Found issue #{issue_number} with label: {label}")
            return issue_number

        return None
    except json.JSONDecodeError:
        log(f"Could not parse JSON output from gh issue list: {issue_list_output}", is_error=True)
        return None
    except Exception as e:
        log(f"Error searching for GitHub issue with label: {e}", is_error=True)
        return None


def reset_issue(issue_number: int, remediation_label: str) -> bool:
    """
    Resets a GitHub issue by:
    1. Removing all existing labels that start with "smartfix-id:"
    2. Adding the specified remediation label
    3. If coding agent is CoPilot then unassigning the @Copilot user and reassigning the issue to @Copilot
    4. If coding agent is Claude Code then adding a comment to notify @claude to reprocess the issue

    The reset will not occur if there's an open PR for the issue.

    Args:
        issue_number: The issue number to reset
        remediation_label: The new remediation label to add

    Returns:
        bool: True if the issue was successfully reset, False otherwise
    """
    log(f"Resetting GitHub issue #{issue_number}")

    # Check if Issues are enabled for this repository
    if not check_issues_enabled():
        log("GitHub Issues are disabled for this repository. Cannot reset issue.", is_error=True)
        return False

    # First check if there's an open PR for this issue
    open_pr = find_open_pr_for_issue(issue_number)
    if open_pr:
        pr_number = open_pr.get("number")
        pr_url = open_pr.get("url")
        log(f"Cannot reset issue #{issue_number} because it has an open PR #{pr_number}: {pr_url}", is_error=True)
        return False

    gh_env = get_gh_env()

    try:
        # First, get the current labels for the issue
        issue_info_command = [
            "gh", "issue", "view",
            "--repo", config.GITHUB_REPOSITORY,
            str(issue_number),
            "--json", "labels"
        ]

        issue_info = run_command(issue_info_command, env=gh_env, check=True)

        try:
            labels_data = json.loads(issue_info)
            current_labels = [label["name"] for label in labels_data.get("labels", [])]
            debug_log(f"Current labels on issue #{issue_number}: {current_labels}")

            # Find any remediation labels to remove
            labels_to_remove = [label for label in current_labels
                                if label.startswith("smartfix-id:")]

            if labels_to_remove:
                debug_log(f"Labels to remove: {labels_to_remove}")

                # Remove the old remediation labels
                remove_label_command = [
                    "gh", "issue", "edit",
                    "--repo", config.GITHUB_REPOSITORY,
                    str(issue_number),
                    "--remove-label", ",".join(labels_to_remove)
                ]

                run_command(remove_label_command, env=gh_env, check=True)
                debug_log(f"Removed existing remediation labels from issue #{issue_number}")
        except json.JSONDecodeError:
            debug_log(f"Could not parse issue info JSON: {issue_info}")
        except Exception as e:
            log(f"Error processing current issue labels: {e}", is_error=True)

        # Ensure the remediation label exists
        ensure_label(remediation_label, "Remediation ID for Contrast vulnerability", "0075ca")

        # Add the new remediation label
        add_label_command = [
            "gh", "issue", "edit",
            "--repo", config.GITHUB_REPOSITORY,
            str(issue_number),
            "--add-label", remediation_label
        ]

        run_command(add_label_command, env=gh_env, check=True)
        log(f"Added new remediation label to issue #{issue_number}")

        # If using CLAUDE_CODE, skip reassignment and tag @claude in comment
        if config.CODING_AGENT == CodingAgents.CLAUDE_CODE.name:
            debug_log("CLAUDE_CODE agent detected need to add a comment and tag @claude for reprocessing")
            # Add a comment to the existing issue to notify @claude to reprocess
            comment:str = f"@claude reprocess this issue with the new remediation label: {remediation_label} and attempt a fix."
            comment_command = [
                "gh", "issue", "comment",
                "--repo", config.GITHUB_REPOSITORY,
                str(issue_number),
                "--create-if-none",
                "--edit-last",
                "--body", comment
            ]

            # add a new comment and use the @claude handle to reprocess the issue
            run_command(comment_command, env=gh_env, check=True)
            log(f"Added new comment tagging @claude to issue #{issue_number}")
            return True

        # Unassign from @Copilot (if assigned)
        unassign_command = [
            "gh", "issue", "edit",
            "--repo", config.GITHUB_REPOSITORY,
            str(issue_number),
            "--remove-assignee", "@copilot"
        ]

        # Don't check here as it might not be assigned
        run_command(unassign_command, env=gh_env, check=False)

        # Reassign to @Copilot
        assign_command = [
            "gh", "issue", "edit",
            "--repo", config.GITHUB_REPOSITORY,
            str(issue_number),
            "--add-assignee", "@copilot"
        ]

        try:
            run_command(assign_command, env=gh_env, check=True)
            debug_log(f"Reassigned issue #{issue_number} to @Copilot")
        except Exception as assign_error:
            log_copilot_assignment_error(issue_number, assign_error, remediation_label)

        return True
    except Exception as e:
        log(f"Failed to reset issue #{issue_number}: {e}", is_error=True)
        return False


def find_open_pr_for_issue(issue_number: int) -> dict:
    """
    Finds an open pull request associated with the given issue number.
    Specifically looks for PRs with branch names matching the pattern 'copilot/fix-{issue_number}'
    or 'claude/issue-{issue_number}-'.

    Args:
        issue_number: The issue number to find a PR for

    Returns:
        dict: A dictionary with PR information (number, url, title) if found, None otherwise
    """
    debug_log(f"Searching for open PR related to issue #{issue_number}")
    gh_env = get_gh_env()

    # Use search patterns that match PRs with branch names for both Copilot and Claude Code
    # First try to find PRs with Copilot branch pattern
    search_pattern = f"head:copilot/fix-{issue_number}"

    pr_list_command = [
        "gh", "pr", "list",
        "--repo", config.GITHUB_REPOSITORY,
        "--state", "open",
        "--search", search_pattern,
        "--limit", "1",  # Limit to 1 result as we only need the first match
        "--json", "number,url,title,headRefName,baseRefName,state"
    ]

    try:
        pr_list_output = run_command(pr_list_command, env=gh_env, check=False)

        if not pr_list_output or pr_list_output.strip() == "[]":
            # Try again with claude branch pattern
            claude_search_pattern = f"head:claude/issue-{issue_number}-"
            claude_pr_list_command = [
                "gh", "pr", "list",
                "--repo", config.GITHUB_REPOSITORY,
                "--state", "open",
                "--search", claude_search_pattern,
                "--limit", "1",
                "--json", "number,url,title,headRefName,baseRefName,state"
            ]

            pr_list_output = run_command(claude_pr_list_command, env=gh_env, check=False)
            
            if not pr_list_output or pr_list_output.strip() == "[]":
                debug_log(f"No open PRs found for issue #{issue_number} with either Copilot or Claude branch pattern")
                return None

        prs_data = json.loads(pr_list_output)

        if not prs_data:
            debug_log(f"No open PRs found for issue #{issue_number}")
            return None

        # Get the first matching PR
        pr_info = prs_data[0]
        pr_number = pr_info.get("number")
        pr_url = pr_info.get("url")
        pr_title = pr_info.get("title")

        if pr_number and pr_url:
            log(f"Found open PR #{pr_number} for issue #{issue_number}: {pr_title}")
            return pr_info

        return None
    except json.JSONDecodeError:
        log(f"Could not parse JSON output from gh pr list: {pr_list_output}", is_error=True)
        return None
    except Exception as e:
        log(f"Error searching for PRs related to issue #{issue_number}: {e}", is_error=True)
        return None


def extract_issue_number_from_branch(branch_name: str) -> Optional[int]:
    """
    Extracts the GitHub issue number from a branch name with format 'copilot/fix-<issue_number>'
    or 'claude/issue-<issue_number>-YYYYMMDD-HHMM'.

    Args:
        branch_name: The branch name to extract the issue number from

    Returns:
        Optional[int]: The issue number if found and valid, None otherwise
    """
    if not branch_name:
        return None

    # Check for copilot branch format: copilot/fix-<number>
    copilot_pattern = r'^copilot/fix-(\d+)$'
    match = re.match(copilot_pattern, branch_name)

    if not match:
        # Check for claude branch format: claude/issue-<number>-YYYYMMDD-HHMM
        claude_pattern = r'^claude/issue-(\d+)-\d{8}-\d{4}$'
        match = re.match(claude_pattern, branch_name)

    if match:
        try:
            issue_number = int(match.group(1))
            # Validate that it's a positive number (GitHub issue numbers start from 1)
            if issue_number > 0:
                return issue_number
        except ValueError:
            debug_log(f"Failed to convert extracted issue number '{match.group(1)}' from copilot or claude branch to int")
            pass

    return None


def add_labels_to_pr(pr_number: int, labels: List[str]) -> bool:
    """
    Add labels to an existing pull request.

    Args:
        pr_number: The PR number to add labels to
        labels: List of label names to add

    Returns:
        bool: True if labels were successfully added, False otherwise
    """
    if not labels:
        debug_log("No labels provided to add to PR")
        return True

    log(f"Adding labels to PR #{pr_number}: {labels}")
    gh_env = get_gh_env()

    # First ensure all labels exist
    for label_name in labels:
        if label_name.startswith("contrast-vuln-id:"):
            ensure_label(label_name, "Vulnerability identified by Contrast", "ff0000")  # Red
        elif label_name.startswith("smartfix-id:"):
            ensure_label(label_name, "Remediation ID for Contrast vulnerability", "0075ca")  # Blue
        else:
            # For other labels, use default description and color
            ensure_label(label_name, "Label added by Contrast AI SmartFix", "cccccc")  # Gray

    # Add labels to the PR
    add_labels_command = [
        "gh", "pr", "edit",
        "--repo", config.GITHUB_REPOSITORY,
        str(pr_number),
        "--add-label", ",".join(labels)
    ]

    try:
        run_command(add_labels_command, env=gh_env, check=True)
        log(f"Successfully added labels to PR #{pr_number}: {labels}")
        return True
    except Exception as e:
        log(f"Failed to add labels to PR #{pr_number}: {e}", is_error=True)
        return False

# -
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

import re
from typing import List, Optional
from src.utils import run_command, debug_log
from src.config import get_config


class GitOperations:
    """
    Git operations wrapper for SmartFix SCM functionality.

    This class handles all git command operations including branch management,
    staging, committing, and status checking.
    """

    def __init__(self):
        """Initialize Git operations handler."""
        pass

    def configure_git_user(self) -> None:
        """Configures git user email and name."""
        from src.utils import log
        log("Configuring Git user...")
        run_command(["git", "config", "--global", "user.email", "action@github.com"])
        run_command(["git", "config", "--global", "user.name", "GitHub Action"])

    def get_branch_name(self, remediation_id: str) -> str:
        """Generates a unique branch name based on remediation ID"""
        return f"smartfix/remediation-{remediation_id}"

    def prepare_feature_branch(self, remediation_id: str) -> None:
        """
        Prepare a clean repository state and create a new feature branch.

        Args:
            remediation_id: The remediation ID to use for branch naming
        """
        from src.utils import log
        from src.smartfix.shared.failure_categories import FailureCategory
        from src.utils import error_exit
        import subprocess

        config = get_config()
        log("Cleaning workspace and creating new feature branch...")

        try:
            # Reset any changes and remove all untracked files to ensure a pristine state
            run_command(['git', 'reset', '--hard'], check=True)
            run_command(['git', 'clean', '-fd'], check=True)  # Force removal of untracked files and directories
            run_command(['git', 'checkout', config.BASE_BRANCH], check=True)
            # Pull latest changes to ensure we're working with the most up-to-date code
            run_command(['git', 'pull', '--ff-only'], check=True)
            log(f"Successfully cleaned workspace and checked out latest {config.BASE_BRANCH}")

            branch_name = self.get_branch_name(remediation_id)
            # Now create the new branch
            log(f"Creating and checking out new branch: {branch_name}")
            run_command(['git', 'checkout', '-b', branch_name])  # run_command exits on failure
        except subprocess.CalledProcessError as e:
            log(f"ERROR: Failed to prepare clean workspace due to a subprocess error: {str(e)}", is_error=True)
            error_exit(remediation_id, FailureCategory.GIT_COMMAND_FAILURE.value)

    def stage_changes(self) -> None:
        """Stages all changes in the repository."""
        debug_log("Staging changes made by AI agent...")
        # Run with check=False as it might fail if there are no changes, which is ok
        run_command(["git", "add", "."], check=False)

    def check_status(self) -> bool:
        """Checks if there are changes staged for commit. Returns True if changes exist."""
        from src.utils import log
        status_output = run_command(["git", "status", "--porcelain"])
        if not status_output:
            log("No changes detected after AI agent run. Nothing to commit or push.")
            return False
        else:
            debug_log("Changes detected, proceeding with commit and push.")
            return True

    def generate_commit_message(self, vuln_title: str, vuln_uuid: str) -> str:
        """Generates the commit message."""
        return f"Automated fix attempt for: {vuln_title[:50]} (VULN-{vuln_uuid})"

    def commit_changes(self, message: str) -> None:
        """Commits staged changes."""
        from src.utils import log
        log(f"Committing changes with message: '{message}'")
        run_command(["git", "commit", "-m", message])  # run_command exits on failure

    def get_uncommitted_changed_files(self) -> List[str]:
        """Gets the list of files that have been modified but not yet committed.

        This is useful for tracking changes made by agents before committing them.

        Returns:
            List[str]: List of file paths that have been modified, added, or deleted
        """
        debug_log("Getting uncommitted changed files...")
        # Use --no-pager to prevent potential hanging
        # Use --name-only to get just the file paths
        # Compare working directory + staged changes against HEAD
        diff_output = run_command(["git", "--no-pager", "diff", "HEAD", "--name-only"], check=False)
        if not diff_output:
            debug_log("No uncommitted changes found")
            return []

        changed_files = [f for f in diff_output.splitlines() if f.strip()]
        debug_log(f"Uncommitted changed files: {changed_files}")
        return changed_files

    def get_last_commit_changed_files(self) -> List[str]:
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

    def amend_commit(self) -> None:
        """Amends the last commit with currently staged changes, reusing the previous message."""
        from src.utils import log
        log("Amending the previous commit with QA fixes...")
        # Use --no-edit to keep the original commit message
        run_command(["git", "commit", "--amend", "--no-edit"])  # run_command exits on failure

    def push_branch(self, branch_name: str) -> None:
        """Pushes the current branch to the remote repository."""
        from src.utils import log
        from urllib.parse import urlparse
        from src.config import get_config
        config = get_config()
        log(f"Pushing branch {branch_name} to remote...")
        # Extract hostname from GITHUB_SERVER_URL (e.g., "https://github.com" -> "github.com")
        parsed = urlparse(config.GITHUB_SERVER_URL)
        github_host = parsed.netloc
        remote_url = f"https://x-access-token:{config.GITHUB_TOKEN}@{github_host}/{config.GITHUB_REPOSITORY}.git"
        run_command(["git", "push", "--set-upstream", remote_url, branch_name])  # run_command exits on failure

    def cleanup_branch(self, branch_name: str) -> None:
        """Cleans up a git branch by switching back to the base branch and deleting the specified branch.
        This function is designed to be safe to use even if errors occur (using check=False).

        Args:
            branch_name: Name of the branch to delete
        """
        from src.utils import log
        from src.config import get_config
        config = get_config()
        debug_log(f"Cleaning up branch: {branch_name}")
        run_command(["git", "reset", "--hard"], check=False)
        run_command(["git", "checkout", config.BASE_BRANCH], check=False)
        run_command(["git", "branch", "-D", branch_name], check=False)
        log("Branch cleanup completed.")

    def extract_issue_number_from_branch(self, branch_name: str) -> Optional[int]:
        """Extracts the GitHub issue number from a branch name with format 'copilot/fix-<issue_number>'
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

    def get_latest_branch_by_pattern(self, pattern: str) -> Optional[str]:
        """Gets the latest branch matching a specific pattern, ignoring author information.

        This function is particularly useful for finding Claude-generated branches
        which follow a specific naming pattern regardless of the commit author.

        Args:
            pattern: The regex pattern to match branch names against

        Returns:
            Optional[str]: The latest matching branch name or None if no matches found
        """
        from src.utils import log
        from src.config import get_config
        import json
        config = get_config()

        debug_log(f"Finding latest branch matching pattern '{pattern}'")

        # Construct GraphQL query to get branches
        # Limit to 100 most recent branches, ordered by commit date descending
        graphql_query = """
        query($repo_owner: String!, $repo_name: String!) {
          repository(owner: $repo_owner, name: $repo_name) {
            refs(refPrefix: "refs/heads/", first: 100, orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
              nodes {
                name
                target {
                  ... on Commit {
                    committedDate
                  }
                }
              }
            }
          }
        }
        """

        try:
            repo_data = config.GITHUB_REPOSITORY.split('/')
            if len(repo_data) != 2:
                log(f"Invalid repository format: {config.GITHUB_REPOSITORY}", is_error=True)
                return None

            repo_owner, repo_name = repo_data

            from src.git_handler import get_gh_env
            gh_env = get_gh_env()
            latest_branch_command = [
                'gh', 'api', 'graphql',
                '-f', f'query={graphql_query}',
                '-f', f'repo_owner={repo_owner}',
                '-f', f'repo_name={repo_name}'
            ]
            result = run_command(latest_branch_command, env=gh_env, check=False)

            if not result:
                debug_log("Failed to get branches from GitHub GraphQL API")
                return None

            # Parse JSON response
            data = json.loads(result)
            branches = data.get('data', {}).get('repository', {}).get('refs', {}).get('nodes', [])

            # Compile regex pattern
            pattern_regex = re.compile(pattern)

            # Filter branches by pattern only (ignoring author)
            matching_branches = []
            for branch in branches:
                branch_name = branch.get('name')
                if not branch_name or not pattern_regex.match(branch_name):
                    continue

                # Always collect the committed date for sorting
                committed_date = branch.get('target', {}).get('committedDate')
                if committed_date:
                    matching_branches.append((branch_name, committed_date))

            # Sort by commit date in descending order (newest first)
            matching_branches.sort(key=lambda x: x[1], reverse=True)

            if matching_branches:
                latest_branch = matching_branches[0][0]
                debug_log(f"Found latest matching branch: {latest_branch}")
                return latest_branch
            else:
                debug_log(f"No branches found matching pattern '{pattern}'")
                return None

        except Exception as e:
            log(f"Error finding latest branch: {str(e)}", is_error=True)
            return None

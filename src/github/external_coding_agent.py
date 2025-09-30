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
import time
from typing import Optional
from src.utils import log, debug_log, error_exit, tail_string
from src.contrast_api import FailureCategory, notify_remediation_pr_opened
from src.config import Config
from src import git_handler
from src import telemetry_handler
from src.coding_agents import CodingAgents


class ExternalCodingAgent:
    """
    A class that interfaces with an external coding agent through an API or command line.
    This agent is used as an alternative to the built-in SmartFix coding agent.
    """

    def __init__(self, config: Config):
        """
        Initialize the ExternalCodingAgent with configuration settings.

        Args:
            config: The application configuration object
        """
        self.config = config
        debug_log("Initialized ExternalCodingAgent")

    def assemble_issue_body(self, vulnerability_details: dict) -> str:
        """
        Assembles a GitHub Issue body from vulnerability details.

        Args:
            vulnerability_details: Dictionary containing vulnerability information

        Returns:
            str: Formatted GitHub Issue body for the vulnerability
        """
        # Extract key details with safe fallbacks
        vuln_title = vulnerability_details.get('vulnerabilityTitle', 'Unknown Vulnerability')
        vuln_uuid = vulnerability_details.get('vulnerabilityUuid', 'Unknown UUID')
        vuln_rule = vulnerability_details.get('vulnerabilityRuleName', 'Unknown Rule')
        vuln_severity = vulnerability_details.get('vulnerabilitySeverity', 'Unknown Severity')
        vuln_status = vulnerability_details.get('vulnerabilityStatus', 'Unknown Status')

        # Get raw values first to check if they're empty
        raw_overview = vulnerability_details.get('vulnerabilityOverviewStory', '')
        raw_events = vulnerability_details.get('vulnerabilityEventsSummary', '')
        raw_http_details = vulnerability_details.get('vulnerabilityHttpRequestDetails', '')

        # Tail large fields to reasonable limits to prevent GitHub's 64k character limit (only if they have content)
        vuln_overview = tail_string(raw_overview, 8000) if raw_overview.strip() else None
        vuln_events = tail_string(raw_events, 20000) if raw_events.strip() else None
        vuln_http_details = tail_string(raw_http_details, 4000) if raw_http_details.strip() else None

        # Start building the issue body
        contrast_url = (f"https://{self.config.CONTRAST_HOST}/Contrast/static/ng/index.html#/"
                        f"{self.config.CONTRAST_ORG_ID}/applications/{self.config.CONTRAST_APP_ID}/vulns/{vuln_uuid}")

        issue_body = f"""
# Contrast AI SmartFix Issue Report

This issue should address a vulnerability identified by the Contrast Security platform (ID: [{vuln_uuid}]({contrast_url})).

# Security Vulnerability: {vuln_title}

## Vulnerability Details

**Rule:** {vuln_rule}
**Severity:** {vuln_severity}
**Status:** {vuln_status}  """

        # Add overview section only if content is available
        if vuln_overview:
            issue_body += f"""

## Overview

{vuln_overview}"""

        # Add technical details section only if we have event summary or HTTP details
        if vuln_events or vuln_http_details:
            issue_body += """

## Technical Details"""

            # Add event summary subsection only if content is available
            if vuln_events:
                issue_body += f"""

### Event Summary
```
{vuln_events}
```"""

            # Add HTTP request details subsection only if content is available
            if vuln_http_details:
                issue_body += f"""

### HTTP Request Details
```
{vuln_http_details}
```"""

        # Add the action required section
        issue_body += """

## Action Required

Please review this security vulnerability and implement appropriate fixes to address the identified issue.

**Important:** If you cannot find the vulnerability, then take no actions (corrective or otherwise). Simply report that the vulnerability was not found."""

        debug_log(f"Assembled issue body with {len(issue_body)} characters")
        return issue_body

    def generate_fixes(self, vuln_uuid: str, remediation_id: str, vuln_title: str, issue_body: str = None) -> bool:
        """
        Generate fixes for vulnerabilities.

        Args:
            vuln_uuid: The vulnerability UUID
            remediation_id: The remediation ID
            vuln_title: The vulnerability title
            issue_body: The issue body content (optional, uses default if not provided)

        Returns:
            bool: False if the CODING_AGENT is SMARTFIX, True otherwise
        """
        if hasattr(self.config, 'CODING_AGENT') and self.config.CODING_AGENT == CodingAgents.SMARTFIX.name:
            debug_log("SMARTFIX agent detected, ExternalCodingAgent.generate_fixes returning False")
            return False

        log(f"\n::group::--- Using External Coding Agent ({self.config.CODING_AGENT}) ---")
        telemetry_handler.update_telemetry("additionalAttributes.codingAgent", "EXTERNAL-COPILOT")

        # Generate labels and issue details
        vulnerability_label = f"contrast-vuln-id:VULN-{vuln_uuid}"
        remediation_label = f"smartfix-id:{remediation_id}"
        issue_title = vuln_title

        if self.config.CODING_AGENT == CodingAgents.CLAUDE_CODE.name:
            debug_log("CLAUDE_CODE agent detected, tagging @claude in issue title for processing")
            issue_title = f"@claude Fix: {issue_title}"

        # Use the provided issue_body or fall back to default
        if issue_body is None:
            log(f"Failed to generate issue body for vulnerability id {vuln_uuid}", is_error=True)
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        # Use git_handler to find if there's an existing issue with this label
        issue_number = git_handler.find_issue_with_label(vulnerability_label)

        is_existing_issue = False
        if issue_number is None:
            # Check if this is because Issues are disabled
            if not git_handler.check_issues_enabled():
                log("GitHub Issues are disabled for this repository. External coding agent requires Issues to be enabled.", is_error=True)
                error_exit(remediation_id, FailureCategory.GIT_COMMAND_FAILURE.value)

            debug_log(f"No GitHub issue found with label {vulnerability_label}")
            issue_number = git_handler.create_issue(issue_title, issue_body, vulnerability_label, remediation_label)
            if not issue_number:
                log(f"Failed to create issue with labels {vulnerability_label}, {remediation_label}", is_error=True)
                error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
        else:
            debug_log(f"Found existing GitHub issue #{issue_number} with label {vulnerability_label}")
            if not git_handler.reset_issue(issue_number, issue_title, remediation_label):
                log(f"Failed to reset issue #{issue_number} with labels {vulnerability_label}, {remediation_label}", is_error=True)
                error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
            is_existing_issue = True

        telemetry_handler.update_telemetry("additionalAttributes.externalIssueNumber", issue_number)

        # Proceed with PR polling for all agent types

        # Poll for PR creation by the external agent
        log(f"Waiting for external agent to create a PR for issue #{issue_number}, '{issue_title}'")

        # Poll for a PR to be created by the external agent (100 attempts, 5 seconds apart = ~8.3 minutes max)
        pr_info = self._process_external_coding_agent_run(
            issue_number, issue_title, remediation_id, vulnerability_label,
            remediation_label, is_existing_issue, max_attempts=100, sleep_seconds=5
        )

        log("\n::endgroup::")
        if pr_info:
            pr_number = pr_info.get("number")
            pr_url = pr_info.get("url")
            log(f"External agent created PR #{pr_number} at {pr_url}")
            telemetry_handler.update_telemetry("resultInfo.prCreated", True)
            telemetry_handler.update_telemetry("additionalAttributes.prStatus", "OPEN")
            telemetry_handler.update_telemetry("additionalAttributes.prNumber", pr_number)
            telemetry_handler.update_telemetry("additionalAttributes.prUrl", pr_url)
            return True
        else:
            log("External agent failed to create a PR within the timeout period", is_error=True)
            telemetry_handler.update_telemetry("resultInfo.prCreated", False)
            telemetry_handler.update_telemetry("resultInfo.failureReason", "PR creation timeout")
            telemetry_handler.update_telemetry("resultInfo.failureCategory", FailureCategory.AGENT_FAILURE.name)
            return False

    def _process_external_coding_agent_run(self, issue_number: int, issue_title: str, remediation_id: str, vulnerability_label: str,
                                           remediation_label: str, is_existing_issue: bool,
                                           max_attempts: int = 100, sleep_seconds: int = 5) -> Optional[dict]:
        """
        Poll for a PR to be created by the external agent.

        Args:
            issue_number: The issue number to check for a PR
            remediation_id: The remediation ID for telemetry and API notification
            vulnerability_label: The vulnerability label to add to the PR
            remediation_label: The remediation label to add to the PR
            is_existing_issue: Flag indicating if this is an existing issue being reprocessed
            max_attempts: Maximum number of polling attempts (default: 100)
            sleep_seconds: Time to sleep between attempts (default: 5 seconds)

        Returns:
            Optional[dict]: PR information if found, None if not found after max attempts
        """
        debug_log(f"Polling for PR creation for issue #{issue_number}, max {max_attempts} attempts with {sleep_seconds}s interval")

        for attempt in range(1, max_attempts + 1):
            debug_log(f"Polling attempt {attempt}/{max_attempts} for PR related to issue #{issue_number}")
            if self.config.CODING_AGENT == CodingAgents.CLAUDE_CODE.name:
                if is_existing_issue:
                    debug_log(f"Claude is going to reprocess exiting issue #{issue_number}.")
                    # Let's wait 25 seconds to ensure the claude workflow run has started
                    # This should ensure we get the latest comment and workflow run ID
                    time.sleep(25)
                pr_info = self._process_claude_workflow_run(issue_number, remediation_id)
            else:
                # GitHub Copilot agent
                pr_info = git_handler.find_open_pr_for_issue(issue_number, issue_title)

            if pr_info:
                pr_number = pr_info.get("number")
                pr_url = pr_info.get("url")

                # Add vulnerability and remediation labels to the PR
                labels_to_add = [vulnerability_label, remediation_label]
                if git_handler.add_labels_to_pr(pr_number, labels_to_add):
                    debug_log(f"Successfully added labels to PR #{pr_number}: {labels_to_add}")
                else:
                    log(f"Failed to add labels to PR #{pr_number}", is_error=True)
                    return None

                debug_log(f"Found PR #{pr_number} for issue #{issue_number} after {attempt} attempts")

                # Notify the Remediation backend about the PR
                success = notify_remediation_pr_opened(
                    remediation_id=remediation_id,
                    pr_number=pr_number,
                    pr_url=pr_url,
                    contrast_host=self.config.CONTRAST_HOST,
                    contrast_org_id=self.config.CONTRAST_ORG_ID,
                    contrast_app_id=self.config.CONTRAST_APP_ID,
                    contrast_auth_key=self.config.CONTRAST_AUTHORIZATION_KEY,
                    contrast_api_key=self.config.CONTRAST_API_KEY
                )

                if success:
                    log(f"Successfully notified remediation backend about PR #{pr_number}")
                else:
                    log(f"Failed to notify remediation backend about PR #{pr_number}", is_error=True)

                return pr_info

            # Sleep before the next attempt, but don't sleep after the last attempt
            if attempt < max_attempts:
                time.sleep(sleep_seconds)

        log(f"No PR found for issue #{issue_number} after {max_attempts} polling attempts", is_error=True)
        return None

    def _process_claude_workflow_run(self, issue_number: int, remediation_id: str,) -> Optional[dict]:
        """
        Process the Claude Code workflow run and extract PR information from Claude's comment
        and then create the PR using the claude produced information.

        Args:
            issue_number: The issue number Claude is working on
            remediation_id: The remediation ID for telemetry and API notification

        Returns:
            Optional[dict]: PR information if successfully created, None otherwise
        """
        try:
            # Check for Claude workflow run ID
            workflow_run_id = git_handler.get_claude_workflow_run_id()

            if not workflow_run_id:
                # If no workflow run ID found yet, continue polling
                debug_log("Claude workflow_run_id not found, checking again...")
                return None

            # Get all issue comments to find the latest comment author.login
            issue_comments = git_handler.get_issue_comments(issue_number)
            if not issue_comments or len(issue_comments) == 0:
                debug_log("No comments added to issue, checking again...")
                return None

            author_login = issue_comments[0].get("author", {}).get("login", '')
            debug_log(f"Found latest issue comment author login: {author_login}")

            # Watch the claude GitHub action run
            debug_log(f"OK, found claude workflow_run_id value: {workflow_run_id}")
            workflow_success = git_handler.watch_github_action_run(workflow_run_id)

            if not workflow_success:
                log(f"Claude workflow run #{workflow_run_id} failed for issue #{issue_number} terminating SmartFix run.", is_error=True)
                reason = f"Claude workflow run #{workflow_run_id} failed processing with non-zero exit status"
                self._update_telemetry_and_exit_claude_agent_failure(reason, remediation_id, issue_number)

            # Get the issue comments to find the comment author's response to create the PR [default claude]
            author_login = author_login if author_login else "claude"
            claude_comments = git_handler.get_issue_comments(issue_number, author_login)

            if not claude_comments or len(claude_comments) == 0:
                msg = f"No Claude comments found for issue #{issue_number}."
                log(msg, is_error=True)
                self._update_telemetry_and_exit_claude_agent_failure(msg, remediation_id, issue_number)

            # Parse the most recent comment body to extract PR info
            full_comment_body = claude_comments[0].get('body', '')

            # Truncate the comment body to focus only on the header section before the markdown separator
            # This makes regex pattern matching more reliable and efficient
            truncated_comment_body = full_comment_body.split('\n\n---\n')[0] if '\n\n---\n' in full_comment_body else full_comment_body

            # Extract PR information from the comment body
            comment_body_pr_data = self._process_claude_comment_body(truncated_comment_body, remediation_id, issue_number)
            head_branch_from_url = comment_body_pr_data["head_branch_from_url"]
            pr_title = comment_body_pr_data["pr_title"]
            pr_body = comment_body_pr_data["pr_body"]

            # Attempt to get the branch name using multiple methods in order of preference
            head_branch = self._get_claude_head_branch(head_branch_from_url, full_comment_body, issue_number, remediation_id)

            # Create PR using extracted information
            base_branch = self.config.BASE_BRANCH
            pr_url = git_handler.create_claude_pr(
                title=pr_title,
                body=pr_body,
                base_branch=base_branch,
                head_branch=head_branch
            )
            debug_log(f"Claude create PR returned url: {pr_url}")

            if not pr_url:
                log("Failed to create PR for Claude Code fix", is_error=True)
                reason = "Could not create Claude PR due to processing issues"
                self._update_telemetry_and_exit_claude_agent_failure(reason, remediation_id, issue_number)

            # Extract PR number from URL
            pr_number_match = re.search(r'/pull/(\d+)$', pr_url)
            if not pr_number_match:
                msg = f"Could not extract PR number from URL: {pr_url}"
                log(msg, is_error=True)
                self._update_telemetry_and_exit_claude_agent_failure(msg, remediation_id, issue_number)

            pr_number = int(pr_number_match.group(1))

            # Create PR info object similar to what find_open_pr_for_issue returns
            pr_info = {
                "number": pr_number,
                "url": pr_url,
                "title": pr_title,
                "headRefName": head_branch,
                "baseRefName": base_branch,
                "state": "OPEN"
            }

            log(f"Successfully created PR #{pr_number} for Claude Code fix")
            return pr_info

        except Exception as e:
            msg = f"Error processing Claude external agent run : {str(e)}"
            log(msg, is_error=True)
            self._update_telemetry_and_exit_claude_agent_failure(msg, remediation_id, issue_number)
            return None

    def _process_claude_comment_body(self, comment_body: str, remediation_id: str, issue_number: int) -> dict:  # noqa: C901
        """
        Process Claude's comment body to extract PR information. Returning the pr_title
        and pr_body are required for this method to be successful and to create the PR.

        Args:
            comment_body: The truncated comment body from Claude
            remediation_id: The remediation ID for telemetry and error handling
            issue_number: The issue number Claude is working on

        Returns:
            dict: A dictionary containing head_branch_from_url, pr_title, and pr_body
        """
        import urllib.parse

        # Extract head branch from backticks inside square brackets (most reliable method)
        head_branch_from_url = None
        branch_match = re.search(fr'\[`(claude/issue-{issue_number}-\d{{8}}-\d{{4}})`\]', comment_body)
        if branch_match:
            head_branch_from_url = branch_match.group(1)
            debug_log(f"Found branch name from backticks: {head_branch_from_url}")

        # Find the URL starting with "Create PR" English support only atm
        start_marker = '[Create PR ➔]('
        pr_title = ''
        pr_body = ''

        if start_marker in comment_body:
            start_idx = comment_body.find(start_marker) + len(start_marker)

            # Find matching closing parenthesis with proper nesting handling
            paren_count = 0
            end_idx = -1
            for i in range(start_idx, len(comment_body)):
                if comment_body[i] == '(':
                    paren_count += 1
                elif comment_body[i] == ')':
                    if paren_count == 0:
                        end_idx = i
                        break
                    paren_count -= 1

            if end_idx > start_idx:
                create_pr_url = comment_body[start_idx:end_idx]
                debug_log(f"Found PR URL: {create_pr_url}...")

                # If no branch yet, extract it from URL
                if not head_branch_from_url and '...' in create_pr_url:
                    url_parts = create_pr_url.split('...')
                    if len(url_parts) > 1:
                        branch_part = url_parts[1]
                        if '?' in branch_part:
                            head_branch_from_url = branch_part.split('?')[0]
                        else:
                            head_branch_from_url = branch_part
                        debug_log(f"Found branch name from URL: {head_branch_from_url}")

                # Extract query params for title and body
                params = {}
                if '?' in create_pr_url:
                    query = create_pr_url.split('?', 1)[1]
                    param_pairs = query.split('&')
                    for pair in param_pairs:
                        if '=' in pair:
                            key, value = pair.split('=', 1)
                            params[key] = urllib.parse.unquote(value)

                    debug_log(f"Found {len(params)} URL parameters: {', '.join(params.keys())}")

                    # Extract title and body
                    pr_title = params.get('title', '')
                    if pr_title:
                        debug_log(f"Found PR title: {pr_title}")
                    else:
                        debug_log("Could not extract PR title from URL parameters")

                    pr_body = params.get('body', '')
                    if pr_body:
                        debug_log(f"Found PR body: {pr_body}")
                    else:
                        debug_log("Could not extract PR body from URL parameters")

        # Final fallback for finding branch - search for compare URL pattern
        if not head_branch_from_url and '/compare/' in comment_body:
            compare_match = re.search(r'/compare/[^.]+\.\.\.([^?)\s]+)', comment_body)
            if compare_match:
                head_branch_from_url = compare_match.group(1)
                debug_log(f"Found branch name using fallback: {head_branch_from_url}")

        # Verify we have required pr_title and pr_body data
        if not (pr_title and pr_body):
            error_msg = f"Could not extract required PR title and body data from comment_body: {comment_body}"
            debug_log(error_msg, is_error=True)
            self._update_telemetry_and_exit_claude_agent_failure(error_msg, remediation_id, issue_number)

        contrast_pr_body = f"{pr_body}\n Powered by Contrast AI SmartFix"
        return {
            "head_branch_from_url": head_branch_from_url,
            "pr_title": pr_title,
            "pr_body": contrast_pr_body
        }

    def _get_claude_head_branch(self, head_branch_from_url: str,
                                comment_body: str,
                                issue_number: int,
                                remediation_id: str) -> str:
        """
        Get Claude's head branch that was created during the workflow run so a
        PR can be created.

        Args:
            head_branch_from_url: the possible head_branch extracted from the URL in the comment body
            comment_body: The full comment body from Claude
            remediation_id: The remediation ID for telemetry and error handling
            issue_number: The issue number Claude is working on

        Returns:
            str: A String containing head_branch that the claude code workflow created
        """
        # Attempt to get the branch name using multiple methods in order of preference
        head_branch = None

        # Method 1: Try to use the branch name extracted from URL in comment body
        if head_branch_from_url:
            head_branch = head_branch_from_url
            debug_log(f"Using head branch extracted from URL: {head_branch}")
            return head_branch

        # Method 2: Try to extract from backtick-formatted branch in comment
        if not head_branch:
            # Look for the branch name in backtick format inside square brackets in the comment
            branch_match = re.search(fr'\[`(claude/issue-{issue_number}-\d{{8}}-\d{{4}})`\]', comment_body)

            if branch_match:
                head_branch = branch_match.group(1)
                debug_log(f"Using head branch from backtick format match in comment: {head_branch}")

        # Method 3: Use the API to get the latest branch by pattern if all else fails
        if not head_branch:
            # Pattern to match claude/issue-NUMBER-YYYYMMDD-HHMM format
            pattern = fr'^claude/issue-{issue_number}-\d{{8}}-\d{{4}}$'
            debug_log(f"Falling back to GraphQL API call method with pattern: {pattern}")
            head_branch = git_handler.get_latest_branch_by_pattern(pattern)

            if head_branch:
                debug_log(f"Using head branch from GitHub GraphQl API call: {head_branch}")

        # Final check - if no branch could be found by any method, fail gracefully
        if not head_branch:
            log("Could not determine claude branch name using any available method", is_error=True)
            reason = "Could not extract Claude head_branch needed for PR creation"
            self._update_telemetry_and_exit_claude_agent_failure(reason, remediation_id, issue_number)

        return head_branch

    def _update_telemetry_and_exit_claude_agent_failure(self, reason: str, remediation_id: str, issue_number: int):
        """
        Update telemetry for a Claude Code agent failure and exit.

        Args:
            reason: The reason for the failure
            remediation_id: The remediation ID for telemetry and error handling
            issue_number: The issue number Claude is working on
        """
        log(f"Claude Code agent failure for issue #{issue_number}: {reason}", is_error=True)
        telemetry_handler.update_telemetry("resultInfo.prCreated", False)
        telemetry_handler.update_telemetry("resultInfo.issueNumber", issue_number)
        telemetry_handler.update_telemetry("resultInfo.failureReason", reason)
        telemetry_handler.update_telemetry("resultInfo.failureCategory", FailureCategory.AGENT_FAILURE.name)
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    # Additional methods will be implemented later

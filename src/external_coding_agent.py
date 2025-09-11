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

import time
from typing import Optional
from src.utils import log, debug_log, error_exit, tail_string
from src.contrast_api import FailureCategory, notify_remediation_pr_opened
from src.config import Config
from src import git_handler
from src import telemetry_handler
from src.coding_agents import CodingAgents


@PendingDeprecationWarning
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
            issue_title = f"@claude fix: {issue_title}"

        # Use the provided issue_body or fall back to default
        if issue_body is None:
            log(f"Failed to generate issue body for vulnerability id {vuln_uuid}", is_error=True)
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        # Use git_handler to find if there's an existing issue with this label
        issue_number = git_handler.find_issue_with_label(vulnerability_label)

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
            if not git_handler.reset_issue(issue_number, remediation_label):
                log(f"Failed to reset issue #{issue_number} with labels {vulnerability_label}, {remediation_label}", is_error=True)
                error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        telemetry_handler.update_telemetry("additionalAttributes.externalIssueNumber", issue_number)

        if self.config.CODING_AGENT == CodingAgents.CLAUDE_CODE.name:
            # temporary short-circuit for Claude until we implement the PR processing logic
            log("Claude agent processing support is not implemented as of yet so stop processing and log agent failure", is_error=True)
            telemetry_handler.update_telemetry("resultInfo.prCreated", False)
            telemetry_handler.update_telemetry("resultInfo.failureReason", "Claude processing not implemented")
            telemetry_handler.update_telemetry("resultInfo.failureCategory", FailureCategory.AGENT_FAILURE.name)
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        # Poll for PR creation by the external agent
        log(f"Waiting for external agent to create a PR for issue #{issue_number}")

        # Poll for a PR to be created by the external agent (100 attempts, 5 seconds apart = ~8.3 minutes max)
        pr_info = self._poll_for_pr(issue_number, remediation_id, vulnerability_label, remediation_label, max_attempts=100, sleep_seconds=5)

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

    def _poll_for_pr(self, issue_number: int, remediation_id: str, vulnerability_label: str,
                     remediation_label: str, max_attempts: int = 100, sleep_seconds: int = 5) -> Optional[dict]:
        """
        Poll for a PR to be created by the external agent.

        Args:
            issue_number: The issue number to check for a PR
            remediation_id: The remediation ID for telemetry and API notification
            max_attempts: Maximum number of polling attempts (default: 100)
            sleep_seconds: Time to sleep between attempts (default: 5 seconds)

        Returns:
            Optional[dict]: PR information if found, None if not found after max attempts
        """
        debug_log(f"Polling for PR creation for issue #{issue_number}, max {max_attempts} attempts with {sleep_seconds}s interval")

        for attempt in range(1, max_attempts + 1):
            debug_log(f"Polling attempt {attempt}/{max_attempts} for PR related to issue #{issue_number}")

            pr_info = git_handler.find_open_pr_for_issue(issue_number)

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

    # Additional methods will be implemented later

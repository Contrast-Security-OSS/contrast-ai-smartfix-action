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

import atexit
import os
import json
import sys

# Import from src package to ensure correct module resolution
from src import contrast_api
from src.config import get_config  # Using get_config function instead of direct import
from src.utils import debug_log, extract_remediation_id_from_branch, extract_remediation_id_from_labels, log
from src.github.github_operations import GitHubOperations
from src.smartfix.domains.telemetry import otel_provider, telemetry_handler


def _load_github_event() -> dict:
    """Load and parse the GitHub event data."""
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        log("Error: GITHUB_EVENT_PATH not set. Cannot process PR event.", is_error=True)
        sys.exit(1)

    try:
        with open(event_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        log(f"Error reading or parsing GITHUB_EVENT_PATH file: {e}", is_error=True)
        sys.exit(1)


def _validate_pr_event(event_data: dict) -> dict:
    """Validate the PR event and return PR data."""
    if event_data.get("action") != "closed":
        log("PR action is not 'closed'. Skipping.")
        sys.exit(0)

    pull_request = event_data.get("pull_request", {})
    if not pull_request.get("merged"):
        log("PR was closed but not merged. Skipping.")
        sys.exit(0)

    debug_log("Pull request was merged.")
    return pull_request


def _extract_remediation_info(pull_request: dict) -> tuple:
    """Extract remediation ID and other info from PR data."""
    branch_name = pull_request.get("head", {}).get("ref")
    if not branch_name:
        log("Error: Could not determine branch name from PR.", is_error=True)
        sys.exit(1)

    debug_log(f"Branch name: {branch_name}")
    labels = pull_request.get("labels", [])

    # Determine coding agent from branch prefix (independent of remediation ID extraction)
    if branch_name.startswith("claude/issue-"):
        coding_agent = "EXTERNAL-CLAUDE_CODE"
        github_ops = GitHubOperations()
        issue_number = github_ops.extract_issue_number_from_branch(branch_name)
        if issue_number:
            telemetry_handler.update_telemetry("additionalAttributes.externalIssueNumber", issue_number)
            debug_log(f"Extracted external issue number from branch name: {issue_number}")
        else:
            debug_log(f"Could not extract issue number from branch name: {branch_name}")
    elif branch_name.startswith("copilot/fix"):
        coding_agent = "EXTERNAL-GITHUB_COPILOT"
        github_ops = GitHubOperations()
        issue_number = github_ops.extract_issue_number_from_branch(branch_name)
        if issue_number:
            telemetry_handler.update_telemetry("additionalAttributes.externalIssueNumber", issue_number)
            debug_log(f"Extracted external issue number from branch name: {issue_number}")
        else:
            debug_log(f"Could not extract issue number from branch name: {branch_name}")
    else:
        coding_agent = "INTERNAL-SMARTFIX"
    debug_log(f"Determined coding agent to be: {coding_agent}")
    telemetry_handler.update_telemetry("additionalAttributes.codingAgent", coding_agent)

    # Extract remediation ID: (1) smartfix-id: label, (2) branch name fallback
    remediation_id = extract_remediation_id_from_labels(labels)
    if remediation_id:
        debug_log(f"Extracted remediation ID from smartfix-id label: {remediation_id}")
    else:
        remediation_id = extract_remediation_id_from_branch(branch_name)
        if remediation_id:
            debug_log(f"Extracted remediation ID from branch name: {remediation_id}")

    if not remediation_id:
        log(f"Error: Could not extract remediation ID from labels or branch name: {branch_name}", is_error=True)
        sys.exit(1)

    return remediation_id, labels


def _extract_vulnerability_info(labels: list) -> str:
    """Extract vulnerability UUID from PR labels."""
    vuln_uuid = "unknown"

    for label in labels:
        label_name = label.get("name", "")
        if label_name.startswith("contrast-vuln-id:VULN-"):
            # Extract UUID from label format "contrast-vuln-id:VULN-{vuln_uuid}"
            label_name_parts = label_name.split("VULN-")
            vuln_uuid = label_name_parts[1] if len(label_name_parts) > 1 else "unknown"
            if vuln_uuid and vuln_uuid != "unknown":
                debug_log(f"Extracted Vulnerability UUID from PR label: {vuln_uuid}")
                break

    if vuln_uuid == "unknown":
        debug_log("Could not extract vulnerability UUID from PR labels. Telemetry may be incomplete.")

    return vuln_uuid


def _notify_remediation_service(remediation_id: str):
    """Notify the Remediation backend service about the merged PR."""
    log(f"Notifying Remediation service about merged PR for remediation {remediation_id}...")
    config = get_config()
    remediation_notified = contrast_api.notify_remediation_pr_merged_org(
        remediation_id=remediation_id,
        contrast_host=config.CONTRAST_HOST,
        contrast_org_id=config.CONTRAST_ORG_ID,
        contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
        contrast_api_key=config.CONTRAST_API_KEY
    )

    if remediation_notified:
        log(f"Successfully notified Remediation service about merged PR for remediation {remediation_id}.")
    else:
        log(f"Failed to notify Remediation service about merged PR for remediation {remediation_id}.", is_error=True)


def _cleanup_smartfix_labels(pull_request: dict, labels: list) -> None:
    """Best-effort: remove SmartFix-managed labels from the PR (and linked issue
    in the external-agent flow). Never raises — failures are logged and the
    handler completes regardless."""
    try:
        pr_number = pull_request.get("number")
        if not pr_number:
            debug_log("No PR number in event payload; skipping label cleanup.")
            return

        github_ops = GitHubOperations()
        smartfix_labels = github_ops.filter_smartfix_labels(labels)
        if not smartfix_labels:
            debug_log("No SmartFix labels on PR; skipping label cleanup.")
            return

        debug_log(f"Cleaning up SmartFix labels: {smartfix_labels}")
        github_ops.remove_labels_from_pr(pr_number, smartfix_labels)

        branch_name = pull_request.get("head", {}).get("ref") or ""
        if branch_name.startswith(("claude/issue-", "copilot/fix")):
            issue_number = github_ops.extract_issue_number_from_branch(branch_name)
            if issue_number:
                github_ops.remove_labels_from_issue(issue_number, smartfix_labels)
    except Exception as e:
        log(f"Best-effort SmartFix label cleanup raised: {e}", is_error=True)


def handle_merged_pr():
    """Handles the logic when a pull request is merged."""
    config = get_config()
    telemetry_handler.initialize_telemetry()
    otel_provider.initialize_otel(config)
    # atexit guard ensures flush even when sys.exit() is called deep in a
    # helper.  The explicit finally below handles normal flow; shutdown_otel
    # is idempotent (guarded by _shutdown_called) so double-calling is safe.
    atexit.register(otel_provider.shutdown_otel)

    log("--- Handling Merged Contrast AI SmartFix Pull Request ---")

    # Load and validate event before starting the span so non-merge events
    # don't produce a smartfix-merge span with pr_merged=true.
    event_data = _load_github_event()
    pull_request = _validate_pr_event(event_data)

    try:
        with otel_provider.start_span("smartfix-merge") as merge_span:
            merge_span.set_attribute("contrast.smartfix.pr_merged", True)

            # Extract remediation and vulnerability information
            remediation_id, labels = _extract_remediation_info(pull_request)
            vuln_uuid = _extract_vulnerability_info(labels)

            merge_span.set_attribute("contrast.smartfix.remediation_id", remediation_id)
            merge_span.set_attribute("contrast.finding.fingerprint", vuln_uuid)

            # Update telemetry with extracted information
            debug_log(f"Extracted Remediation ID: {remediation_id}")
            telemetry_handler.update_telemetry("additionalAttributes.remediationId", remediation_id)
            telemetry_handler.update_telemetry("vulnInfo.vulnId", vuln_uuid)
            telemetry_handler.update_telemetry("vulnInfo.vulnRule", "unknown")

            # Notify the Remediation backend service
            _notify_remediation_service(remediation_id)

            # Complete telemetry and finish
            telemetry_handler.update_telemetry("additionalAttributes.prStatus", "MERGED")
            contrast_api.send_telemetry_data_org(
                remediation_id=remediation_id,
                telemetry_data=telemetry_handler.get_telemetry_data(),
                contrast_host=config.CONTRAST_HOST,
                contrast_org_id=config.CONTRAST_ORG_ID,
                contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                contrast_api_key=config.CONTRAST_API_KEY
            )

            _cleanup_smartfix_labels(pull_request, labels)
    finally:
        otel_provider.shutdown_otel()

    log("--- Merged Contrast AI SmartFix Pull Request Handling Complete ---")


if __name__ == "__main__":
    handle_merged_pr()

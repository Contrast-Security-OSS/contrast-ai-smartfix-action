#-
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
import sys

# Import from src package to ensure correct module resolution
from src import contrast_api
from src.config import get_config  # Using get_config function instead of direct import
from src.utils import debug_log, extract_remediation_id_from_branch, log
import src.telemetry_handler as telemetry_handler

def handle_merged_pr():
    """Handles the logic when a pull request is merged."""
    telemetry_handler.initialize_telemetry()

    log("--- Handling Merged Contrast AI SmartFix Pull Request ---")

    # Get PR event details from environment variables set by GitHub Actions
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        log("Error: GITHUB_EVENT_PATH not set. Cannot process PR event.", is_error=True)
        sys.exit(1)

    try:
        with open(event_path, 'r') as f:
            event_data = json.load(f)
    except Exception as e:
        log(f"Error reading or parsing GITHUB_EVENT_PATH file: {e}", is_error=True)
        sys.exit(1)

    if event_data.get("action") != "closed":
        log("PR action is not 'closed'. Skipping.")
        sys.exit(0)

    pull_request = event_data.get("pull_request", {})
    if not pull_request.get("merged"):
        log("PR was closed but not merged. Skipping.")
        sys.exit(0)

    debug_log("Pull request was merged.")

    # Get the branch name from the PR
    branch_name = pull_request.get("head", {}).get("ref")
    if not branch_name:
        log("Error: Could not determine branch name from PR.", is_error=True)
        sys.exit(1)
    
    debug_log(f"Branch name: {branch_name}")

    # Extract remediation ID from branch name or PR labels
    remediation_id = None
    
    # Check if this is a branch created by external agent (e.g., GitHub Copilot)
    if branch_name.startswith("copilot/fix"):
        debug_log("Branch appears to be created by external agent. Extracting remediation ID from PR labels.")
        # Get labels from the PR
        labels = pull_request.get("labels", [])
        remediation_id = extract_remediation_id_from_labels(labels)
    else:
        # Use original method for branches created by SmartFix
        remediation_id = extract_remediation_id_from_branch(branch_name)
    
    if not remediation_id:
        if branch_name.startswith("copilot/fix"):
            log(f"Error: Could not extract remediation ID from PR labels for external agent branch: {branch_name}", is_error=True)
        else:
            log(f"Error: Could not extract remediation ID from branch name: {branch_name}", is_error=True)
        # If we can't find the remediation ID, we can't proceed with the new approach
        sys.exit(1)
    
    debug_log(f"Extracted Remediation ID: {remediation_id}")
    telemetry_handler.update_telemetry("additionalAttributes.remediationId", remediation_id)
    
    # Try to extract vulnerability UUID from PR labels
    labels = pull_request.get("labels", [])
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
    telemetry_handler.update_telemetry("vulnInfo.vulnId", vuln_uuid)
    telemetry_handler.update_telemetry("vulnInfo.vulnRule", "unknown")
    
    if vuln_uuid == "unknown":
        debug_log("Could not extract vulnerability UUID from PR labels. Telemetry may be incomplete.")

    
    # Notify the Remediation backend service about the merged PR
    log(f"Notifying Remediation service about merged PR for remediation {remediation_id}...")
    # Get config instance using the canonical OO approach
    config = get_config()
    remediation_notified = contrast_api.notify_remediation_pr_merged(
        remediation_id=remediation_id,
        contrast_host=config.CONTRAST_HOST,
        contrast_org_id=config.CONTRAST_ORG_ID,
        contrast_app_id=config.CONTRAST_APP_ID,
        contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
        contrast_api_key=config.CONTRAST_API_KEY
    )
    
    if remediation_notified:
        log(f"Successfully notified Remediation service about merged PR for remediation {remediation_id}.")
    else:
        log(f"Failed to notify Remediation service about merged PR for remediation {remediation_id}.", is_error=True)

    telemetry_handler.update_telemetry("additionalAttributes.prStatus", "MERGED")
    contrast_api.send_telemetry_data()

    log("--- Merged Contrast AI SmartFix Pull Request Handling Complete ---")

if __name__ == "__main__":
    handle_merged_pr()

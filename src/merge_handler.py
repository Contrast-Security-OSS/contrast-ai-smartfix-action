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
import re
from typing import Optional

# Assuming contrast_api.py is in the same directory or PYTHONPATH is set up
import contrast_api
import config # To access Contrast API credentials and other configs
from utils import debug_log, extract_remediation_id_from_branch, log
import telemetry_handler

# Keep this function for backward compatibility with existing PRs
def get_vuln_uuid_from_labels(labels_json_str: str) -> Optional[str]:
    """Extracts the vulnerability UUID from a JSON string of PR labels."""
    try:
        labels = json.loads(labels_json_str)
        for label in labels:
            if isinstance(label, dict) and label.get("name", "").startswith("contrast-vuln-id:VULN-"):
                return label["name"].split("contrast-vuln-id:VULN-", 1)[1]
    except json.JSONDecodeError:
        log(f"Error: Could not decode labels JSON: {labels_json_str}", is_error=True)
        sys.exit(1)
    except Exception as e:
        log(f"Error processing labels: {e}", is_error=True)
        sys.exit(1)
    return None

def handle_merged_pr():
    """Handles the logic when a pull request is merged."""
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

    # Extract remediation ID from branch name
    remediation_id = extract_remediation_id_from_branch(branch_name)
    
    if not remediation_id:
        log(f"Error: Could not extract remediation ID from branch name: {branch_name}", is_error=True)
        # If we can't find the remediation ID, we can't proceed with the new approach
        sys.exit(1)
    
    debug_log(f"Extracted Remediation ID: {remediation_id}")
    telemetry_handler.update_telemetry("additionalAttributes.remediationId", remediation_id)

    config.check_contrast_config_values_exist()
    
    # Notify the Remediation backend service about the merged PR
    log(f"Notifying Remediation service about merged PR for remediation {remediation_id}...")
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
        log(f"Warning: Failed to notify Remediation service about merged PR for remediation {remediation_id}.", is_error=True)

    log("--- Merged Contrast AI SmartFix Pull Request Handling Complete ---")

if __name__ == "__main__":
    handle_merged_pr()

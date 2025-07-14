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

# Add project root to Python path to allow absolute imports when run as script
import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import using absolute imports
from src import contrast_api
from src.config_compat import CONTRAST_HOST, CONTRAST_ORG_ID, CONTRAST_APP_ID, CONTRAST_AUTHORIZATION_KEY, CONTRAST_API_KEY
from src.utils import debug_log, extract_remediation_id_from_branch, log
import src.telemetry_handler as telemetry_handler

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

    # Config values already checked through config_compat
    
    # Notify the Remediation backend service about the merged PR
    log(f"Notifying Remediation service about merged PR for remediation {remediation_id}...")
    remediation_notified = contrast_api.notify_remediation_pr_merged(
        remediation_id=remediation_id,
        contrast_host=CONTRAST_HOST,
        contrast_org_id=CONTRAST_ORG_ID,
        contrast_app_id=CONTRAST_APP_ID,
        contrast_auth_key=CONTRAST_AUTHORIZATION_KEY,
        contrast_api_key=CONTRAST_API_KEY
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

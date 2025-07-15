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
import sys

# Add project root to Python path to allow absolute imports when run as script
import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import using absolute imports
from src.config_compat import CONTRAST_HOST, CONTRAST_ORG_ID, CONTRAST_APP_ID, CONTRAST_AUTHORIZATION_KEY, CONTRAST_API_KEY, USER_AGENT, ENABLE_FULL_TELEMETRY
from src.utils import debug_log, extract_remediation_id_from_branch, log
import src.telemetry_handler as telemetry_handler
from src.api.contrast_api_client import ContrastApiClient
from src.telemetry.telemetry_handler import TelemetryHandler

def handle_closed_pr():
    """Handles the logic when a pull request is closed without merging."""
    log("--- Handling Closed (Unmerged) Contrast AI SmartFix Pull Request ---")

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
    if pull_request.get("merged"):
        log("PR was merged. Should be handled by merge_handler.py. Skipping.")
        sys.exit(0)

    debug_log("Pull request was closed without merging.")

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
        # If we can't find the remediation ID, we can't proceed
        sys.exit(1)
    
    debug_log(f"Extracted Remediation ID: {remediation_id}")
    telemetry_handler_obj.update_telemetry("additionalAttributes.remediationId", remediation_id)
    # For backward compatibility
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
    telemetry_handler_obj.update_telemetry("vulnInfo.vulnId", vuln_uuid)
    telemetry_handler_obj.update_telemetry("vulnInfo.vulnRule", "unknown")
    # For backward compatibility
    telemetry_handler.update_telemetry("vulnInfo.vulnId", vuln_uuid)
    telemetry_handler.update_telemetry("vulnInfo.vulnRule", "unknown")
    
    if vuln_uuid == "unknown":
        debug_log("Could not extract vulnerability UUID from PR labels. Telemetry may be incomplete.")

    # Config values already checked through config_compat
    
    # Create ContrastApiClient
    contrast_client = ContrastApiClient(
        host=CONTRAST_HOST,
        org_id=CONTRAST_ORG_ID,
        app_id=CONTRAST_APP_ID,
        auth_key=CONTRAST_AUTHORIZATION_KEY,
        api_key=CONTRAST_API_KEY,
        user_agent=USER_AGENT
    )
    
    # Initialize the TelemetryHandler
    telemetry_handler_obj = TelemetryHandler(
        contrast_api_client=contrast_client,
        enable_full_telemetry=ENABLE_FULL_TELEMETRY
    )
    
    # Notify the Remediation backend service about the closed PR
    log(f"Notifying Remediation service about closed PR for remediation {remediation_id}...")
    remediation_notified = contrast_client.notify_remediation_pr_closed(
        remediation_id=remediation_id
    )
    
    if remediation_notified:
        log(f"Successfully notified Remediation service about closed PR for remediation {remediation_id}.")
    else:
        log(f"Failed to notify Remediation service about closed PR for remediation {remediation_id}.", is_error=True)

    telemetry_handler_obj.update_telemetry("additionalAttributes.prStatus", "CLOSED")
    # For backward compatibility
    telemetry_handler.update_telemetry("additionalAttributes.prStatus", "CLOSED")
    # Send telemetry using the telemetry handler
    telemetry_handler_obj.send_telemetry_data()
    
    log("--- Closed Contrast AI SmartFix Pull Request Handling Complete ---")

if __name__ == "__main__":
    handle_closed_pr()

# %%
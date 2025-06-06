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
from typing import Optional

# Assuming contrast_api.py is in the same directory or PYTHONPATH is set up
import contrast_api
import config # To access Contrast API credentials and other configs
from utils import debug_print

def get_vuln_uuid_from_labels(labels_json_str: str) -> Optional[str]:
    """Extracts the vulnerability UUID from a JSON string of PR labels."""
    try:
        labels = json.loads(labels_json_str)
        for label in labels:
            if isinstance(label, dict) and label.get("name", "").startswith("contrast-vuln-id:VULN-"):
                return label["name"].split("contrast-vuln-id:VULN-", 1)[1]
    except json.JSONDecodeError:
        print(f"Error: Could not decode labels JSON: {labels_json_str}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error processing labels: {e}", file=sys.stderr)
        sys.exit(1)
    return None

def handle_merged_pr():
    """Handles the logic when a pull request is merged."""
    print("--- Handling Merged Contrast AI SmartFix Pull Request ---")

    # Get PR event details from environment variables set by GitHub Actions
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        print("Error: GITHUB_EVENT_PATH not set. Cannot process PR event.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(event_path, 'r') as f:
            event_data = json.load(f)
    except Exception as e:
        print(f"Error reading or parsing GITHUB_EVENT_PATH file: {e}", file=sys.stderr)
        sys.exit(1)

    if event_data.get("action") != "closed":
        print("PR action is not 'closed'. Skipping.")
        sys.exit(0)

    pull_request = event_data.get("pull_request", {})
    if not pull_request.get("merged"):
        print("PR was closed but not merged. Skipping.")
        sys.exit(0)

    debug_print("Pull request was merged.")

    pr_url = pull_request.get("html_url")
    if not pr_url:
        print("Error: Could not determine PR URL.", file=sys.stderr)
        # Continue if possible, as we might still get the UUID
        # sys.exit(1) # Or decide to exit if PR URL is critical

    # Labels are part of the pull_request object in the event payload
    labels = pull_request.get("labels", [])
    labels_json_str = json.dumps(labels) # Convert list of label objects to JSON string for existing function
    
    vuln_uuid = get_vuln_uuid_from_labels(labels_json_str)

    if not vuln_uuid:
        print("Error: Could not extract vulnerability UUID from PR labels. Cannot send note to Contrast.", file=sys.stderr)
        sys.exit(1) # Exit if we can't identify the vulnerability

    debug_print(f"Extracted Vulnerability UUID: {vuln_uuid}")
    
    if not config.SKIP_COMMENTS:
        note_content = f"Contrast AI SmartFix merged remediation PR: {pr_url if pr_url else 'Unknown URL'}"
        
        # Ensure all necessary config values are loaded/available
        # These would typically be set as environment variables in the GitHub Actions workflow
        # and loaded by the config.py module.
        
        # Check for essential Contrast configuration
        if not all([config.CONTRAST_HOST, config.CONTRAST_ORG_ID, config.CONTRAST_APP_ID, config.CONTRAST_AUTHORIZATION_KEY, config.CONTRAST_API_KEY]):
            print("Error: Missing one or more Contrast API configuration variables (HOST, ORG_ID, APP_ID, AUTH_KEY, API_KEY).", file=sys.stderr)
            sys.exit(1)

        print(f"Sending note to Contrast for vulnerability {vuln_uuid}...")
        note_added = contrast_api.add_note_to_vulnerability(
            vuln_uuid=vuln_uuid,
            note_content=note_content,
            contrast_host=config.CONTRAST_HOST,
            contrast_org_id=config.CONTRAST_ORG_ID,
            contrast_app_id=config.CONTRAST_APP_ID,
            contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
            contrast_api_key=config.CONTRAST_API_KEY
        )

        if note_added:
            debug_print(f"Successfully added 'merged' note to Contrast for vulnerability {vuln_uuid}.")
        else:
            print(f"Warning: Failed to add 'merged' note to Contrast for vulnerability {vuln_uuid}.")
            # Decide if this should be a failing condition for the action

        # Set vulnerability status to Remediated
        print(f"Setting status to 'Remediated' for vulnerability {vuln_uuid}...")
        status_set = contrast_api.set_vulnerability_status(
            vuln_uuid=vuln_uuid,
            status="Remediated",
            contrast_host=config.CONTRAST_HOST,
            contrast_org_id=config.CONTRAST_ORG_ID,
            contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
            contrast_api_key=config.CONTRAST_API_KEY,
            pr_url=pr_url
        )

        if status_set:
            debug_print(f"Successfully set status to 'Remediated' for vulnerability {vuln_uuid}.")
        else:
            print(f"Warning: Failed to set status to 'Remediated' for vulnerability {vuln_uuid}.", file=sys.stderr)
            # Optionally, decide if this should be a failing condition for the action
            # sys.exit(1)
    else:
        print("Skipping adding comment and setting status to 'Remediated' due to SKIP_COMMENTS setting.")

    # Tag vulnerability as "SmartFix Remediated"
    tag_to_add = "SmartFix Remediated"
    print(f"Attempting to tag vulnerability {vuln_uuid} with '{tag_to_add}'...")
    existing_tags = contrast_api.get_vulnerability_tags(
        vuln_uuid=vuln_uuid,
        contrast_host=config.CONTRAST_HOST,
        contrast_org_id=config.CONTRAST_ORG_ID,
        contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
        contrast_api_key=config.CONTRAST_API_KEY
    )

    if existing_tags is not None:
        if tag_to_add not in existing_tags:  # Covers empty list or list without the specific tag
            new_tags_list = existing_tags + [tag_to_add]
            tags_updated = contrast_api.add_vulnerability_tags(
                vuln_uuid=vuln_uuid,
                tags_to_set=new_tags_list,
                contrast_host=config.CONTRAST_HOST,
                contrast_org_id=config.CONTRAST_ORG_ID,
                contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                contrast_api_key=config.CONTRAST_API_KEY
            )
            if tags_updated:
                debug_print(f"Successfully added tag '{tag_to_add}' to vulnerability {vuln_uuid}.")
            else:
                print(f"Warning: Failed to add tag '{tag_to_add}' to vulnerability {vuln_uuid}.", file=sys.stderr)
        else:  # Tag already exists
            debug_print(f"Tag '{tag_to_add}' already exists for vulnerability {vuln_uuid}.")
    else:
        print(f"Warning: Could not retrieve existing tags for vulnerability {vuln_uuid}. Skipping tagging.", file=sys.stderr)

    print("--- Merged Contrast AI SmartFix Pull Request Handling Complete ---")

if __name__ == "__main__":
    handle_merged_pr()

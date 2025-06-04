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

import requests
import json
import sys
from typing import Optional
import config
from utils import debug_print

def add_note_to_vulnerability(vuln_uuid: str, note_content: str, contrast_host: str, contrast_org_id: str, contrast_app_id: str, contrast_auth_key: str, contrast_api_key: str) -> bool:
    """Adds a note to a specific vulnerability in Contrast.

    Args:
        vuln_uuid: The UUID of the vulnerability.
        note_content: The content of the note to add.
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_app_id: The application ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        bool: True if the note was added successfully, False otherwise.
    """
    debug_print(f"--- Adding note to vulnerability {vuln_uuid} ---")
    # The app_id is in the URL structure for notes, ensure it's available
    api_url = f"https://{contrast_host}/Contrast/api/ng/{contrast_org_id}/applications/{contrast_app_id}/traces/{vuln_uuid}/notes?expand=skip_links"

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "note": note_content
    }

    try:
        debug_print(f"Making POST request to: {api_url}")
        debug_print(f"Payload: {json.dumps(payload)}") # Log the payload for debugging
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        debug_print(f"Add note API Response Status Code: {response.status_code}")
        response_json = response.json()

        if response_json.get("success"):
            print(f"Successfully added note to vulnerability {vuln_uuid}.")
            return True
        else:
            error_message = response_json.get("messages", ["Unknown error"])[0]
            print(f"Failed to add note to vulnerability {vuln_uuid}. Error: {error_message}", file=sys.stderr)
            return False

    except requests.exceptions.HTTPError as e:
        print(f"HTTP error adding note to vulnerability {vuln_uuid}: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Request error adding note to vulnerability {vuln_uuid}: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error decoding JSON response when adding note to vulnerability {vuln_uuid}.", file=sys.stderr)
        sys.exit(1)

def set_vulnerability_status(vuln_uuid: str, status: str, contrast_host: str, contrast_org_id: str, contrast_auth_key: str, contrast_api_key: str, pr_url: str) -> bool:
    """Sets the status of a specific vulnerability in Contrast."""
    api_url = f"https://{contrast_host}/Contrast/api/ng/{contrast_org_id}/orgtraces/mark"
    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "note": f"Contrast AI SmartFix remediated ({pr_url if pr_url else 'Unknown URL'})",
        "traces": [vuln_uuid],
        "status": status
    }

    debug_print(f"Setting status for {vuln_uuid} to {status} via URL: {api_url}")
    debug_print(f"Payload for set status: {json.dumps(payload)}")

    try:
        response = requests.put(api_url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200: # Or other success codes like 204
            debug_print(f"Successfully set status for vulnerability {vuln_uuid} to {status}.")
            return True
        else:
            print(f"Error setting status for vulnerability {vuln_uuid}: {response.status_code} - {response.text}", file=sys.stderr)
            return False
    except requests.exceptions.RequestException as e:
        print(f"Request failed while setting status for vulnerability {vuln_uuid}: {e}", file=sys.stderr)
        sys.exit(1)

def get_vulnerability_tags(vuln_uuid: str, contrast_host: str, contrast_org_id: str, contrast_auth_key: str, contrast_api_key: str) -> Optional[list[str]]:
    """Gets the existing tags for a specific vulnerability in Contrast."""
    api_url = f"https://{contrast_host}/Contrast/api/ng/{contrast_org_id}/tags/traces/bulk?expand=skip_links"
    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {"traces_uuid": [vuln_uuid]}

    debug_print(f"Getting tags for {vuln_uuid} via URL: {api_url}")
    debug_print(f"Payload for get tags: {json.dumps(payload)}")

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("success"):
                tags = response_data.get("tags", [])
                debug_print(f"Successfully retrieved tags for vulnerability {vuln_uuid}: {tags}")
                return tags
            else:
                print(f"API indicated failure while getting tags for {vuln_uuid}: {response_data.get('messages')}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Error getting tags for vulnerability {vuln_uuid}: {response.status_code} - {response.text}", file=sys.stderr)
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Request failed while getting tags for vulnerability {vuln_uuid}: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON response while getting tags for {vuln_uuid}: {e}", file=sys.stderr)
        sys.exit(1)


def add_vulnerability_tags(vuln_uuid: str, tags_to_set: list[str], contrast_host: str, contrast_org_id: str, contrast_auth_key: str, contrast_api_key: str) -> bool:
    """Adds tags to a specific vulnerability in Contrast. This will overwrite existing tags if not included in tags_to_set."""
    api_url = f"https://{contrast_host}/Contrast/api/ng/{contrast_org_id}/tags/traces/bulk?expand=skip_links"
    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "traces_uuid": [vuln_uuid],
        "tags": tags_to_set,
        "tags_remove": []  # Assuming we don't want to explicitly remove any tags not in the new set this way
    }

    debug_print(f"Setting tags for {vuln_uuid} to {tags_to_set} via URL: {api_url}")
    debug_print(f"Payload for set tags: {json.dumps(payload)}")

    try:
        response = requests.put(api_url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("success"):
                debug_print(f"Successfully set tags for vulnerability {vuln_uuid}.")
                return True
            else:
                print(f"API indicated failure while setting tags for {vuln_uuid}: {response_data.get('messages')}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Error setting tags for vulnerability {vuln_uuid}: {response.status_code} - {response.text}", file=sys.stderr)
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Request failed while setting tags for vulnerability {vuln_uuid}: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON response while setting tags for {vuln_uuid}: {e}", file=sys.stderr)
        sys.exit(1)

def get_vulnerability_with_prompts(contrast_host, contrast_org_id, contrast_app_id, contrast_auth_key, contrast_api_key, max_open_prs, github_repo_url, vulnerability_severities):
    """Fetches a vulnerability to process along with pre-populated prompt templates from the new prompt-details endpoint.
    
    Args:
        contrast_host: The Contrast Security host URL
        contrast_org_id: The organization ID
        contrast_app_id: The application ID
        contrast_auth_key: The Contrast authorization key
        contrast_api_key: The Contrast API key
        max_open_prs: Maximum number of open PRs allowed
        github_repo_url: The GitHub repository URL
        vulnerability_severities: List of severity levels to filter by
    
    Returns:
        dict: Contains vulnerability data and prompts, or None if no vulnerability found or error occurred
        Structure: {
            'vulnerability': {...},
            'fixSystemPrompt': '...',
            'fixUserPrompt': '...',
            'qaSystemPrompt': '...',
            'qaUserPrompt': '...'
        }
    """
    debug_print("\n--- Fetching vulnerability and prompts from prompt-details API ---")
    
    api_url = f"https://{contrast_host}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/prompt-details"
    debug_print(f"API URL: {api_url}")
    
    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Replace placeholder values with actual config values
    payload = {
        "teamserverHost": f"https://{contrast_host}",
        "repoRootDir": str(config.REPO_ROOT),
        "repoUrl": github_repo_url,
        "maxPullRequests": max_open_prs,
        "severities": vulnerability_severities
    }
    
    debug_print(f"Request payload: {json.dumps(payload, indent=2)}")
    
    try:
        debug_print(f"Making POST request to: {api_url}")
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        
        debug_print(f"Prompt-details API Response Status Code: {response.status_code}")
        
        # Handle different status codes
        if response.status_code == 204:
            print("No vulnerabilities found that need remediation (204 No Content).")
            return None
        elif response.status_code == 409:
            print("At or over the maximum PR limit (409 Conflict).")
            return None
        elif response.status_code == 200:
            response_json = response.json()
            debug_print(f"Full response_json: {json.dumps(response_json, indent=2)}")
            
            debug_print("Successfully received vulnerability and prompts from API")
            debug_print(f"Response keys: {list(response_json.keys())}")
            
            # Validate that we have all required components
            required_keys = ['remediationId', 'vulnerabilityUuid', 'vulnerabilityTitle', 'vulnerabilityRuleName', 'vulnerabilitySeverity', 'vulnerabilityStatus', 'vulnerabilitySeverity', 'fixSystemPrompt', 'fixUserPrompt', 'qaSystemPrompt', 'qaUserPrompt']
            missing_keys = [key for key in required_keys if key not in response_json]
            
            if missing_keys:
                print(f"Error: Missing required keys in API response: {missing_keys}", file=sys.stderr)
                sys.exit(1)
            
            return response_json
        else:
            print(f"Unexpected status code {response.status_code} from prompt-details API: {response.text}", file=sys.stderr)
            sys.exit(1)
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching vulnerability and prompts: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error decoding JSON response from prompt-details API.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error calling prompt-details API: {e}", file=sys.stderr)
        sys.exit(1)

# %%

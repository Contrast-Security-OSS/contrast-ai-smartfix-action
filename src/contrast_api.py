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

def normalize_host(host: str) -> str:
    """Remove any protocol prefix from host to prevent double prefixing when constructing URLs."""
    return host.replace('https://', '').replace('http://', '')

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
    
    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/prompt-details"
    debug_print(f"API URL: {api_url}")
    
    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }
    
    # Replace placeholder values with actual config values
    payload = {
        "teamserverHost": f"https://{normalize_host(contrast_host)}",
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
            required_keys = ['remediationId', 'vulnerabilityUuid', 'vulnerabilityTitle', 'vulnerabilityRuleName', 'vulnerabilityStatus', 'vulnerabilitySeverity', 'fixSystemPrompt', 'fixUserPrompt', 'qaSystemPrompt', 'qaUserPrompt']
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

def notify_remediation_pr_opened(remediation_id: str, pr_number: int, pr_url: str, contrast_host: str, contrast_org_id: str, contrast_app_id: str, contrast_auth_key: str, contrast_api_key: str) -> bool:
    """Notifies the Remediation backend service that a PR has been opened for a remediation.

    Args:
        remediation_id: The ID of the remediation.
        pr_number: The PR number.
        pr_url: The URL of the PR.
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_app_id: The application ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        bool: True if the notification was successful, False otherwise.
    """
    debug_print(f"--- Notifying Remediation service about PR for remediation {remediation_id} ---")
    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/remediations/{remediation_id}/open"

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }
    
    payload = {
        "pullRequestNumber": pr_number,
        "pullRequestUrl": pr_url
    }

    try:
        debug_print(f"Making PUT request to: {api_url}")
        debug_print(f"Payload: {json.dumps(payload)}") # Log the payload for debugging
        response = requests.put(api_url, headers=headers, json=payload)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        debug_print(f"Remediation notification API response status code: {response.status_code}")
        
        if response.status_code == 204:
            debug_print(f"Successfully notified Remediation service API about PR for remediation {remediation_id}")
            return True
        else:
            error_message = "Unknown error"
            try:
                response_json = response.json()
                if "messages" in response_json and response_json["messages"]:
                    error_message = response_json["messages"][0]
            except:
                error_message = response.text
                
            print(f"Failed to notify Remediation service about PR for remediation {remediation_id}. Error: {error_message}", file=sys.stderr)
            return False

    except requests.exceptions.HTTPError as e:
        print(f"HTTP error notifying Remediation service about PR for remediation {remediation_id}: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        return False
    except requests.exceptions.RequestException as e:
        print(f"Request error notifying Remediation service about PR for remediation {remediation_id}: {e}", file=sys.stderr)
        return False
    except json.JSONDecodeError:
        print(f"Error decoding JSON response when notifying Remediation service about PR for remediation {remediation_id}.", file=sys.stderr)
        return False

def notify_remediation_pr_merged(remediation_id: str, contrast_host: str, contrast_org_id: str, contrast_app_id: str, contrast_auth_key: str, contrast_api_key: str) -> bool:
    """Notifies the Remediation backend service that a PR has been merged for a remediation.

    Args:
        remediation_id: The ID of the remediation.
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_app_id: The application ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        bool: True if the notification was successful, False otherwise.
    """
    debug_print(f"--- Notifying Remediation service about merged PR for remediation {remediation_id} ---")
    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/remediations/{remediation_id}/merged"

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    try:
        debug_print(f"Making PUT request to: {api_url}")
        response = requests.put(api_url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        debug_print(f"Remediation merged notification API response status code: {response.status_code}")
        
        if response.status_code == 204:
            debug_print(f"Successfully notified Remediation service API about merged PR for remediation {remediation_id}")
            return True
        else:
            error_message = "Unknown error"
            try:
                response_json = response.json()
                if "messages" in response_json and response_json["messages"]:
                    error_message = response_json["messages"][0]
            except:
                error_message = response.text
                
            print(f"Failed to notify Remediation service about merged PR for remediation {remediation_id}. Error: {error_message}", file=sys.stderr)
            return False

    except requests.exceptions.HTTPError as e:
        print(f"HTTP error notifying Remediation service about merged PR for remediation {remediation_id}: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        return False
    except requests.exceptions.RequestException as e:
        print(f"Request error notifying Remediation service about merged PR for remediation {remediation_id}: {e}", file=sys.stderr)
        return False
    except json.JSONDecodeError:
        print(f"Error decoding JSON response when notifying Remediation service about merged PR for remediation {remediation_id}.", file=sys.stderr)
        return False

def notify_remediation_pr_closed(remediation_id: str, contrast_host: str, contrast_org_id: str, contrast_app_id: str, contrast_auth_key: str, contrast_api_key: str) -> bool:
    """Notifies the Remediation backend service that a PR has been closed without merging for a remediation.

    Args:
        remediation_id: The ID of the remediation.
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_app_id: The application ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        bool: True if the notification was successful, False otherwise.
    """
    debug_print(f"--- Notifying Remediation service about closed PR for remediation {remediation_id} ---")
    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/remediations/{remediation_id}/closed"

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    try:
        debug_print(f"Making PUT request to: {api_url}")
        response = requests.put(api_url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        debug_print(f"Remediation closed notification API response status code: {response.status_code}")
        
        if response.status_code == 204:
            debug_print(f"Successfully notified Remediation service API about closed PR for remediation {remediation_id}")
            return True
        else:
            error_message = "Unknown error"
            try:
                response_json = response.json()
                if "messages" in response_json and response_json["messages"]:
                    error_message = response_json["messages"][0]
            except:
                error_message = response.text
                
            print(f"Failed to notify Remediation service about closed PR for remediation {remediation_id}. Error: {error_message}", file=sys.stderr)
            return False

    except requests.exceptions.HTTPError as e:
        print(f"HTTP error notifying Remediation service about closed PR for remediation {remediation_id}: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        return False
    except requests.exceptions.RequestException as e:
        print(f"Request error notifying Remediation service about closed PR for remediation {remediation_id}: {e}", file=sys.stderr)
        return False
    except json.JSONDecodeError:
        print(f"Error decoding JSON response when notifying Remediation service about closed PR for remediation {remediation_id}.", file=sys.stderr)
        return False

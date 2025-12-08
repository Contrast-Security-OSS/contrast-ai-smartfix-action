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

import requests
import json
import sys
from typing import Optional
from src.config import get_config
from src.utils import debug_log, log, normalize_host
from src import telemetry_handler
from src.smartfix.domains.workflow.credit_tracking import CreditTrackingResponse

config = get_config()


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
    debug_log("\n--- Fetching vulnerability and prompts from prompt-details API ---")

    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/prompt-details"
    debug_log(f"API URL: {api_url}")

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
        "severities": vulnerability_severities,
        "contrastProvidedLlm": config.USE_CONTRAST_LLM
    }

    debug_log(f"Request payload: {json.dumps(payload, indent=2)}")

    try:
        debug_log(f"Making POST request to: {api_url}")
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)

        debug_log(f"Prompt-details API Response Status Code: {response.status_code}")

        # Handle different status codes
        if response.status_code == 204:
            log("No vulnerabilities found that need remediation")
            return None
        elif response.status_code == 409:
            log("At or over the maximum PR limit")
            return None
        elif response.status_code == 200:
            response_json = response.json()

            # Create a redacted copy of the response for debug logging
            redacted_response = response_json.copy()
            # Redact sensitive prompt data
            for key in ['fixSystemPrompt', 'fixUserPrompt', 'qaSystemPrompt', 'qaUserPrompt']:
                if key in redacted_response:
                    redacted_response[key] = f"[REDACTED - {len(redacted_response[key])} chars]"

            debug_log(f"Response with redacted prompts: {json.dumps(redacted_response, indent=2)}")
            debug_log("Successfully received vulnerability and prompts from API")
            debug_log(f"Response keys: {list(response_json.keys())}")

            # Validate that we have all required components
            required_keys = ['remediationId', 'vulnerabilityUuid', 'vulnerabilityTitle', 'vulnerabilityRuleName',
                             'vulnerabilityStatus', 'vulnerabilitySeverity', 'fixSystemPrompt', 'fixUserPrompt',
                             'qaSystemPrompt', 'qaUserPrompt']
            missing_keys = [key for key in required_keys if key not in response_json]

            if missing_keys:
                log(f"Error: Missing required keys in API response: {missing_keys}", is_error=True)
                sys.exit(1)

            return response_json
        else:
            log(f"Unexpected status code {response.status_code} from prompt-details API: {response.text}", is_error=True)
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        log(f"Error fetching vulnerability and prompts: {e}", is_error=True)
        sys.exit(1)
    except json.JSONDecodeError:
        log("Error decoding JSON response from prompt-details API.", is_error=True)
        sys.exit(1)
    except Exception as e:
        log(f"Unexpected error calling prompt-details API: {e}", is_error=True)
        sys.exit(1)


def notify_remediation_pr_opened(remediation_id: str, pr_number: int, pr_url: str, contrastProvidedLlm: bool, contrast_host: str,
                                 contrast_org_id: str, contrast_app_id: str, contrast_auth_key: str,
                                 contrast_api_key: str) -> bool:
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
    debug_log(f"--- Notifying Remediation service about PR for remediation {remediation_id} ---")
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
        "pullRequestUrl": pr_url,
        "contrastProvidedLlm": contrastProvidedLlm
    }

    try:
        debug_log(f"Making PUT request to: {api_url}")
        debug_log(f"Payload: {json.dumps(payload)}")  # Log the payload for debugging
        response = requests.put(api_url, headers=headers, json=payload)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        debug_log(f"Remediation notification API response status code: {response.status_code}")

        # Log all response information for debugging
        debug_log(f"Response headers: {dict(response.headers)}")
        debug_log(f"Raw response text: {response.text}")

        if response.status_code in [200, 204]:
            debug_log(f"Successfully notified Remediation service API about PR for remediation {remediation_id}")
            return True
        else:
            log(f"Failed to notify Remediation service about PR for remediation {remediation_id}. Response: {response.text}", is_error=True)
            return False

    except requests.exceptions.HTTPError as e:
        log(f"HTTP error notifying Remediation service about PR for remediation {remediation_id}: {e.response.status_code} - {e.response.text}", is_error=True)
        return False
    except requests.exceptions.RequestException as e:
        log(f"Request error notifying Remediation service about PR for remediation {remediation_id}: {e}", is_error=True)
        return False
    except json.JSONDecodeError:
        log(f"Error decoding JSON response when notifying Remediation service about PR for remediation {remediation_id}.", is_error=True)
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
    debug_log(f"--- Notifying Remediation service about merged PR for remediation {remediation_id} ---")
    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/remediations/{remediation_id}/merged"

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    try:
        debug_log(f"Making PUT request to: {api_url}")
        response = requests.put(api_url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        debug_log(f"Remediation merged notification API response status code: {response.status_code}")

        if response.status_code == 204:
            debug_log(f"Successfully notified Remediation service API about merged PR for remediation {remediation_id}")
            return True
        else:
            error_message = "Unknown error"
            try:
                response_json = response.json()
                if "messages" in response_json and response_json["messages"]:
                    error_message = response_json["messages"][0]
            except (ValueError, KeyError):
                error_message = response.text

            log(f"Failed to notify Remediation service about merged PR for remediation {remediation_id}. Error: {error_message}", is_error=True)
            return False

    except requests.exceptions.HTTPError as e:
        log(f"HTTP error notifying Remediation service about merged PR for remediation {remediation_id}: {e.response.status_code} - {e.response.text}", is_error=True)
        return False
    except requests.exceptions.RequestException as e:
        log(f"Request error notifying Remediation service about merged PR for remediation {remediation_id}: {e}", is_error=True)
        return False
    except json.JSONDecodeError:
        log(f"Error decoding JSON response when notifying Remediation service about merged PR for remediation {remediation_id}.", is_error=True)
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
    debug_log(f"--- Notifying Remediation service about closed PR for remediation {remediation_id} ---")
    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/remediations/{remediation_id}/closed"

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    try:
        debug_log(f"Making PUT request to: {api_url}")
        response = requests.put(api_url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        debug_log(f"Remediation closed notification API response status code: {response.status_code}")

        if response.status_code == 204:
            debug_log(f"Successfully notified Remediation service API about closed PR for remediation {remediation_id}")
            return True
        else:
            error_message = "Unknown error"
            try:
                response_json = response.json()
                if "messages" in response_json and response_json["messages"]:
                    error_message = response_json["messages"][0]
            except (ValueError, KeyError):
                error_message = response.text

            log(f"Failed to notify Remediation service about closed PR for remediation {remediation_id}. Error: {error_message}", is_error=True)
            return False

    except requests.exceptions.HTTPError as e:
        log(f"HTTP error notifying Remediation service about closed PR for remediation {remediation_id}: {e.response.status_code} - {e.response.text}", is_error=True)
        return False
    except requests.exceptions.RequestException as e:
        log(f"Request error notifying Remediation service about closed PR for remediation {remediation_id}: {e}", is_error=True)
        return False
    except json.JSONDecodeError:
        log(f"Error decoding JSON response when notifying Remediation service about closed PR for remediation {remediation_id}.", is_error=True)
        return False


def send_telemetry_data() -> bool:
    """Sends the collected telemetry data to the backend.

    Args:
        telemetry_data: The telemetry data dictionary.

    Returns:
        bool: True if sending was successful, False otherwise.
    """
    telemetry_data = telemetry_handler.get_telemetry_data()

    if not all([config.CONTRAST_HOST, config.CONTRAST_ORG_ID, config.CONTRAST_APP_ID, config.CONTRAST_AUTHORIZATION_KEY, config.CONTRAST_API_KEY]):
        log("Telemetry endpoint configuration is incomplete. Skipping telemetry send.", is_warning=True)
        return False

    # Get remediationId from telemetry_data.additionalAttributes.remediationId
    remediation_id_for_url = telemetry_data.get("additionalAttributes", {}).get("remediationId", None)

    if not remediation_id_for_url:
        log("remediationId not found in telemetry_data.additionalAttributes. Telemetry data not sent.", is_warning=True)
        return

    base_url = f"https://{normalize_host(config.CONTRAST_HOST)}/api/v4/aiml-remediation"
    api_url = f"{base_url}/organizations/{config.CONTRAST_ORG_ID}/applications/{config.CONTRAST_APP_ID}/remediations/{remediation_id_for_url}/telemetry"

    headers = {
        "Authorization": config.CONTRAST_AUTHORIZATION_KEY,
        "API-Key": config.CONTRAST_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"AI SmartFix {config.VERSION}"  # Use specific User-Agent
    }

    debug_log(f"Sending telemetry data to: {api_url}")
    # Avoid logging full telemetry data by default in production to prevent sensitive info leakage
    # For debugging, one might temporarily log: debug_log(f"Telemetry payload: {json.dumps(telemetry_data, indent=2)}")

    try:
        response = requests.post(api_url, headers=headers, json=telemetry_data, timeout=30)

        if response.status_code >= 200 and response.status_code < 300:
            debug_log(f"Telemetry data sent successfully. Status: {response.status_code}")
            return True
        else:
            log(f"Failed to send telemetry data. Status: {response.status_code} - Response: {response.text}", is_error=True)
            return False
    except requests.exceptions.RequestException as e:
        log(f"Error sending telemetry data: {e}", is_error=True)
        return False
    except Exception as e:
        log(f"Unexpected error sending telemetry: {e}", is_error=True)
        return False


def notify_remediation_failed(remediation_id: str, failure_category: str, contrast_host: str,
                              contrast_org_id: str, contrast_app_id: str, contrast_auth_key: str,
                              contrast_api_key: str) -> bool:
    """Notifies the Remediation backend service that a remediation has failed.

    Args:
        remediation_id: The ID of the remediation.
        failure_category: The category of failure (e.g., "INITIAL_BUILD_FAILURE").
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_app_id: The application ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        bool: True if the notification was successful, False otherwise.
    """
    debug_log(f"--- Notifying Remediation service about failed remediation {remediation_id} with category {failure_category} ---")
    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/remediations/{remediation_id}/failed"

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    payload = {
        "failureCategory": failure_category
    }

    try:
        debug_log(f"Making PUT request to: {api_url}")
        debug_log(f"Payload: {json.dumps(payload)}")
        response = requests.put(api_url, headers=headers, json=payload)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        debug_log(f"Remediation failed notification API response status code: {response.status_code}")

        if response.status_code == 204:
            debug_log(f"Successfully notified Remediation service API about failed remediation {remediation_id}")
            return True
        else:
            error_message = "Unknown error"
            try:
                response_json = response.json()
                if "messages" in response_json and response_json["messages"]:
                    error_message = response_json["messages"][0]
            except (ValueError, KeyError):
                error_message = response.text

            log(f"Failed to notify Remediation service about failed remediation {remediation_id}. Error: {error_message}", is_error=True)
            return False

    except requests.exceptions.HTTPError as e:
        log(f"HTTP error notifying Remediation service about failed remediation {remediation_id}: {e.response.status_code} - {e.response.text}", is_error=True)
        return False
    except requests.exceptions.RequestException as e:
        log(f"Request error notifying Remediation service about failed remediation {remediation_id}: {e}", is_error=True)
        return False
    except json.JSONDecodeError:
        log(f"Error decoding JSON response when notifying Remediation service about failed remediation {remediation_id}.", is_error=True)
        return False


def get_vulnerability_details(contrast_host: str, contrast_org_id: str, contrast_app_id: str,
                              contrast_auth_key: str, contrast_api_key: str, github_repo_url: str,
                              max_pull_requests: int = 5, severities: list = None) -> dict:
    """Gets vulnerability remediation details from the Contrast API.

    Args:
        contrast_host: The Contrast Security host URL
        contrast_org_id: The organization ID
        contrast_app_id: The application ID
        contrast_auth_key: The Contrast authorization key
        contrast_api_key: The Contrast API key
        github_repo_url: The GitHub repository URL
        max_pull_requests: Maximum number of pull requests (default: 5)
        severities: List of vulnerability severities to filter by (default: ["CRITICAL", "HIGH"])

    Returns:
        dict: Contains vulnerability remediation details or None if no vulnerability found
        Structure: {
            'remediationId': '...',
            'vulnerabilityUuid': '...',
            'vulnerabilityTitle': '...',
            'vulnerabilityRuleName': '...',
            'vulnerabilityStatus': '...',
            'vulnerabilitySeverity': '...',
            'vulnerabilityOverviewStory': '...',
            'vulnerabilityEventsSummary': '...',
            'vulnerabilityHttpRequestDetails': '...'
        }
    """
    if severities is None:
        severities = ["CRITICAL", "HIGH"]

    debug_log("\n--- Fetching vulnerability details from remediation-details API ---")

    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/remediation-details"
    debug_log(f"API URL: {api_url}")

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    payload = {
        "teamserverHost": f"https://{normalize_host(contrast_host)}",
        "repoRootDir": str(config.REPO_ROOT),
        "repoUrl": github_repo_url,
        "maxPullRequests": max_pull_requests,
        "severities": severities
    }

    debug_log(f"Request payload: {json.dumps(payload, indent=2)}")

    try:
        debug_log(f"Making POST request to: {api_url}")
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)

        debug_log(f"Remediation-details API Response Status Code: {response.status_code}")

        # Handle different status codes
        if response.status_code == 204:
            log("No vulnerabilities found that need remediation")
            return None
        elif response.status_code == 409:
            log("At or over the maximum PR limit")
            return None
        elif response.status_code == 200:
            response_json = response.json()
            debug_log("Successfully received vulnerability details from API")
            debug_log(f"Response keys: {list(response_json.keys())}")

            # Validate that we have required components
            required_keys = ['remediationId', 'vulnerabilityUuid', 'vulnerabilityTitle']
            missing_keys = [key for key in required_keys if key not in response_json]

            if missing_keys:
                log(f"Warning: Missing some keys in API response: {missing_keys}")

            # Log a summary without exposing sensitive details
            debug_log(f"Vulnerability UUID: {response_json.get('vulnerabilityUuid', 'Unknown')}")
            debug_log(f"Vulnerability Title: {response_json.get('vulnerabilityTitle', 'Unknown')}")
            debug_log(f"Vulnerability Severity: {response_json.get('vulnerabilitySeverity', 'Unknown')}")
            debug_log(f"Remediation ID: {response_json.get('remediationId', 'Unknown')}")

            return response_json
        else:
            log(f"Unexpected status code {response.status_code} from remediation-details API: {response.text}", is_error=True)
            return None

    except requests.exceptions.RequestException as e:
        log(f"Error fetching vulnerability details: {e}", is_error=True)
        return None
    except json.JSONDecodeError:
        log("Error decoding JSON response from remediation-details API.", is_error=True)
        return None
    except Exception as e:
        log(f"Unexpected error calling remediation-details API: {e}", is_error=True)
        return None


def get_credit_tracking(contrast_host: str, contrast_org_id: str, contrast_app_id: str, contrast_auth_key: str, contrast_api_key: str) -> Optional[CreditTrackingResponse]:
    """Get credit tracking information from the Contrast API.

    Args:
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_app_id: The application ID.
        contrast_auth_key: The Contrast authorization key.

    Returns:
        CreditTrackingResponse object if successful, None if failed.
    """
    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/applications/{contrast_app_id}/credit-tracking"

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    try:
        debug_log(f"Fetching credit tracking from: {api_url}")
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()

        debug_log(f"Credit tracking API response status code: {response.status_code}")
        debug_log(f"Raw credit tracking response: {response.text}")

        data = response.json()
        return CreditTrackingResponse.from_api_response(data)

    except requests.exceptions.HTTPError as e:
        debug_log(f"HTTP error fetching credit tracking: {e.response.status_code} - {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        debug_log(f"Request error fetching credit tracking: {e}")
        return None
    except json.JSONDecodeError:
        debug_log("Error decoding JSON response from credit-tracking API.")
        return None
    except Exception as e:
        debug_log(f"Unexpected error calling credit-tracking API: {e}")
        return None

# %%

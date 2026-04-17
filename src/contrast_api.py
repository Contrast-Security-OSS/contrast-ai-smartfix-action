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
from src.utils import debug_log, log, normalize_host, RED, RESET
from src.smartfix.domains.telemetry import telemetry_handler
from src.smartfix.domains.workflow.credit_tracking import CreditTrackingResponse

config = get_config()


def get_sanitized_409_message(response_text: str, credit_info=None) -> tuple[str, bool]:
    """
    Return a user-friendly message for 409 responses and whether it's an error condition.

    Args:
        response_text: The raw response body from the API
        credit_info: Optional CreditTrackingResponse to determine trial vs credit exhaustion

    Returns:
        Tuple of (sanitized message, is_error_condition)
        is_error_condition=True means action should exit with code 1
        is_error_condition=False means action can exit with code 0 (e.g., PR limit is expected)
    """
    from datetime import datetime, timezone

    try:
        error_data = json.loads(response_text)
        backend_msg = error_data.get('message', '')
    except (json.JSONDecodeError, ValueError):
        backend_msg = response_text

    # PR limit - NOT an error, expected behavior
    if "Maximum pull request limit" in backend_msg:
        return ("Maximum pull request limit exceeded", False)

    # Credits exhausted - check if trial expired vs credits used up
    if "Credits have been exhausted" in backend_msg:
        if credit_info and credit_info.end_date and credit_info.end_date.strip():
            try:
                end_date = datetime.fromisoformat(credit_info.end_date.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                if now > end_date:
                    return ("Your Contrast-provided LLM trial has expired. Please contact your Contrast representative to renew.", True)
            except (ValueError, AttributeError):
                # If date parsing fails, fall through to credits exhausted message
                debug_log(f"Could not parse end_date: {credit_info.end_date}")
        return ("Your Contrast-provided LLM credits have been exhausted. Please contact your Contrast representative for additional credits.", True)

    # No credit tracking entry
    if "No active remediation credit tracking" in backend_msg:
        return ("This organization is not enabled for Contrast-provided LLM. Configure your own LLM provider, "
                "or contact your Contrast representative to enable this feature.", True)

    # Generic fallback for unknown 409 errors - IS an error
    return ("Unable to process request. Please try again or contact Contrast support if the issue persists.", True)


def get_org_open_remediations(contrast_host: str, contrast_org_id: str, app_ids: list,
                              contrast_auth_key: str, contrast_api_key: str) -> list:
    """Returns open remediations across multiple apps from the org-level endpoint.

    Best-effort: returns [] on any error. Must not block main flow.

    Args:
        contrast_host: The Contrast Security host URL
        contrast_org_id: The organization ID
        app_ids: List of application IDs to query
        contrast_auth_key: The Contrast authorization key
        contrast_api_key: The Contrast API key

    Returns:
        list: List of open remediation dicts, or empty list on error
    """
    api_url = (f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/"
               f"organizations/{contrast_org_id}/remediations/open")

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    payload = {"appIds": app_ids}

    try:
        debug_log(f"Fetching org-level open remediations from: {api_url}")
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)

        if response.status_code == 200:
            result = response.json()
            debug_log(f"Found {len(result)} open remediations")
            return result
        else:
            log(f"Unexpected status {response.status_code} fetching org open remediations: {response.text[:500]}", is_warning=True)
            return []

    except requests.exceptions.RequestException as e:
        log(f"Error fetching org open remediations: {e}", is_warning=True)
        return []
    except json.JSONDecodeError:
        log("Error decoding JSON from org open remediations endpoint", is_warning=True)
        return []
    except Exception as e:
        log(f"Unexpected error fetching org open remediations: {e}", is_warning=True)
        return []


def get_org_remediation_details(contrast_host: str, contrast_org_id: str, app_ids: list,
                                contrast_auth_key: str, contrast_api_key: str,
                                github_repo_url: str, max_pull_requests: int = 5,
                                severities: list = None, credit_info=None) -> Optional[dict]:
    """Gets vulnerability remediation details from the org-level endpoint.

    Args:
        contrast_host: The Contrast Security host URL
        contrast_org_id: The organization ID
        app_ids: List of application IDs to query
        contrast_auth_key: The Contrast authorization key
        contrast_api_key: The Contrast API key
        github_repo_url: The GitHub repository URL
        max_pull_requests: Maximum number of pull requests (default: 5)
        severities: List of vulnerability severities to filter by
        credit_info: Optional CreditTrackingResponse for 409 message handling

    Returns:
        dict: Remediation details including applicationId and skippedAppIds, or None
    """
    if severities is None:
        severities = ["CRITICAL", "HIGH"]

    debug_log("\n--- Fetching org-level vulnerability details from remediation-details API ---")

    api_url = (f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/"
               f"organizations/{contrast_org_id}/remediation-details")
    debug_log(f"API URL: {api_url}")

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    payload = {
        "appIds": app_ids,
        "teamserverHost": f"https://{normalize_host(contrast_host)}",
        "repoRootDir": str(config.REPO_ROOT),
        "repoUrl": github_repo_url,
        "maxPullRequests": max_pull_requests,
        "severities": severities
    }

    try:
        debug_log(f"Making POST request to: {api_url}")
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)

        debug_log(f"Org remediation-details API Response Status Code: {response.status_code}")

        if response.status_code == 204:
            log("No vulnerabilities found that need remediation")
            return None
        elif response.status_code == 409:
            error_msg, is_error = get_sanitized_409_message(response.text, credit_info)
            log(f"{RED}{error_msg}{RESET}", is_error=is_error)
            if is_error:
                sys.exit(1)
            return None
        elif response.status_code == 200:
            response_json = response.json()
            debug_log("Successfully received org-level vulnerability details from API")
            debug_log(f"Response keys: {list(response_json.keys())}")

            required_keys = ['remediationId', 'vulnerabilityUuid', 'vulnerabilityTitle',
                             'vulnerabilityRuleName']
            missing_keys = [key for key in required_keys if key not in response_json]
            if missing_keys:
                log(f"Warning: Missing keys in org remediation-details response: {missing_keys}")

            return response_json
        else:
            log(f"Unexpected status code {response.status_code} from org remediation-details API: {response.text}", is_error=True)
            return None

    except requests.exceptions.RequestException as e:
        log(f"Error fetching org vulnerability details: {e}", is_error=True)
        return None
    except json.JSONDecodeError:
        log("Error decoding JSON response from org remediation-details API.", is_error=True)
        return None
    except Exception as e:
        log(f"Unexpected error calling org remediation-details API: {e}", is_error=True)
        return None


def get_org_prompt_details(contrast_host: str, contrast_org_id: str, app_ids: list,
                           contrast_auth_key: str, contrast_api_key: str,
                           max_open_prs: int, github_repo_url: str,
                           vulnerability_severities: list, credit_info=None) -> Optional[dict]:
    """Fetches a vulnerability and LLM-ready prompts from the org-level prompt-details endpoint.

    Args:
        contrast_host: The Contrast Security host URL
        contrast_org_id: The organization ID
        app_ids: List of application IDs to query
        contrast_auth_key: The Contrast authorization key
        contrast_api_key: The Contrast API key
        max_open_prs: Maximum number of open PRs allowed
        github_repo_url: The GitHub repository URL
        vulnerability_severities: List of severity levels to filter by
        credit_info: Optional CreditTrackingResponse for 409 message handling

    Returns:
        dict: Prompt details including applicationId and skippedAppIds, or None
    """
    debug_log("\n--- Fetching org-level vulnerability and prompts from prompt-details API ---")

    api_url = (f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/"
               f"organizations/{contrast_org_id}/prompt-details")
    debug_log(f"API URL: {api_url}")

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    payload = {
        "appIds": app_ids,
        "teamserverHost": f"https://{normalize_host(contrast_host)}",
        "repoRootDir": str(config.REPO_ROOT),
        "repoUrl": github_repo_url,
        "maxPullRequests": max_open_prs,
        "severities": vulnerability_severities,
        "contrastProvidedLlm": config.USE_CONTRAST_LLM
    }

    try:
        debug_log(f"Making POST request to: {api_url}")
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)

        debug_log(f"Org prompt-details API Response Status Code: {response.status_code}")

        if response.status_code == 204:
            log("No vulnerabilities found that need remediation")
            return None
        elif response.status_code == 503:
            log("All requested applications were inaccessible. Retry the request or verify application access.", is_warning=True)
            return None
        elif response.status_code == 409:
            error_msg, is_error = get_sanitized_409_message(response.text, credit_info)
            log(f"{RED}{error_msg}{RESET}", is_error=is_error)
            if is_error:
                sys.exit(1)
            return None
        elif response.status_code == 200:
            response_json = response.json()
            debug_log("Successfully received org-level vulnerability and prompts from API")
            debug_log(f"Response keys: {list(response_json.keys())}")

            required_keys = ['remediationId', 'vulnerabilityUuid', 'vulnerabilityTitle',
                             'vulnerabilityRuleName', 'vulnerabilityStatus', 'vulnerabilitySeverity',
                             'fixSystemPrompt', 'fixUserPrompt']
            missing_keys = [key for key in required_keys if key not in response_json]
            if missing_keys:
                log(f"Error: Missing required keys in org prompt-details response: {missing_keys}", is_error=True)
                sys.exit(1)

            return response_json
        else:
            log(f"Unexpected status code {response.status_code} from org prompt-details API: {response.text}", is_error=True)
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        log(f"Error fetching org vulnerability and prompts: {e}", is_error=True)
        return None
    except json.JSONDecodeError:
        log("Error decoding JSON response from org prompt-details API.", is_error=True)
        return None
    except Exception as e:
        log(f"Unexpected error calling org prompt-details API: {e}", is_error=True)
        return None


def notify_remediation_pr_opened_org(remediation_id: str, pr_number: int, pr_url: str,
                                     contrast_provided_llm: bool, contrast_host: str,
                                     contrast_org_id: str, contrast_auth_key: str,
                                     contrast_api_key: str) -> bool:
    """Notifies the org-level Remediation backend that a PR has been opened.

    Args:
        remediation_id: The ID of the remediation.
        pr_number: The PR number.
        pr_url: The URL of the PR.
        contrast_provided_llm: True if using Contrast LLM.
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        bool: True if the notification was successful, False otherwise.
    """
    debug_log(f"--- Notifying org-level Remediation service about PR for remediation {remediation_id} ---")
    api_url = (f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/"
               f"organizations/{contrast_org_id}/remediations/{remediation_id}/open")

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
        "contrastProvidedLlm": contrast_provided_llm
    }

    try:
        debug_log(f"Making PUT request to: {api_url}")
        response = requests.put(api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        debug_log(f"Successfully notified org-level Remediation service about PR for remediation {remediation_id}")
        return True

    except requests.exceptions.HTTPError as e:
        log(f"HTTP error notifying org-level Remediation service about PR for remediation {remediation_id}: {e.response.status_code} - {e.response.text}", is_error=True)
        return False
    except requests.exceptions.RequestException as e:
        log(f"Request error notifying org-level Remediation service about PR for remediation {remediation_id}: {e}", is_error=True)
        return False


def notify_remediation_pr_closed_org(remediation_id: str, contrast_host: str,
                                     contrast_org_id: str, contrast_auth_key: str,
                                     contrast_api_key: str) -> bool:
    """Notifies the org-level Remediation backend that a PR has been closed without merging.

    Args:
        remediation_id: The ID of the remediation.
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        bool: True if the notification was successful, False otherwise.
    """
    debug_log(f"--- Notifying org-level Remediation service about closed PR for remediation {remediation_id} ---")
    api_url = (f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/"
               f"organizations/{contrast_org_id}/remediations/{remediation_id}/closed")

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    try:
        debug_log(f"Making PUT request to: {api_url}")
        response = requests.put(api_url, headers=headers, timeout=30)
        response.raise_for_status()
        debug_log(f"Successfully notified org-level Remediation service about closed PR for remediation {remediation_id}")
        return True

    except requests.exceptions.HTTPError as e:
        log(f"HTTP error notifying org-level Remediation service about closed PR for remediation {remediation_id}: {e.response.status_code} - {e.response.text}", is_error=True)
        return False
    except requests.exceptions.RequestException as e:
        log(f"Request error notifying org-level Remediation service about closed PR for remediation {remediation_id}: {e}", is_error=True)
        return False


def notify_remediation_pr_merged_org(remediation_id: str, contrast_host: str,
                                     contrast_org_id: str, contrast_auth_key: str,
                                     contrast_api_key: str) -> bool:
    """Notifies the org-level Remediation backend that a PR has been merged.

    Args:
        remediation_id: The ID of the remediation.
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        bool: True if the notification was successful, False otherwise.
    """
    debug_log(f"--- Notifying org-level Remediation service about merged PR for remediation {remediation_id} ---")
    api_url = (f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/"
               f"organizations/{contrast_org_id}/remediations/{remediation_id}/merged")

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    try:
        debug_log(f"Making PUT request to: {api_url}")
        response = requests.put(api_url, headers=headers, timeout=30)
        response.raise_for_status()
        debug_log(f"Successfully notified org-level Remediation service about merged PR for remediation {remediation_id}")
        return True

    except requests.exceptions.HTTPError as e:
        log(f"HTTP error notifying org-level Remediation service about merged PR for remediation {remediation_id}: {e.response.status_code} - {e.response.text}", is_error=True)
        return False
    except requests.exceptions.RequestException as e:
        log(f"Request error notifying org-level Remediation service about merged PR for remediation {remediation_id}: {e}", is_error=True)
        return False


def notify_remediation_failed_org(remediation_id: str, failure_category: str,
                                  contrast_host: str, contrast_org_id: str,
                                  contrast_auth_key: str, contrast_api_key: str) -> bool:
    """Notifies the org-level Remediation backend that a remediation has failed.

    Args:
        remediation_id: The ID of the remediation.
        failure_category: The category of failure.
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        bool: True if the notification was successful, False otherwise.
    """
    debug_log(f"--- Notifying org-level Remediation service about failed remediation {remediation_id} ---")
    api_url = (f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/"
               f"organizations/{contrast_org_id}/remediations/{remediation_id}/failed")

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    payload = {"failureCategory": failure_category}

    try:
        debug_log(f"Making PUT request to: {api_url}")
        response = requests.put(api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        debug_log(f"Successfully notified org-level Remediation service about failed remediation {remediation_id}")
        return True

    except requests.exceptions.HTTPError as e:
        log(f"HTTP error notifying org-level Remediation service about failed remediation {remediation_id}: {e.response.status_code} - {e.response.text}", is_error=True)
        return False
    except requests.exceptions.RequestException as e:
        log(f"Request error notifying org-level Remediation service about failed remediation {remediation_id}: {e}", is_error=True)
        return False


def send_telemetry_data_org(remediation_id: str, telemetry_data: dict,
                            contrast_host: str, contrast_org_id: str,
                            contrast_auth_key: str, contrast_api_key: str) -> bool:
    """Sends telemetry data to the org-level backend endpoint.

    Args:
        remediation_id: The remediation ID (used in the URL).
        telemetry_data: The telemetry data dictionary.
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        bool: True if sending was successful, False otherwise.
    """
    api_url = (f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/"
               f"organizations/{contrast_org_id}/remediations/{remediation_id}/telemetry")

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    debug_log(f"Sending org-level telemetry data to: {api_url}")

    try:
        response = requests.post(api_url, headers=headers, json=telemetry_data, timeout=30)

        if response.status_code >= 200 and response.status_code < 300:
            debug_log(f"Org-level telemetry data sent successfully. Status: {response.status_code}")
            return True
        else:
            log(f"Failed to send org-level telemetry data. Status: {response.status_code} - Response: {response.text}", is_error=True)
            return False
    except requests.exceptions.RequestException as e:
        log(f"Error sending org-level telemetry data: {e}", is_error=True)
        return False
    except Exception as e:
        log(f"Unexpected error sending org-level telemetry: {e}", is_error=True)
        return False


def get_credit_tracking_org(contrast_host: str, contrast_org_id: str, contrast_auth_key: str, contrast_api_key: str) -> Optional[CreditTrackingResponse]:
    """Get credit tracking information from the org-level Contrast API endpoint.

    Args:
        contrast_host: The Contrast Security host URL.
        contrast_org_id: The organization ID.
        contrast_auth_key: The Contrast authorization key.
        contrast_api_key: The Contrast API key.

    Returns:
        CreditTrackingResponse object if successful, None if failed.
    """
    api_url = f"https://{normalize_host(contrast_host)}/api/v4/aiml-remediation/organizations/{contrast_org_id}/credit-tracking"

    headers = {
        "Authorization": contrast_auth_key,
        "API-Key": contrast_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": config.USER_AGENT
    }

    try:
        debug_log(f"Fetching org-level credit tracking from: {api_url}")
        response = requests.get(api_url, headers=headers, timeout=30)
        response.raise_for_status()

        debug_log(f"Org-level credit tracking API response status code: {response.status_code}")
        debug_log(f"Raw org-level credit tracking response: {response.text}")

        data = response.json()
        return CreditTrackingResponse.from_api_response(data)

    except requests.exceptions.HTTPError as e:
        debug_log(f"HTTP error fetching org-level credit tracking: {e.response.status_code} - {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        debug_log(f"Request error fetching org-level credit tracking: {e}")
        return None
    except json.JSONDecodeError:
        debug_log("Error decoding JSON response from org-level credit-tracking API.")
        return None
    except Exception as e:
        debug_log(f"Unexpected error calling org-level credit-tracking API: {e}")
        return None

# %%

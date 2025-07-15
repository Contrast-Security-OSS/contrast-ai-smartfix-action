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

import requests
import json
import sys
from enum import Enum
from src.utils import debug_log, log
import src.telemetry_handler as telemetry_handler

# Define failure categories as an enum to ensure consistency
class FailureCategory(Enum):
    INITIAL_BUILD_FAILURE = "INITIAL_BUILD_FAILURE"
    EXCEEDED_QA_ATTEMPTS = "EXCEEDED_QA_ATTEMPTS"
    QA_AGENT_FAILURE = "QA_AGENT_FAILURE"
    GIT_COMMAND_FAILURE = "GIT_COMMAND_FAILURE"
    AGENT_FAILURE = "AGENT_FAILURE"
    GENERATE_PR_FAILURE = "GENERATE_PR_FAILURE"
    GENERAL_FAILURE = "GENERAL_FAILURE"
    EXCEEDED_TIMEOUT = "EXCEEDED_TIMEOUT"
    EXCEEDED_AGENT_EVENTS = "EXCEEDED_AGENT_EVENTS"
    INVALID_LLM_CONFIG = "INVALID_LLM_CONFIG"

class ContrastApiClient:
    """
    Client for interacting with the Contrast Security API.
    This class encapsulates all API calls to Contrast.
    """
    
    def __init__(self, host, org_id, app_id, auth_key, api_key, user_agent):
        """
        Initialize the Contrast API client with required credentials.
        
        Args:
            host: The Contrast Security host URL
            org_id: The organization ID
            app_id: The application ID
            auth_key: The Contrast authorization key
            api_key: The Contrast API key
            user_agent: User agent string to identify the client
        """
        self.host = self._normalize_host(host)
        self.org_id = org_id
        self.app_id = app_id
        self.auth_key = auth_key
        self.api_key = api_key
        self.user_agent = user_agent
        
    def _normalize_host(self, host):
        """Remove any protocol prefix from host to prevent double prefixing when constructing URLs."""
        return host.replace('https://', '').replace('http://', '')
        
    def _get_headers(self):
        """Generate standard headers for API calls."""
        return {
            "Authorization": self.auth_key,
            "API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.user_agent
        }
        
    def get_vulnerability_with_prompts(self, max_open_prs, github_repo_url, vulnerability_severities):
        """
        Fetches a vulnerability to process along with pre-populated prompt templates.
        
        Args:
            max_open_prs: Maximum number of open PRs allowed
            github_repo_url: The GitHub repository URL
            vulnerability_severities: List of severity levels to filter by
        
        Returns:
            dict: Contains vulnerability data and prompts, or None if no vulnerability found or error occurred
        """
        debug_log("\n--- Fetching vulnerability and prompts from prompt-details API ---")
        
        api_url = f"https://{self._normalize_host(self.host)}/api/v4/aiml-remediation/organizations/{self.org_id}/applications/{self.app_id}/prompt-details"
        debug_log(f"API URL: {api_url}")
        
        headers = self._get_headers()
        
        # Prepare the payload
        from pathlib import Path
        import os
        repo_root = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
        
        payload = {
            "teamserverHost": f"https://{self._normalize_host(self.host)}",
            "repoRootDir": str(repo_root),
            "repoUrl": github_repo_url,
            "maxPullRequests": max_open_prs,
            "severities": vulnerability_severities
        }
        
        debug_log(f"Request payload: {json.dumps(payload, indent=2)}")
        
        try:
            debug_log(f"Making POST request to: {api_url}")
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            
            debug_log(f"Prompt-details API Response Status Code: {response.status_code}")
            
            # Handle different status codes
            if response.status_code == 204:
                log("No vulnerabilities found that need remediation (204 No Content).")
                return None
            elif response.status_code == 409:
                log("At or over the maximum PR limit (409 Conflict).")
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
                required_keys = ['remediationId', 'vulnerabilityUuid', 'vulnerabilityTitle', 'vulnerabilityRuleName', 'vulnerabilityStatus', 'vulnerabilitySeverity', 'fixSystemPrompt', 'fixUserPrompt', 'qaSystemPrompt', 'qaUserPrompt']
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
    
    def notify_remediation_pr_opened(self, remediation_id, pr_number, pr_url):
        """
        Notifies the Remediation backend service that a PR has been opened for a remediation.
        
        Args:
            remediation_id: The ID of the remediation
            pr_number: The PR number
            pr_url: The URL of the PR
            
        Returns:
            bool: True if the notification was successful, False otherwise
        """
        debug_log(f"--- Notifying Remediation service about PR for remediation {remediation_id} ---")
        api_url = f"https://{self._normalize_host(self.host)}/api/v4/aiml-remediation/organizations/{self.org_id}/applications/{self.app_id}/remediations/{remediation_id}/open"

        headers = self._get_headers()
        
        payload = {
            "pullRequestNumber": pr_number,
            "pullRequestUrl": pr_url
        }

        try:
            debug_log(f"Making PUT request to: {api_url}")
            debug_log(f"Payload: {json.dumps(payload)}")
            response = requests.put(api_url, headers=headers, json=payload)
            response.raise_for_status()

            debug_log(f"Remediation notification API response status code: {response.status_code}")
            
            if response.status_code == 204:
                debug_log(f"Successfully notified Remediation service API about PR for remediation {remediation_id}")
                return True
            else:
                error_message = "Unknown error"
                try:
                    response_json = response.json()
                    if "messages" in response_json and response_json["messages"]:
                        error_message = response_json["messages"][0]
                except:
                    error_message = response.text
                    
                log(f"Failed to notify Remediation service about PR for remediation {remediation_id}. Error: {error_message}", is_error=True)
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
    
    def notify_remediation_pr_merged(self, remediation_id):
        """
        Notifies the Remediation backend service that a PR has been merged for a remediation.
        
        Args:
            remediation_id: The ID of the remediation
            
        Returns:
            bool: True if the notification was successful, False otherwise
        """
        debug_log(f"--- Notifying Remediation service about merged PR for remediation {remediation_id} ---")
        api_url = f"https://{self._normalize_host(self.host)}/api/v4/aiml-remediation/organizations/{self.org_id}/applications/{self.app_id}/remediations/{remediation_id}/merged"

        headers = self._get_headers()

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
                except:
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
    
    def notify_remediation_pr_closed(self, remediation_id):
        """
        Notifies the Remediation backend service that a PR has been closed without merging.
        
        Args:
            remediation_id: The ID of the remediation
            
        Returns:
            bool: True if the notification was successful, False otherwise
        """
        debug_log(f"--- Notifying Remediation service about closed PR for remediation {remediation_id} ---")
        api_url = f"https://{self._normalize_host(self.host)}/api/v4/aiml-remediation/organizations/{self.org_id}/applications/{self.app_id}/remediations/{remediation_id}/closed"

        headers = self._get_headers()

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
                except:
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
    
    def notify_remediation_failed(self, remediation_id, failure_category):
        """
        Notifies the Remediation backend service that a remediation has failed.
        
        Args:
            remediation_id: The ID of the remediation
            failure_category: The category of failure
            
        Returns:
            bool: True if the notification was successful, False otherwise
        """
        debug_log(f"--- Notifying Remediation service about failed remediation {remediation_id} with category {failure_category} ---")
        api_url = f"https://{self._normalize_host(self.host)}/api/v4/aiml-remediation/organizations/{self.org_id}/applications/{self.app_id}/remediations/{remediation_id}/failed"

        headers = self._get_headers()
        
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
                except:
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
            
    def send_telemetry_data(self):
        """
        Sends the collected telemetry data to the backend.
        Retrieves telemetry data from the telemetry handler and sends it to the API.
            
        Returns:
            bool: True if sending was successful, False otherwise
        """
        debug_log("Sending telemetry data")
        
        # Get telemetry data from the telemetry handler
        telemetry_data = telemetry_handler.get_telemetry_data()
        
        if not telemetry_data:
            log("No telemetry data to send", is_warning=True)
            return False
        
        # Get remediationId from telemetry_data.additionalAttributes.remediationId
        remediation_id_for_url = telemetry_data.get("additionalAttributes", {}).get("remediationId", None)

        if not remediation_id_for_url:
            log("remediationId not found in telemetry_data.additionalAttributes. Telemetry data not sent.", is_warning=True)
            return False

        api_url = f"https://{self._normalize_host(self.host)}/api/v4/aiml-remediation/organizations/{self.org_id}/applications/{self.app_id}/remediations/{remediation_id_for_url}/telemetry"
        
        from src.config_compat import VERSION
        
        headers = {
            "Authorization": self.auth_key,
            "API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"AI SmartFix {VERSION}"  # Use specific User-Agent
        }

        debug_log(f"Sending telemetry data to: {api_url}")
        # Avoid logging full telemetry data to prevent sensitive info leakage

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
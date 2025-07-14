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

# Re-export the failure category enum for compatibility
from src.contrast_api import FailureCategory
import src.contrast_api as legacy_contrast_api

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
        # For Phase 1, we'll call the existing function
        return legacy_contrast_api.get_vulnerability_with_prompts(
            self.host,
            self.org_id, 
            self.app_id, 
            self.auth_key, 
            self.api_key, 
            max_open_prs, 
            github_repo_url, 
            vulnerability_severities
        )
    
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
        # For Phase 1, we'll call the existing function
        return legacy_contrast_api.notify_remediation_pr_opened(
            remediation_id,
            pr_number,
            pr_url,
            self.host,
            self.org_id,
            self.app_id,
            self.auth_key,
            self.api_key
        )
    
    def notify_remediation_pr_merged(self, remediation_id):
        """
        Notifies the Remediation backend service that a PR has been merged for a remediation.
        
        Args:
            remediation_id: The ID of the remediation
            
        Returns:
            bool: True if the notification was successful, False otherwise
        """
        # For Phase 1, we'll call the existing function
        return legacy_contrast_api.notify_remediation_pr_merged(
            remediation_id,
            self.host,
            self.org_id,
            self.app_id,
            self.auth_key,
            self.api_key
        )
    
    def notify_remediation_pr_closed(self, remediation_id):
        """
        Notifies the Remediation backend service that a PR has been closed without merging.
        
        Args:
            remediation_id: The ID of the remediation
            
        Returns:
            bool: True if the notification was successful, False otherwise
        """
        # For Phase 1, we'll call the existing function
        return legacy_contrast_api.notify_remediation_pr_closed(
            remediation_id,
            self.host,
            self.org_id,
            self.app_id,
            self.auth_key,
            self.api_key
        )
    
    def notify_remediation_failed(self, remediation_id, failure_category):
        """
        Notifies the Remediation backend service that a remediation has failed.
        
        Args:
            remediation_id: The ID of the remediation
            failure_category: The category of failure
            
        Returns:
            bool: True if the notification was successful, False otherwise
        """
        # For Phase 1, we'll call the existing function
        return legacy_contrast_api.notify_remediation_failed(
            remediation_id,
            failure_category,
            self.host,
            self.org_id,
            self.app_id,
            self.auth_key,
            self.api_key
        )
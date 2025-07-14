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
import sys
import json
from pathlib import Path
from typing import Optional, Any, List
from src.utils import debug_log, log

class SmartFixConfig:
    """
    Configuration manager for Contrast AI SmartFix.
    Handles loading, validating, and accessing configuration values.
    """
    
    # Preset values
    VERSION = "v1.0.6"
    USER_AGENT = f"contrast-smart-fix {VERSION}"
    VALID_SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NOTE"]
    
    def __init__(self, env_vars=None):
        """
        Initialize the configuration manager.
        
        Args:
            env_vars: Optional dictionary of environment variables (for testing)
        """
        self.env_vars = env_vars or os.environ
        self._load_config()
    
    def _get_env_var(self, var_name: str, required: bool = True, default: Optional[Any] = None) -> Optional[str]:
        """Gets an environment variable or exits if required and not found."""
        value = self.env_vars.get(var_name)
        if required and not value:
            log(f"Error: Required environment variable {var_name} is not set.", is_error=True)
            sys.exit(1)
        return value if value else default
        
    def _load_config(self):
        """Loads all configuration from environment variables."""
        
        # --- Core Settings ---
        self.debug_mode = self._get_env_var("DEBUG_MODE", required=False, default="false").lower() == "true"
        self.base_branch = self._get_env_var("BASE_BRANCH", required=True, default=None)
        self.run_task = self._get_env_var("RUN_TASK", required=False, default="generate_fix")
        
        # --- Build and Formatting Configuration ---
        self.is_generate_fix_task = self.run_task == "generate_fix"
        if self.is_generate_fix_task:
            debug_log("Running in generate_fix mode - BUILD_COMMAND is required")
        else:
            debug_log(f"Running in {self.run_task} mode - BUILD_COMMAND and FORMATTING_COMMAND are not required")
        
        self.build_command = self._get_env_var("BUILD_COMMAND", required=self.is_generate_fix_task, default=None)
        self.formatting_command = self._get_env_var("FORMATTING_COMMAND", required=False, default=None)
        
        # --- Validated and normalized settings ---
        self.max_qa_attempts = self._get_max_qa_attempts()
        self.max_open_prs = self._get_max_open_prs()
        self.max_events_per_agent = self._get_max_events_per_agent()
        
        # --- GitHub Configuration ---
        self.github_token = self._get_env_var("GITHUB_TOKEN", required=True)
        self.github_repository = self._get_env_var("GITHUB_REPOSITORY")
        
        # --- Contrast API Configuration ---
        self.contrast_host = self._get_env_var("CONTRAST_HOST", required=True)
        self.contrast_org_id = self._get_env_var("CONTRAST_ORG_ID", required=True)
        self.contrast_app_id = self._get_env_var("CONTRAST_APP_ID", required=True)
        self.contrast_authorization_key = self._get_env_var("CONTRAST_AUTHORIZATION_KEY", required=True)
        self.contrast_api_key = self._get_env_var("CONTRAST_API_KEY", required=True)
        
        # --- AI Agent Configuration ---
        self.agent_model = self._get_env_var("AGENT_MODEL", required=False, default="bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0")
        
        # --- Test Writing Configuration ---
        self.skip_writing_security_test = self._get_env_var("SKIP_WRITING_SECURITY_TEST", required=False, default="false").lower() == "true"
        
        # --- QA Configuration ---
        self.skip_qa_review = self._get_env_var("SKIP_QA_REVIEW", required=False, default="false").lower() == "true"
        
        # --- Telemetry Configuration ---
        self.enable_full_telemetry = self._get_env_var("ENABLE_FULL_TELEMETRY", required=False, default="true").lower() == "true"
        
        # --- Vulnerability Configuration ---
        self.vulnerability_severities = self._parse_and_validate_severities(
            self._get_env_var("VULNERABILITY_SEVERITIES", required=False, default='["CRITICAL", "HIGH"]')
        )
        
        # --- Paths ---
        self.script_dir = Path(__file__).parent.parent.resolve()
        self.repo_root = Path(self._get_env_var("GITHUB_WORKSPACE", required=True)).resolve()
        
        # Debug logs for configuration
        debug_log(f"Repository Root: {self.repo_root}")
        debug_log(f"Script Directory: {self.script_dir}")
        debug_log(f"Debug Mode: {self.debug_mode}")
        debug_log(f"Base Branch: {self.base_branch}")
        debug_log(f"Run Task: {self.run_task}")
        debug_log(f"Agent Model: {self.agent_model}")
        debug_log(f"Skip Writing Security Test: {self.skip_writing_security_test}")
        debug_log(f"Skip QA Review: {self.skip_qa_review}") 
        debug_log(f"Vulnerability Severities: {self.vulnerability_severities}")
        debug_log(f"Max Events Per Agent: {self.max_events_per_agent}")
        debug_log(f"Enable Full Telemetry: {self.enable_full_telemetry}")
    
    def _get_max_qa_attempts(self) -> int:
        """Validates and normalizes the MAX_QA_ATTEMPTS setting."""
        default_max_attempts = 6
        hard_cap_attempts = 10
        try:
            max_attempts_from_env = int(self._get_env_var("MAX_QA_ATTEMPTS", required=False, default="6"))
            # Apply the hard cap
            max_qa_attempts = min(max_attempts_from_env, hard_cap_attempts)
            if max_attempts_from_env > hard_cap_attempts:
                log(f"MAX_QA_ATTEMPTS ({max_attempts_from_env}) exceeded hard cap ({hard_cap_attempts}). Using {hard_cap_attempts}.", is_warning=True)
            else:
                debug_log(f"Using MAX_QA_ATTEMPTS from config: {max_qa_attempts}")
            return max_qa_attempts
        except (ValueError, TypeError):
            log(f"Invalid MAX_QA_ATTEMPTS value. Using default: {default_max_attempts}", is_warning=True)
            return default_max_attempts
    
    def _get_max_open_prs(self) -> int:
        """Validates and normalizes the MAX_OPEN_PRS setting."""
        default_max_open_prs = 5
        try:
            max_open_prs = int(self._get_env_var("MAX_OPEN_PRS", required=False, default="5"))
            if max_open_prs < 0:  # Ensure non-negative
                max_open_prs = default_max_open_prs
                log(f"MAX_OPEN_PRS was negative, using default: {default_max_open_prs}", is_warning=True)
            else:
                debug_log(f"Using MAX_OPEN_PRS from environment: {max_open_prs}")
            return max_open_prs
        except (ValueError, TypeError):
            log(f"Invalid or missing MAX_OPEN_PRS environment variable. Using default: {default_max_open_prs}", is_warning=True)
            return default_max_open_prs
    
    def _get_max_events_per_agent(self) -> int:
        """Validates and normalizes the MAX_EVENTS_PER_AGENT setting."""
        default_max_events = 120
        try:
            max_events = int(self._get_env_var("MAX_EVENTS_PER_AGENT", required=False, default="120"))
            if max_events < 10:  # Ensure it's at least 10 to allow for minimal agent operation
                log(f"MAX_EVENTS_PER_AGENT ({max_events}) is too low. Using minimum value: 10", is_warning=True)
                return 10
            elif max_events > 500:
                log(f"MAX_EVENTS_PER_AGENT ({max_events}) is too high. Using maximum value: 500", is_warning=True)
                return 500
            else:
                debug_log(f"Using MAX_EVENTS_PER_AGENT from environment: {max_events}")
                return max_events
        except (ValueError, TypeError):
            log(f"Invalid or missing MAX_EVENTS_PER_AGENT environment variable. Using default: {default_max_events}", is_warning=True)
            return default_max_events
    
    def _parse_and_validate_severities(self, json_str: Optional[str]) -> List[str]:
        """Parse and validate vulnerability severity levels from a JSON string."""
        default_severities = ["CRITICAL", "HIGH"]
        try:
            if not json_str:
                return default_severities
            
            # Parse JSON string to list
            severities = json.loads(json_str)
            
            # Ensure it's a list
            if not isinstance(severities, list):
                log(f"Vulnerability_severities must be a list, got {type(severities)}. Using default.", is_warning=True)
                return default_severities
            
            # Convert to uppercase and filter valid values
            validated = []
            for severity in severities:
                severity_upper = str(severity).upper()
                if severity_upper in self.VALID_SEVERITIES:
                    validated.append(severity_upper)
                else:
                    log(f"'{severity}' is not a valid severity level; disregarding this severity. Must be one of {self.VALID_SEVERITIES}.", is_warning=True)
            
            # Return default if no valid severities
            if not validated:
                log(f"No valid severity levels provided. Using default: {default_severities}", is_warning=True)
                return default_severities
                
            return validated
        except json.JSONDecodeError:
            log(f"Error parsing vulnerability_severities JSON: {json_str}. Using default.", is_error=True)
            return default_severities
        except Exception as e:
            log(f"Error processing vulnerability_severities: {e}. Using default.", is_error=True)
            return default_severities
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
import sys
import json
from pathlib import Path
from typing import Optional, Any
from utils import debug_log, log
import telemetry_handler

def check_contrast_config_values_exist():
    # Check for essential Contrast configuration
    if not all([CONTRAST_HOST, CONTRAST_ORG_ID, CONTRAST_APP_ID, CONTRAST_AUTHORIZATION_KEY, CONTRAST_API_KEY]):
        log("Error: Missing one or more Contrast API configuration variables (HOST, ORG_ID, APP_ID, AUTH_KEY, API_KEY).", is_error=True)
        sys.exit(1)

def get_env_var(var_name: str, required: bool = True, default: Optional[Any] = None) -> Optional[str]:
    """Gets an environment variable or exits if required and not found.
    
    Args:
        var_name: Name of the environment variable to retrieve
        required: Whether the variable is required (exits if True and not found)
        default: Default value to return if variable is not found and not required
    
    Returns:
        Value of the environment variable or default if not found and not required
        
    Exits:
        If required=True and variable not found
    """
    value = os.environ.get(var_name)
    if required and not value:
        log(f"Error: Required environment variable {var_name} is not set.", is_error=True)
        sys.exit(1)
    return value if value else default


def get_max_qa_attempts() -> int:
    """Validates and normalizes the MAX_QA_ATTEMPTS setting.
    
    Returns:
        The validated and normalized maximum number of QA attempts
    """
    default_max_attempts = 6
    hard_cap_attempts = 10
    try:
        max_attempts_from_env = int(get_env_var("MAX_QA_ATTEMPTS", required=False, default="6"))
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

def get_max_open_prs() -> int:
    """Validates and normalizes the MAX_OPEN_PRS setting.
    
    Returns:
        The validated and normalized maximum number of open PRs
    """
    default_max_open_prs = 5
    try:
        max_open_prs = int(get_env_var("MAX_OPEN_PRS", required=False, default="5"))
        if max_open_prs < 0:  # Ensure non-negative
            max_open_prs = default_max_open_prs
            log(f"MAX_OPEN_PRS was negative, using default: {default_max_open_prs}", is_warning=True)
        else:
            debug_log(f"Using MAX_OPEN_PRS from environment: {max_open_prs}")
        return max_open_prs
    except (ValueError, TypeError):
        log(f"Invalid or missing MAX_OPEN_PRS environment variable. Using default: {default_max_open_prs}", is_warning=True)
        return default_max_open_prs

def get_max_events_per_agent() -> int:
    """Validates and normalizes the MAX_EVENTS_PER_AGENT setting.
    
    Returns:
        The validated and normalized maximum number of events per agent run
    """
    default_max_events = 120
    try:
        max_events = int(get_env_var("MAX_EVENTS_PER_AGENT", required=False, default="120"))
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

# --- Preset ---
VERSION = "v1.0.4"
USER_AGENT = f"contrast-smart-fix {VERSION}"

# --- Core Settings ---
DEBUG_MODE = get_env_var("DEBUG_MODE", required=False, default="false").lower() == "true"
BASE_BRANCH = get_env_var("BASE_BRANCH", required=True, default=None)
RUN_TASK = get_env_var("RUN_TASK", required=False, default="generate_fix")

# --- Build and Formatting Configuration ---
# Only require BUILD_COMMAND if RUN_TASK is generate_fix
is_generate_fix_task = RUN_TASK == "generate_fix"
if is_generate_fix_task:
    debug_log("Running in generate_fix mode - BUILD_COMMAND is required")
else:
    debug_log(f"Running in {RUN_TASK} mode - BUILD_COMMAND and FORMATTING_COMMAND are not required")

BUILD_COMMAND = get_env_var("BUILD_COMMAND", required=is_generate_fix_task, default=None)
# FORMATTING_COMMAND is optional even in generate_fix mode
FORMATTING_COMMAND = get_env_var("FORMATTING_COMMAND", required=False, default=None)

# Validated and normalized settings
MAX_QA_ATTEMPTS = get_max_qa_attempts()
MAX_OPEN_PRS = get_max_open_prs()
MAX_EVENTS_PER_AGENT = get_max_events_per_agent()

# --- GitHub Configuration ---
GITHUB_TOKEN = get_env_var("GITHUB_TOKEN", required=True)
# GITHUB_REPOSITORY is automatically set by Actions
GITHUB_REPOSITORY = get_env_var("GITHUB_REPOSITORY")

# --- Contrast API Configuration ---
CONTRAST_HOST = get_env_var("CONTRAST_HOST", required=True)
CONTRAST_ORG_ID = get_env_var("CONTRAST_ORG_ID", required=True)
CONTRAST_APP_ID = get_env_var("CONTRAST_APP_ID", required=True)
CONTRAST_AUTHORIZATION_KEY = get_env_var("CONTRAST_AUTHORIZATION_KEY", required=True)
CONTRAST_API_KEY = get_env_var("CONTRAST_API_KEY", required=True)

# --- Anthropic Claude Credentials (LiteLLM) ---
ANTHROPIC_API_KEY = get_env_var("ANTHROPIC_API_KEY", required=False)

# --- Google Gemini Credentials (LiteLLM) ---
GEMINI_API_KEY = get_env_var("GEMINI_API_KEY", required=False)

# --- Azure Credentials for Azure OpenAI (LiteLLM) ---
AZURE_API_KEY = get_env_var("AZURE_API_KEY", required=False)
AZURE_API_BASE = get_env_var("AZURE_API_BASE", required=False)
AZURE_API_VERSION = get_env_var("AZURE_API_VERSION", required=False)

# --- AWS Bedrock Configuration ---
AWS_REGION_NAME = get_env_var("AWS_REGION_NAME", required=False)
AWS_ACCESS_KEY_ID = get_env_var("AWS_ACCESS_KEY_ID", required=False)
AWS_SECRET_ACCESS_KEY = get_env_var("AWS_SECRET_ACCESS_KEY", required=False)
AWS_SESSION_TOKEN = get_env_var("AWS_SESSION_TOKEN", required=False)
AWS_PROFILE_NAME = get_env_var("AWS_PROFILE_NAME", required=False)
AWS_ROLE_NAME = get_env_var("AWS_ROLE_NAME", required=False)
AWS_SESSION_NAME = get_env_var("AWS_SESSION_NAME", required=False)
AWS_WEB_IDENTITY_TOKEN = get_env_var("AWS_WEB_IDENTITY_TOKEN", required=False)
AWS_BEDROCK_RUNTIME_ENDPOINT = get_env_var("AWS_BEDROCK_RUNTIME_ENDPOINT", required=False)

# --- AI Agent Configuration ---
AGENT_MODEL = get_env_var("AGENT_MODEL", required=False, default="bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0")
# --- Test Writing Configuration ---
SKIP_WRITING_SECURITY_TEST = get_env_var("SKIP_WRITING_SECURITY_TEST", required=False, default="false").lower() == "true"
# --- QA Configuration ---
SKIP_QA_REVIEW = get_env_var("SKIP_QA_REVIEW", required=False, default="false").lower() == "true"

# --- Telemetry Configuration ---
ENABLE_FULL_TELEMETRY = get_env_var("ENABLE_FULL_TELEMETRY", required=False, default="true").lower() == "true"

# --- Vulnerability Configuration ---
# Define the allowlist of valid severity levels
VALID_SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NOTE"]

# Parse the severity levels from the environment variable or use default
def _parse_and_validate_severities(json_str: Optional[str]) -> list[str]:
    """Parse and validate vulnerability severity levels from a JSON string.
    
    Args:
        json_str: JSON string containing a list of severity levels
        
    Returns:
        List of validated severity levels, or default if invalid
    """
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
            if severity_upper in VALID_SEVERITIES:
                validated.append(severity_upper)
            else:
                log(f"'{severity}' is not a valid severity level; disregarding this severity. Must be one of {VALID_SEVERITIES}.", is_warning=True)
        
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

# Parse the severity levels from environment variable with a default of ["CRITICAL", "HIGH"]
VULNERABILITY_SEVERITIES = _parse_and_validate_severities(get_env_var("VULNERABILITY_SEVERITIES", required=False, default='["CRITICAL", "HIGH"]'))
# Define allowed commands/flags if using CLI MCP server (adjust as needed)
ALLOWED_COMMANDS = "ls,cat,pwd,echo,grep,mkdir"
ALLOWED_FLAGS = "-l,-a,--help,--version,-i,-r,-R,-n,-v,-c,-e,-E,-A,-B,-C,-p,--include=*.java"

# --- Paths ---
# Use GITHUB_WORKSPACE environment variable which is automatically set by GitHub Actions
# to point to the repository root, regardless of where the action code is located
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = Path(get_env_var("GITHUB_WORKSPACE", required=True)).resolve()

debug_log(f"Repository Root: {REPO_ROOT}")
debug_log(f"Script Directory: {SCRIPT_DIR}")
debug_log(f"Debug Mode: {DEBUG_MODE}")
debug_log(f"Base Branch: {BASE_BRANCH}")
debug_log(f"Run Task: {RUN_TASK}")
debug_log(f"Agent Model: {AGENT_MODEL}")
debug_log(f"Skip Writing Security Test: {SKIP_WRITING_SECURITY_TEST}")
debug_log(f"Skip QA Review: {SKIP_QA_REVIEW}") # Added debug print
debug_log(f"AWS Region Name: {AWS_REGION_NAME}")
debug_log(f"Vulnerability Severities: {VULNERABILITY_SEVERITIES}")
debug_log(f"Max Events Per Agent: {MAX_EVENTS_PER_AGENT}")
debug_log(f"Enable Full Telemetry: {ENABLE_FULL_TELEMETRY}")
if AWS_SESSION_TOKEN:
    debug_log("AWS Session Token found.")

telemetry_handler.initialize_telemetry() # Initialize telemetry at the start

# %%

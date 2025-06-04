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
from src.utils import debug_print # Corrected import to be from src.utils
from src.message_prefixes import MessagePrefix # Added import

# --- Pre-defined module constants (can be defined before load_and_validate_config) ---
VALID_SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NOTE"]
SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = (SCRIPT_DIR / "../../../").resolve() # Assumes script is in .github/actions/contrast-ai-smartfix

# --- Placeholder module-level config variables ---
# These will be populated by load_and_validate_config()
DEBUG_MODE = None
BASE_BRANCH = None
BUILD_COMMAND = None
MAX_BUILD_ATTEMPTS = None
FORMATTING_COMMAND = None
MAX_OPEN_PRS = None
GITHUB_TOKEN = None
GITHUB_REPOSITORY = None # This one is critical and read early by GitHub Actions
CONTRAST_HOST = None
CONTRAST_ORG_ID = None
CONTRAST_APP_ID = None
CONTRAST_AUTHORIZATION_KEY = None
CONTRAST_API_KEY = None
AWS_REGION = None
AWS_ACCESS_KEY_ID = None
AWS_SECRET_ACCESS_KEY = None
AWS_SESSION_TOKEN = None
AGENT_MODEL = None
ATTEMPT_WRITING_SECURITY_TEST = None
SKIP_QA_REVIEW = None
SKIP_COMMENTS = None
VULNERABILITY_SEVERITIES = None
ALLOWED_COMMANDS = None
ALLOWED_FLAGS = None


def get_env_var(var_name, required=True, default=None):
    """Gets an environment variable or exits if required and not found."""
    value = os.environ.get(var_name)
    if required and not value and default is None: # Adjusted condition to allow default for required vars
        print(f"{MessagePrefix.ERROR.value}Required environment variable {var_name} is not set.", file=sys.stderr)
        sys.exit(1)
    return value if value else default

# --- Vulnerability Configuration ---
# Parse the severity levels from the environment variable or use default
def _parse_and_validate_severities(json_str):
    default_severities = ["CRITICAL", "HIGH"]
    try:
        if not json_str:
            return default_severities
        
        # Parse JSON string to list
        severities = json.loads(json_str)
        
        # Ensure it's a list
        if not isinstance(severities, list):
            print(f"{MessagePrefix.WARNING.value}vulnerability_severities must be a list, got {type(severities)}. Using default.", file=sys.stderr)
            return default_severities
        
        # Convert to uppercase and filter valid values
        validated = []
        for severity in severities:
            severity_upper = str(severity).upper()
            if severity_upper in VALID_SEVERITIES:
                validated.append(severity_upper)
            else:
                print(f"{MessagePrefix.WARNING.value}'{severity}' is not a valid severity level. Must be one of {VALID_SEVERITIES}.", file=sys.stderr)
        
        # Return default if no valid severities
        if not validated:
            print(f"{MessagePrefix.WARNING.value}No valid severity levels provided. Using default: {default_severities}", file=sys.stderr)
            return default_severities
            
        return validated
    except json.JSONDecodeError:
        print(f"{MessagePrefix.ERROR.value}Parsing vulnerability_severities JSON: {json_str}. Using default.", file=sys.stderr)
        return default_severities
    except Exception as e:
        print(f"{MessagePrefix.ERROR.value}Processing vulnerability_severities: {e}. Using default.", file=sys.stderr)
        return default_severities

def load_and_validate_config():
    """Loads all configuration from environment variables and validates them."""
    global DEBUG_MODE, BASE_BRANCH, BUILD_COMMAND, MAX_BUILD_ATTEMPTS, FORMATTING_COMMAND, MAX_OPEN_PRS
    global GITHUB_TOKEN, GITHUB_REPOSITORY, CONTRAST_HOST, CONTRAST_ORG_ID, CONTRAST_APP_ID
    global CONTRAST_AUTHORIZATION_KEY, CONTRAST_API_KEY, AWS_REGION, AWS_ACCESS_KEY_ID
    global AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN, AGENT_MODEL, ATTEMPT_WRITING_SECURITY_TEST
    global SKIP_QA_REVIEW, SKIP_COMMENTS, VULNERABILITY_SEVERITIES, ALLOWED_COMMANDS, ALLOWED_FLAGS

    # --- Core Settings ---
    # GITHUB_REPOSITORY is critical and often set by the environment directly.
    # It's used by other actions/systems, so we ensure it's loaded.
    # However, its absence should be caught by get_env_var if it's truly required at load time.
    GITHUB_REPOSITORY = get_env_var("GITHUB_REPOSITORY", required=True) # Explicitly mark as required

    DEBUG_MODE = get_env_var("DEBUG_MODE", required=False, default="false").lower() == "true"
    BASE_BRANCH = get_env_var("BASE_BRANCH", required=False, default="main")

    # --- Build and Formatting Configuration ---
    BUILD_COMMAND = get_env_var("BUILD_COMMAND", required=False, default="mvn clean install")
    # MAX_BUILD_ATTEMPTS and MAX_OPEN_PRS will be strings as per current get_env_var
    # If they need to be integers, conversion should happen here or where they are used.
    # For now, sticking to the provided get_env_var logic.
    raw_max_build_attempts = get_env_var("MAX_BUILD_ATTEMPTS", required=False, default="6")
    try:
        MAX_BUILD_ATTEMPTS = int(raw_max_build_attempts)
    except ValueError:
        print(f"{MessagePrefix.ERROR.value}Invalid value for MAX_BUILD_ATTEMPTS: '{raw_max_build_attempts}'. Must be an integer.", file=sys.stderr)
        sys.exit(1)

    FORMATTING_COMMAND = get_env_var("FORMATTING_COMMAND", required=False, default="mvn spotless:apply")
    raw_max_open_prs = get_env_var("MAX_OPEN_PRS", required=False, default="5")
    try:
        MAX_OPEN_PRS = int(raw_max_open_prs)
    except ValueError:
        print(f"{MessagePrefix.ERROR.value}Invalid value for MAX_OPEN_PRS: '{raw_max_open_prs}'. Must be an integer.", file=sys.stderr)
        sys.exit(1)


    # --- GitHub Configuration ---
    GITHUB_TOKEN = get_env_var("GITHUB_TOKEN", required=True) # Explicitly mark as required

    # --- Contrast API Configuration ---
    CONTRAST_HOST = get_env_var("CONTRAST_HOST", required=True)
    CONTRAST_ORG_ID = get_env_var("CONTRAST_ORG_ID", required=True)
    CONTRAST_APP_ID = get_env_var("CONTRAST_APP_ID", required=True)
    CONTRAST_AUTHORIZATION_KEY = get_env_var("CONTRAST_AUTHORIZATION_KEY", required=True)
    CONTRAST_API_KEY = get_env_var("CONTRAST_API_KEY", required=True)

    # --- AWS Bedrock Configuration ---
    AWS_REGION = get_env_var("AWS_REGION", required=False)
    AWS_ACCESS_KEY_ID = get_env_var("AWS_ACCESS_KEY_ID", required=False)
    AWS_SECRET_ACCESS_KEY = get_env_var("AWS_SECRET_ACCESS_KEY", required=False)
    AWS_SESSION_TOKEN = get_env_var("AWS_SESSION_TOKEN", required=False) # Optional

    # --- AI Agent Configuration ---
    AGENT_MODEL = get_env_var("AGENT_MODEL", required=False, default="bedrock/anthropic.claude-3-7-sonnet-20250219-v1:0")
    # --- Test Writing Configuration ---
    ATTEMPT_WRITING_SECURITY_TEST = get_env_var("ATTEMPT_WRITING_SECURITY_TEST", required=False, default="false").lower() == "true"
    # --- QA Configuration ---
    SKIP_QA_REVIEW = get_env_var("SKIP_QA_REVIEW", required=False, default="true").lower() == "true"
    SKIP_COMMENTS = get_env_var("SKIP_COMMENTS", required=False, default="false").lower() == "true"

    # --- Vulnerability Configuration ---
    VULNERABILITY_SEVERITIES = _parse_and_validate_severities(get_env_var("VULNERABILITY_SEVERITIES", required=False, default='["CRITICAL", "HIGH"]'))
    
    # Define allowed commands/flags if using CLI MCP server (adjust as needed)
    ALLOWED_COMMANDS = "ls,cat,pwd,echo,grep,mkdir" # Example, keep as is or make configurable
    ALLOWED_FLAGS = "-l,-a,--help,--version,-i,-r,-R,-n,-v,-c,-e,-E,-A,-B,-C,-p,--include=*.java" # Example

    # --- Bedrock specific checks (example) ---
    if AGENT_MODEL and AGENT_MODEL.startswith("bedrock/"):
        if not AWS_REGION or not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
            print(f"{MessagePrefix.ERROR.value}Bedrock agent model ('{AGENT_MODEL}') requires AWS_REGION, AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY to be set.", file=sys.stderr)
            sys.exit(1)

    # --- Debug Prints ---
    # SCRIPT_DIR and REPO_ROOT are already defined at module level
    debug_print(f"{MessagePrefix.DEBUG.value}Repository Root: {REPO_ROOT}")
    debug_print(f"{MessagePrefix.DEBUG.value}Script Directory: {SCRIPT_DIR}")
    debug_print(f"{MessagePrefix.DEBUG.value}Debug Mode: {DEBUG_MODE}")
    debug_print(f"{MessagePrefix.DEBUG.value}Base Branch: {BASE_BRANCH}")
    debug_print(f"{MessagePrefix.DEBUG.value}Agent Model: {AGENT_MODEL}")
    debug_print(f"{MessagePrefix.DEBUG.value}Attempt Writing Security Test: {ATTEMPT_WRITING_SECURITY_TEST}")
    debug_print(f"{MessagePrefix.DEBUG.value}Skip QA Review: {SKIP_QA_REVIEW}")
    debug_print(f"{MessagePrefix.DEBUG.value}Skip Comments: {SKIP_COMMENTS}")
    debug_print(f"{MessagePrefix.DEBUG.value}AWS Region: {AWS_REGION}")
    debug_print(f"{MessagePrefix.DEBUG.value}Vulnerability Severities: {VULNERABILITY_SEVERITIES}")
    if AWS_SESSION_TOKEN:
        debug_print(f"{MessagePrefix.DEBUG.value}AWS Session Token found.")

# The lines below that were previously at module level are now inside load_and_validate_config()
# or are defined as constants above.
# Example: GITHUB_TOKEN = get_env_var("GITHUB_TOKEN") is now inside the function.

# Note: This script no longer automatically loads config on import.
# The main application entry point (e.g., main.py) should call load_and_validate_config().

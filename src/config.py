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
from utils import debug_print # Import debug_print

def get_env_var(var_name, required=True, default=None):
    """Gets an environment variable or exits if required and not found."""
    value = os.environ.get(var_name)
    if required and not value:
        print(f"Error: Required environment variable {var_name} is not set.", file=sys.stderr)
        sys.exit(1)
    return value if value else default

# --- Core Settings ---
DEBUG_MODE = get_env_var("DEBUG_MODE", required=False, default="false").lower() == "true"
BASE_BRANCH = get_env_var("BASE_BRANCH", required=False, default="main")

# --- Build and Formatting Configuration ---
BUILD_COMMAND = get_env_var("BUILD_COMMAND", required=True, default=None)
MAX_QA_ATTEMPTS = get_env_var("MAX_QA_ATTEMPTS", required=False, default="6")
FORMATTING_COMMAND = get_env_var("FORMATTING_COMMAND", required=True, default=None)
MAX_OPEN_PRS = get_env_var("MAX_OPEN_PRS", required=False, default="5")

# --- GitHub Configuration ---
GITHUB_TOKEN = get_env_var("GITHUB_TOKEN")
# GITHUB_REPOSITORY is automatically set by Actions
GITHUB_REPOSITORY = get_env_var("GITHUB_REPOSITORY")

# --- Contrast API Configuration ---
CONTRAST_HOST = get_env_var("CONTRAST_HOST")
CONTRAST_ORG_ID = get_env_var("CONTRAST_ORG_ID")
CONTRAST_APP_ID = get_env_var("CONTRAST_APP_ID")
CONTRAST_AUTHORIZATION_KEY = get_env_var("CONTRAST_AUTHORIZATION_KEY")
CONTRAST_API_KEY = get_env_var("CONTRAST_API_KEY")

# --- AWS Bedrock Configuration ---
AWS_REGION = get_env_var("AWS_REGION", required=False)
AWS_ACCESS_KEY_ID = get_env_var("AWS_ACCESS_KEY_ID", required=False)
AWS_SECRET_ACCESS_KEY = get_env_var("AWS_SECRET_ACCESS_KEY", required=False)
AWS_SESSION_TOKEN = get_env_var("AWS_SESSION_TOKEN", required=False) # Optional

# --- AI Agent Configuration ---
AGENT_MODEL = get_env_var("AGENT_MODEL", required=False, default="bedrock/anthropic.claude-3-7-sonnet-20250219-v1:0")
# --- Test Writing Configuration ---
SKIP_WRITING_SECURITY_TEST = get_env_var("SKIP_WRITING_SECURITY_TEST", required=False, default="false").lower() == "true"
# --- QA Configuration ---
SKIP_QA_REVIEW = get_env_var("SKIP_QA_REVIEW", required=False, default="true").lower() == "true"
SKIP_COMMENTS = get_env_var("SKIP_COMMENTS", required=False, default="false").lower() == "true"

# --- Vulnerability Configuration ---
# Define the allowlist of valid severity levels
VALID_SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NOTE"]

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
            print(f"Warning: vulnerability_severities must be a list, got {type(severities)}. Using default.", file=sys.stderr)
            return default_severities
        
        # Convert to uppercase and filter valid values
        validated = []
        for severity in severities:
            severity_upper = str(severity).upper()
            if severity_upper in VALID_SEVERITIES:
                validated.append(severity_upper)
            else:
                print(f"Warning: '{severity}' is not a valid severity level. Must be one of {VALID_SEVERITIES}.", file=sys.stderr)
        
        # Return default if no valid severities
        if not validated:
            print(f"Warning: No valid severity levels provided. Using default: {default_severities}", file=sys.stderr)
            return default_severities
            
        return validated
    except json.JSONDecodeError:
        print(f"Error parsing vulnerability_severities JSON: {json_str}. Using default.", file=sys.stderr)
        return default_severities
    except Exception as e:
        print(f"Error processing vulnerability_severities: {e}. Using default.", file=sys.stderr)
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

debug_print(f"Repository Root: {REPO_ROOT}")
debug_print(f"Script Directory: {SCRIPT_DIR}")
debug_print(f"Debug Mode: {DEBUG_MODE}")
debug_print(f"Base Branch: {BASE_BRANCH}")
debug_print(f"Agent Model: {AGENT_MODEL}")
debug_print(f"Skip Writing Security Test: {SKIP_WRITING_SECURITY_TEST}")
debug_print(f"Skip QA Review: {SKIP_QA_REVIEW}") # Added debug print
debug_print(f"Skip Comments: {SKIP_COMMENTS}")
debug_print(f"AWS Region: {AWS_REGION}")
debug_print(f"Vulnerability Severities: {VULNERABILITY_SEVERITIES}")
if AWS_SESSION_TOKEN:
    debug_print("AWS Session Token found.")

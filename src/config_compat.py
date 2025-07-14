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

"""
Compatibility layer for legacy code that expects global config variables.
This module creates global variables that match the names expected by legacy code,
but sources their values from the new SmartFixConfig class.
"""

import os
from src.config.smart_fix_config import SmartFixConfig

# Create a singleton instance of SmartFixConfig
_config_instance = SmartFixConfig()

# Re-export all configuration as global variables for backwards compatibility
VERSION = _config_instance.VERSION
USER_AGENT = _config_instance.USER_AGENT
DEBUG_MODE = _config_instance.debug_mode
BASE_BRANCH = _config_instance.base_branch
RUN_TASK = _config_instance.run_task

BUILD_COMMAND = _config_instance.build_command
FORMATTING_COMMAND = _config_instance.formatting_command

MAX_QA_ATTEMPTS = _config_instance.max_qa_attempts
MAX_OPEN_PRS = _config_instance.max_open_prs
MAX_EVENTS_PER_AGENT = _config_instance.max_events_per_agent

GITHUB_TOKEN = _config_instance.github_token
GITHUB_REPOSITORY = _config_instance.github_repository

CONTRAST_HOST = _config_instance.contrast_host
CONTRAST_ORG_ID = _config_instance.contrast_org_id
CONTRAST_APP_ID = _config_instance.contrast_app_id
CONTRAST_AUTHORIZATION_KEY = _config_instance.contrast_authorization_key
CONTRAST_API_KEY = _config_instance.contrast_api_key

AGENT_MODEL = _config_instance.agent_model
SKIP_WRITING_SECURITY_TEST = _config_instance.skip_writing_security_test
SKIP_QA_REVIEW = _config_instance.skip_qa_review
ENABLE_FULL_TELEMETRY = _config_instance.enable_full_telemetry
VULNERABILITY_SEVERITIES = _config_instance.vulnerability_severities

SCRIPT_DIR = _config_instance.script_dir
REPO_ROOT = _config_instance.repo_root

# Function to get environment variables (for compatibility)
def get_env_var(var_name, required=True, default=None):
    """
    Compatibility function for legacy code that uses config.get_env_var.
    Delegates to the instance method of SmartFixConfig.
    """
    return _config_instance._get_env_var(var_name, required, default)
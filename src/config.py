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

import os
import sys
import json
from pathlib import Path
from typing import Optional, Any, Dict, List

from src.smartfix.config.command_validator import validate_command, CommandValidationError


def _log_config_message(message: str, is_error: bool = False, is_warning: bool = False):
    """A minimal logger for use only within the config module before full logging is set up."""
    # This function should have no dependencies on other project modules
    if is_error or is_warning:
        print(message, file=sys.stderr)
    else:
        print(message)


class ConfigurationError(Exception):
    """Custom exception for configuration errors."""
    pass


class Config:
    """
    A centralized, object-oriented class to manage all configuration settings.
    It reads from environment variables upon instantiation and provides validated
    and typed settings as attributes.
    """
    def __init__(self, env: Dict[str, str] = os.environ, testing: bool = False):
        self.env = env
        self.testing = testing

        # --- Preset ---
        self.VERSION = "v1.0.11"
        self.USER_AGENT = f"contrast-smart-fix {self.VERSION}"

        # --- Core Settings ---
        self.DEBUG_MODE = self._get_bool_env("DEBUG_MODE", default=False)

        # Check for testing flag to make BASE_BRANCH optional in tests
        if testing and "BASE_BRANCH" not in env:
            self.BASE_BRANCH = "main"  # Default for tests
        else:
            self.BASE_BRANCH = self._get_env_var("BASE_BRANCH", required=True)

        self.RUN_TASK = self._get_env_var("RUN_TASK", required=False, default="generate_fix")

        # --- AI Agent Configuration ---
        self.CODING_AGENT = self._get_coding_agent()
        from src.smartfix.shared.coding_agents import CodingAgents
        is_smartfix_coding_agent = self.CODING_AGENT == CodingAgents.SMARTFIX.name

        default_agent_model = ""
        if is_smartfix_coding_agent:
            default_agent_model = "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        self.AGENT_MODEL = self._get_env_var("AGENT_MODEL", required=False, default=default_agent_model)

        # --- Build and Formatting Configuration ---
        is_build_command_required = self.RUN_TASK == "generate_fix" and is_smartfix_coding_agent
        # Make BUILD_COMMAND optional in tests
        if testing and "BUILD_COMMAND" not in env and is_build_command_required:
            self.BUILD_COMMAND = "echo 'Test build command'"
        else:
            self.BUILD_COMMAND = self._get_env_var("BUILD_COMMAND", required=is_build_command_required)

        # Validate BUILD_COMMAND if present
        if not testing:
            self._validate_command("BUILD_COMMAND", self.BUILD_COMMAND)

        self.FORMATTING_COMMAND = self._get_env_var("FORMATTING_COMMAND", required=False)

        # Validate FORMATTING_COMMAND if present
        if not testing:
            self._validate_command("FORMATTING_COMMAND", self.FORMATTING_COMMAND)

        # --- Validated and normalized settings ---
        self.MAX_QA_ATTEMPTS = self._get_validated_int("MAX_QA_ATTEMPTS", default=6, min_val=0, max_val=10)
        self.MAX_OPEN_PRS = self._get_validated_int("MAX_OPEN_PRS", default=5, min_val=0)
        self.MAX_EVENTS_PER_AGENT = self._get_validated_int("MAX_EVENTS_PER_AGENT", default=120, min_val=10, max_val=500)

        # --- GitHub Configuration ---
        if testing:
            self.GITHUB_TOKEN = self._get_env_var("GITHUB_TOKEN", required=False, default="mock-token-for-testing")
            self.GITHUB_REPOSITORY = self._get_env_var("GITHUB_REPOSITORY", required=False, default="mock/repo-for-testing")
            self.GITHUB_SERVER_URL = self._get_env_var("GITHUB_SERVER_URL", required=False, default="https://github.com")
        else:
            self.GITHUB_TOKEN = self._get_env_var("GITHUB_TOKEN", required=True)
            self.GITHUB_REPOSITORY = self._get_env_var("GITHUB_REPOSITORY", required=True)
            # GITHUB_SERVER_URL is automatically set by GitHub Actions (e.g., https://github.com or https://mycompany.ghe.com)
            self.GITHUB_SERVER_URL = self._get_env_var("GITHUB_SERVER_URL", required=True, default="https://github.com")

        # --- Contrast API Configuration ---
        if testing:
            self.CONTRAST_HOST = self._get_env_var("CONTRAST_HOST", required=False, default="test-host")
            self.CONTRAST_ORG_ID = self._get_env_var("CONTRAST_ORG_ID", required=False, default="test-org")
            self.CONTRAST_APP_ID = self._get_env_var("CONTRAST_APP_ID", required=False, default="test-app")
            self.CONTRAST_AUTHORIZATION_KEY = self._get_env_var("CONTRAST_AUTHORIZATION_KEY", required=False, default="test-auth")
            self.CONTRAST_API_KEY = self._get_env_var("CONTRAST_API_KEY", required=False, default="test-api")
        else:
            self.CONTRAST_HOST = self._get_env_var("CONTRAST_HOST", required=True)
            self.CONTRAST_ORG_ID = self._get_env_var("CONTRAST_ORG_ID", required=True)
            self.CONTRAST_APP_ID = self._get_env_var("CONTRAST_APP_ID", required=True)
            self.CONTRAST_AUTHORIZATION_KEY = self._get_env_var("CONTRAST_AUTHORIZATION_KEY", required=True)
            self.CONTRAST_API_KEY = self._get_env_var("CONTRAST_API_KEY", required=True)

        # Only check config values in non-testing mode
        if not testing:
            self._check_contrast_config_values_exist()

        # --- Feature Flags ---
        self.SKIP_WRITING_SECURITY_TEST = self._get_bool_env("SKIP_WRITING_SECURITY_TEST", default=False)
        self.SKIP_QA_REVIEW = self._get_bool_env("SKIP_QA_REVIEW", default=False)
        self.ENABLE_FULL_TELEMETRY = self._get_bool_env("ENABLE_FULL_TELEMETRY", default=True)
        self.USE_CONTRAST_LLM = self._get_bool_env("USE_CONTRAST_LLM", default=True)
        self.ENABLE_ANTHROPIC_PROMPT_CACHING = self._get_bool_env("ENABLE_ANTHROPIC_PROMPT_CACHING", default=True)

        # Update agent model for Contrast LLM if no explicit model was set
        if (is_smartfix_coding_agent
                and self.USE_CONTRAST_LLM
                and self._get_env_var("AGENT_MODEL", required=False) is None):
            self.AGENT_MODEL = "contrast/claude-sonnet-4-5"

        # --- Vulnerability Configuration ---
        self.VULNERABILITY_SEVERITIES = self._parse_and_validate_severities(
            self._get_env_var("VULNERABILITY_SEVERITIES", required=False, default='["CRITICAL", "HIGH"]')
        )

        # --- Paths ---
        if testing:
            # For tests, default to /tmp if GITHUB_WORKSPACE not set
            self.REPO_ROOT = Path(self._get_env_var("GITHUB_WORKSPACE", required=False, default="/tmp")).resolve()
        else:
            self.REPO_ROOT = Path(self._get_env_var("GITHUB_WORKSPACE", required=True)).resolve()

        self.SCRIPT_DIR = Path(__file__).parent.resolve()

        if not testing:
            self._log_initial_settings()

    def _get_env_var(self, var_name: str, required: bool = True, default: Optional[Any] = None) -> Optional[str]:
        value = self.env.get(var_name)
        if required and not value:
            raise ConfigurationError(f"Error: Required environment variable {var_name} is not set.")
        return value if value else default

    def _get_bool_env(self, var_name: str, default: bool = False) -> bool:
        return self._get_env_var(var_name, required=False, default=str(default)).lower() == "true"

    def _get_validated_int(self, var_name: str, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
        val_str = self._get_env_var(var_name, required=False, default=str(default))
        try:
            value = int(val_str)
            if min_val is not None and value < min_val:
                _log_config_message(f"{var_name} ({value}) is below minimum ({min_val}). Using {min_val}.", is_warning=True)
                return min_val
            if max_val is not None and value > max_val:
                _log_config_message(f"{var_name} ({value}) is above maximum ({max_val}). Using {max_val}.", is_warning=True)
                return max_val
            return value
        except (ValueError, TypeError):
            _log_config_message(f"Invalid value for {var_name}. Using default: {default}", is_warning=True)
            return default

    def _check_contrast_config_values_exist(self):
        if not all([self.CONTRAST_HOST, self.CONTRAST_ORG_ID, self.CONTRAST_APP_ID, self.CONTRAST_AUTHORIZATION_KEY, self.CONTRAST_API_KEY]):
            raise ConfigurationError("Error: Missing one or more Contrast API configuration variables (HOST, ORG_ID, APP_ID, AUTH_KEY, API_KEY).")

    def _validate_command(self, var_name: str, command: Optional[str], source: str = "config") -> None:
        """
        Validate a command against the allowlist.

        Args:
            var_name: Name of the config variable (for error messages)
            command: Command string to validate (can be None)
            source: Command source, either "config" (from action.yml, trusted) or
                   "ai_detected" (generated by AI agent, requires validation).
                   Default: "config"

        Raises:
            ConfigurationError: If command fails validation

        Notes:
            - "config" source: Commands from action.yml inputs are trusted (from humans)
              and skip allowlist validation
            - "ai_detected" source: Commands generated by AI agents go through full
              allowlist validation for security
        """
        if not command:
            # Empty or None commands are allowed (handled by required flag in _get_env_var)
            return

        # Skip validation for config-sourced commands (from humans via action.yml)
        if source == "config":
            _log_config_message(
                f"{var_name} from action config (trusted source), skipping allowlist validation"
            )
            return

        # Validate AI-generated commands through allowlist
        try:
            validate_command(var_name, command)
        except CommandValidationError as e:
            # Log the validation failure for debugging
            _log_config_message(
                f"Command validation failed for {var_name}: {str(e)}",
                is_error=True
            )
            # Convert CommandValidationError to ConfigurationError
            raise ConfigurationError(str(e)) from e

    def _get_coding_agent(self) -> str:
        from src.smartfix.shared.coding_agents import CodingAgents
        coding_agent = self._get_env_var("CODING_AGENT", required=False, default="SMARTFIX")
        try:
            # Try to convert string to Enum
            CodingAgents[coding_agent.upper()]
            return coding_agent.upper()
        except (KeyError, ValueError):
            _log_config_message(
                f"Warning: Invalid CODING_AGENT '{coding_agent}'. "
                f"Must be one of {[agent.name for agent in CodingAgents]}. "
                f"Defaulting to '{CodingAgents.SMARTFIX.name}'.",
                is_warning=True
            )
            return CodingAgents.SMARTFIX.name

    def _parse_and_validate_severities(self, json_str: Optional[str]) -> List[str]:
        default_severities = ["CRITICAL", "HIGH"]
        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NOTE"]
        try:
            if not json_str:
                return default_severities

            severities = json.loads(json_str)

            if not isinstance(severities, list):
                _log_config_message(f"Vulnerability_severities must be a list, got {type(severities)}. Using default.", is_warning=True)
                return default_severities

            validated = [s.upper() for s in severities if s.upper() in valid_severities]

            if not validated:
                _log_config_message(f"No valid severity levels provided. Using default: {default_severities}", is_warning=True)
                return default_severities

            return validated
        except json.JSONDecodeError:
            _log_config_message(f"Error parsing vulnerability_severities JSON: {json_str}. Using default.", is_error=True)
            return default_severities

    def _log_initial_settings(self):
        if not self.DEBUG_MODE:
            return
        _log_config_message(f"Repository Root: {self.REPO_ROOT}")
        _log_config_message(f"Script Directory: {self.SCRIPT_DIR}")
        _log_config_message(f"Debug Mode: {self.DEBUG_MODE}")
        _log_config_message(f"Base Branch: {self.BASE_BRANCH}")
        _log_config_message(f"Run Task: {self.RUN_TASK}")
        if not self.USE_CONTRAST_LLM:
            _log_config_message(f"Agent Model: {self.AGENT_MODEL}")
        _log_config_message(f"Coding Agent: {self.CODING_AGENT}")
        _log_config_message(f"Skip Writing Security Test: {self.SKIP_WRITING_SECURITY_TEST}")
        _log_config_message(f"Skip QA Review: {self.SKIP_QA_REVIEW}")
        _log_config_message(f"Vulnerability Severities: {self.VULNERABILITY_SEVERITIES}")
        _log_config_message(f"Max Events Per Agent: {self.MAX_EVENTS_PER_AGENT}")
        _log_config_message(f"Enable Full Telemetry: {self.ENABLE_FULL_TELEMETRY}")
        _log_config_message(f"Use Contrast LLM: {self.USE_CONTRAST_LLM}")

# --- Global Singleton Instance ---
# This is the single source of truth for configuration in the application.
# It is instantiated once when the module is imported.


_config_instance: Optional[Config] = None


def get_config(testing: bool = False) -> Config:
    """
    Returns the singleton Config instance, creating it if necessary.
    This function ensures that the Config is instantiated only when first needed,
    which is crucial for testing environments where environment variables are
    patched at runtime.

    Args:
        testing: If True, uses testing defaults for missing environment variables.
                This should only be used in tests.
    """
    global _config_instance
    if _config_instance is None:
        try:
            _config_instance = Config(testing=testing)
        except ConfigurationError as e:
            _log_config_message(str(e), is_error=True)
            sys.exit(1)
        except ImportError as e:
            _log_config_message(f"A module required for configuration could not be imported: {e}", is_error=True)
            sys.exit(1)
    return _config_instance


def reset_config():
    """For testing purposes only. Resets the config singleton."""
    global _config_instance
    _config_instance = None

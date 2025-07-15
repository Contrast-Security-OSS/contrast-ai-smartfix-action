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
import subprocess
import sys
import re
import os
import platform
from pathlib import Path
from typing import Optional
# Import DEBUG_MODE from config_compat to avoid circular imports
from src.config_compat import DEBUG_MODE

# We'll use lazy imports for telemetry_handler to avoid circular imports

# Unicode to ASCII fallback mappings for Windows
UNICODE_FALLBACKS = {
    '\u274c': 'X',  # ❌ -> X
    '❌': 'X',  # ❌ -> X
    '\u2705': '',  # ✅ -> ''
    '\u2728': '*',  # ✨ -> *
    '⚠️': '!',  # ⚠️ -> !
    '🔑': '',    # 🔑 -> ''
    '🛠️': '',   # 🛠️ -> ''
    '💡': '',   # 💡 -> ''
    '🚀': '', # 🚀 -> ''
}

def safe_print(message, file=None, flush=True):
    """Safely print message, handling encoding issues on Windows."""
    try:
        print(message, file=file, flush=flush)
    except UnicodeEncodeError:
        # On Windows, replace Unicode chars with ASCII equivalents
        for unicode_char, ascii_fallback in UNICODE_FALLBACKS.items():
            message = message.replace(unicode_char, ascii_fallback)
        
        # Replace any remaining problematic Unicode characters with '?'
        if platform.system() == 'Windows':
            message = ''.join([c if ord(c) < 128 else '?' for c in message])
            
        print(message, file=file, flush=flush)

def log(message: str, is_error: bool = False, is_warning: bool = False):
    """Logs a message to telemetry and prints to stdout/stderr."""
    # Lazy import to avoid circular dependency
    try:
        import src.telemetry_handler as telemetry_handler
        telemetry_handler.add_log_message(message)
    except (ImportError, AttributeError):
        # During initial import, telemetry_handler might not be fully initialized
        pass
    if is_error:
        safe_print(message, file=sys.stderr, flush=True)
    elif is_warning:
        # Optionally, differentiate warning logs, e.g., with a prefix
        safe_print(f"WARNING: {message}", flush=True)
    else:
        safe_print(message, flush=True)

def debug_log(*args, **kwargs):
    """Prints only if DEBUG_MODE is True and logs to telemetry."""
    message = " ".join(map(str, args))
    # Log debug messages to telemetry, possibly with a DEBUG prefix or separate field if needed
    # For now, adding to the main log.
    # Lazy import to avoid circular dependency
    try:
        import src.telemetry_handler as telemetry_handler
        telemetry_handler.add_log_message(f"DEBUG: {message}")
    except (ImportError, AttributeError):
        # During initial import, telemetry_handler might not be fully initialized
        pass
    if DEBUG_MODE:
        # Use safe_print for the combined message rather than direct print of args
        safe_print(message, flush=True)

def extract_remediation_id_from_branch(branch_name: str) -> Optional[str]:
    """Extracts the remediation ID from a branch name.
    
    Args:
        branch_name: Branch name in format 'smartfix/remediation-{remediation_id}'
        
    Returns:
        str: The remediation ID if found, or None if not found
    """
    # Match smartfix/remediation-{id} format
    match = re.search(r'smartfix/remediation-([^/]+)', branch_name)
    if match:
        return match.group(1)
    return None

# Define custom exception for command errors
class CommandExecutionError(Exception):
    """Custom exception for errors during command execution."""
    def __init__(self, message, return_code, command, stdout=None, stderr=None):
        super().__init__(message)
        self.return_code = return_code
        self.command = command
        self.stdout = stdout
        self.stderr = stderr

def run_command(command, env=None, check=True):
    """
    Runs a shell command and returns its stdout.
    Prints command, stdout/stderr based on DEBUG_MODE.
    Exits on error if check=True.
    
    Args:
        command: List of command and arguments to run
        env: Optional environment variables dictionary
        check: Whether to exit on command failure
        
    Returns:
        str: Command stdout output
        
    Raises:
        SystemExit: If check=True and command fails
    """
    try:
        # Show command and options for better debugging
        options_text = f"Options: check={check}"
        if env and env.get('GITHUB_TOKEN'):
            # Don't print the actual token
            options_text += ", GITHUB_TOKEN=***"
            
        debug_log(f"::group::Running command: {' '.join(command)}")
        debug_log(f"  {options_text}")
        
        # Merge with current environment to preserve essential variables like PATH
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
            
        # Set encoding and error handling for better robustness
        process = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            errors='replace',
            check=False,  # We'll handle errors ourselves
            env=full_env
        )

        debug_log(f"  Return Code: {process.returncode}")
        if process.stdout:
            # Truncate very large stdout for readability
            stdout_text = process.stdout.strip()
            if len(stdout_text) > 1000:
                debug_log(f"  Command stdout (truncated):\n---\n{stdout_text[:500]}...\n...{stdout_text[-500:]}\n---")
            else:
                debug_log(f"  Command stdout:\n---\n{stdout_text}\n---")
                
        if process.stderr:
            # Always print stderr if it's not empty, as it often indicates warnings/errors
            stderr_text = process.stderr.strip()
            
            # Use new log function for stderr
            if process.returncode != 0:
                if len(stderr_text) > 1000:
                    log(f"  Command stderr (truncated):\n---\n{stderr_text[:500]}...\n...{stderr_text[-500:]}\n---", is_error=True)
                else:
                    log(f"  Command stderr:\n---\n{stderr_text}\n---", is_error=True)
            elif stderr_text: # Log as debug if there's stderr but command was successful
                if len(stderr_text) > 1000:
                    debug_log(f"  Command stderr (truncated):\n---\n{stderr_text[:500]}...\n...{stderr_text[-500:]}\n---")
                else:
                    debug_log(f"  Command stderr:\n---\n{stderr_text}\n---")


        if check and process.returncode != 0:
            error_message_for_log = f"Error: Command failed with return code {process.returncode}: {' '.join(command)}"
            log(error_message_for_log, is_error=True)
            error_details = process.stderr.strip() if process.stderr else "No error output available"
            log(f"Error details: {error_details}", is_error=True)
            raise CommandExecutionError(
                message=f"Command '{' '.join(command)}' failed with return code {process.returncode}.",
                return_code=process.returncode,
                command=' '.join(command),
                stdout=process.stdout.strip() if process.stdout else None,
                stderr=error_details
            )

        return process.stdout.strip() if process.stdout else "" # Return stdout or empty string
    finally:
        debug_log("::endgroup::")


def error_exit(remediation_id: str, failure_code: Optional[str] = None):
    """
    Cleans up a branch (if provided), sends telemetry, and exits with code 1.
    
    This function handles the graceful shutdown of the SmartFix workflow when an
    error occurs. It attempts to notify the Remediation service, clean up the 
    Git branch, and send telemetry data before exiting. If any step fails with an 
    exception, the function will catch it, log it, and continue with the next step.
    
    Args:
        remediation_id: The ID of the remediation that failed
        failure_code: Optional failure category code, defaults to GENERAL_FAILURE
    """
    # Local imports to avoid circular dependencies
    from src.git_handler import cleanup_branch, get_branch_name
    from src.contrast_api import notify_remediation_failed, send_telemetry_data
    # Import FailureCategory from the new API client to avoid circular imports
    from src.api.contrast_api_client import FailureCategory

    # Set default failure code if none provided
    if not failure_code:
        failure_code = FailureCategory.GENERAL_FAILURE.value

    # Import config values from config_compat to avoid circular imports
    from src.config_compat import CONTRAST_HOST, CONTRAST_ORG_ID, CONTRAST_APP_ID
    from src.config_compat import CONTRAST_AUTHORIZATION_KEY, CONTRAST_API_KEY

    # Attempt to notify remediation service - continue even if this fails
    remediation_notified = notify_remediation_failed(
        remediation_id=remediation_id,
        failure_category=failure_code,
        contrast_host=CONTRAST_HOST,
        contrast_org_id=CONTRAST_ORG_ID,
        contrast_app_id=CONTRAST_APP_ID,
        contrast_auth_key=CONTRAST_AUTHORIZATION_KEY,
        contrast_api_key=CONTRAST_API_KEY
    )

    if remediation_notified:
        log(f"Successfully notified Remediation service about {failure_code} for remediation {remediation_id}.")
    else:
        log(f"Failed to notify Remediation service about {failure_code} for remediation {remediation_id}.", is_warning=True)

    # Attempt to clean up any branches - continue even if this fails
    branch_name = get_branch_name(remediation_id)
    cleanup_branch(branch_name)

    # Always attempt to send final telemetry
    send_telemetry_data()

    # Exit with error code
    sys.exit(1)

def singleton(cls):
    instances = {}
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance
# %%

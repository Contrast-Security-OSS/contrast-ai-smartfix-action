# -
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
Build Runner Module

Handles execution of build commands and test commands for vulnerability remediation.
"""

import subprocess
from pathlib import Path
from typing import Tuple

from src.utils import debug_log, log, error_exit
import src.telemetry_handler as telemetry_handler


def run_build_command(command: str, repo_root: Path, remediation_id: str) -> Tuple[bool, str]:
    """
    Runs the specified build command in the repository root.

    Args:
        command: The build command string (e.g., "mvn clean install").
        repo_root: The Path object representing the repository root directory.
        remediation_id: Remediation ID for error tracking.

    Returns:
        A tuple containing:
        - bool: True if the command succeeded (exit code 0), False otherwise.
        - str: The combined stdout and stderr output of the command.
    """
    log(f"\n--- Running Build Command: {command} ---")
    try:
        # Use shell=True if the command might contain shell operators like &&, ||, > etc.
        # Be cautious with shell=True if the command comes from untrusted input.
        # Here, it's from an environment variable, assumed to be controlled.
        result = subprocess.run(
            command,
            cwd=repo_root,
            shell=True,
            check=False,  # Don't raise exception on non-zero exit
            capture_output=True,
            text=True,
            encoding='utf-8',  # Explicitly set encoding
            errors='replace'  # Handle potential encoding errors in output
        )
        telemetry_handler.update_telemetry("configInfo.buildCommandRunTestsIncluded", True)
        output = result.stdout + result.stderr
        if result.returncode == 0:
            log("Build command succeeded.")
            return True, output
        else:
            debug_log(f"Build command failed with exit code {result.returncode}.")

            return False, output
    except FileNotFoundError:
        log(f"Error: Build command '{command}' not found. Is it installed and in PATH?", is_error=True)
        error_exit(remediation_id)
    except Exception as e:
        log(f"An unexpected error occurred while running the build command: {e}", is_error=True)
        error_exit(remediation_id)

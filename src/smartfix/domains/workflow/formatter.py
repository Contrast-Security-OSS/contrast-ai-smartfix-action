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
Formatter Module

Handles code formatting operations for vulnerability remediation.
"""

import os
from pathlib import Path
from typing import Optional, List

from src.utils import debug_log, log, error_exit, run_command


def run_formatting_command(formatting_command: Optional[str], repo_root: Path, remediation_id: str) -> List[str]:
    """
    Runs the formatting command if provided.

    Args:
        formatting_command: The formatting command to run (or None).
        repo_root: The repository root path.
        remediation_id: Remediation ID for error tracking.

    Returns:
        List[str]: List of files changed by the formatting command, empty list if none or no command.
    """
    changed_files = []
    if not formatting_command:
        return changed_files

    log(f"\n--- Running Formatting Command: {formatting_command} ---")
    # Use shell=True to preserve shell operators like &&, ||, ; etc.
    # The command is validated by command_validator.py before reaching here.
    current_dir = os.getcwd()
    try:
        os.chdir(str(repo_root))  # Change to repo root directory
        try:
            format_output = run_command(
                formatting_command,  # Pass as string for shell=True
                check=False,  # Don't exit on failure, we'll check status
                shell=True  # Enable shell operators (&&, ||, |, ;)
            )
            format_success = True  # If no exception was raised, consider it successful
        except Exception as e:
            format_success = False
            format_output = str(e)
    finally:
        os.chdir(current_dir)  # Change back to original directory

    if format_success:
        debug_log("Formatting command successful.")
        # NOTE: Git operations are handled by main.py after all agent work completes
        # We just track which files were changed by the formatter
        # The formatter modifies files in place, so we don't need to commit here
        log("Formatting command completed.")
    else:
        log(f"::error::Error executing formatting command: {formatting_command}")
        log(f"::error::Error details: {format_output}", is_error=True)
        error_exit(remediation_id)

    return changed_files

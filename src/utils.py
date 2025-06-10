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
from pathlib import Path
from typing import Optional
import config # Import config to access DEBUG_MODE

def debug_print(*args, **kwargs):
    """Prints only if DEBUG_MODE is True."""
    if config.DEBUG_MODE:
        print(*args, **kwargs)

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
            
        debug_print(f"::group::Running command: {' '.join(command)}")
        debug_print(f"  {options_text}")
        
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

        debug_print(f"  Return Code: {process.returncode}")
        if process.stdout:
            # Truncate very large stdout for readability
            stdout_text = process.stdout.strip()
            if len(stdout_text) > 1000:
                debug_print(f"  Command stdout (truncated):\n---\n{stdout_text[:500]}...\n...{stdout_text[-500:]}\n---")
            else:
                debug_print(f"  Command stdout:\n---\n{stdout_text}\n---")
                
        if process.stderr:
            # Always print stderr if it's not empty, as it often indicates warnings/errors
            stderr_text = process.stderr.strip()
            debug_level = print if process.returncode != 0 else debug_print
            stderr_level = sys.stderr if process.returncode != 0 else None
            
            if len(stderr_text) > 1000:
                debug_level(f"  Command stderr (truncated):\n---\n{stderr_text[:500]}...\n...{stderr_text[-500:]}\n---", file=stderr_level)
            else:
                debug_level(f"  Command stderr:\n---\n{stderr_text}\n---", file=stderr_level)

        if check and process.returncode != 0:
            print(f"Error: Command failed with return code {process.returncode}: {' '.join(command)}", file=sys.stderr)
            error_msg = process.stderr.strip() if process.stderr else "No error output available"
            print(f"Error details: {error_msg}", file=sys.stderr)
            sys.exit(1)  # Exit if check is True and command failed

        return process.stdout.strip() if process.stdout else "" # Return stdout or empty string

    except FileNotFoundError:
        print(f"Error: Command not found: {command[0]}. Ensure it's installed and in the PATH.", file=sys.stderr)
        if check:
            sys.exit(1)
        return None # Indicate failure if not checking
    except Exception as e:
        print(f"An unexpected error occurred running command {' '.join(command)}: {e}", file=sys.stderr)
        if check:
            sys.exit(1)
        return None # Indicate failure if not checking
    finally:
        debug_print("::endgroup::", flush=True)



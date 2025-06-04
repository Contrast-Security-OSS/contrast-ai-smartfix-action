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
import sys # Added import
from pathlib import Path # Added import
from src.message_prefixes import MessagePrefix
# Import config_check from src to access DEBUG_MODE
from src import config_check as config

def debug_print(*args, **kwargs):
    """Prints only if DEBUG_MODE is True."""
    if config.DEBUG_MODE:
        print(MessagePrefix.DEBUG.value, *args, **kwargs)

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
        
        # Set encoding and error handling for better robustness
        process = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            errors='replace',
            check=False,  # We'll handle errors ourselves
            env=env
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
            print(f"{MessagePrefix.ERROR.value}Command failed with return code {process.returncode}: {' '.join(command)}", file=sys.stderr)
            error_msg = process.stderr.strip() if process.stderr else "No error output available"
            print(f"{MessagePrefix.ERROR.value}Error details: {error_msg}", file=sys.stderr)
            sys.exit(1)  # Exit if check is True and command failed

        return process.stdout.strip() if process.stdout else "" # Return stdout or empty string

    except FileNotFoundError:
        print(f"{MessagePrefix.ERROR.value}Command not found: {command[0]}. Ensure it's installed and in the PATH.", file=sys.stderr)
        if check:
            sys.exit(1)
        return None # Indicate failure if not checking
    except Exception as e:
        print(f"{MessagePrefix.ERROR.value}An unexpected error occurred running command {' '.join(command)}: {e}", file=sys.stderr)
        if check:
            sys.exit(1)
        return None # Indicate failure if not checking
    finally:
        debug_print("::endgroup::", flush=True)


def ensure_gitignore_ignores_script_dir(repo_root: Path, script_dir_relative: str):
    """Checks if .gitignore ignores the script directory and adds the rule if not."""
    gitignore_path = repo_root / ".gitignore"
    # Use the relative path from repo root provided
    ignore_pattern = f"{script_dir_relative}/**/*.pyc"
    pattern_found = False

    debug_print(f"Checking {gitignore_path} for ignore pattern: '{ignore_pattern}'")

    try:
        if gitignore_path.exists():
            with open(gitignore_path, "r") as f:
                for line in f:
                    if line.strip() == ignore_pattern.strip():
                        pattern_found = True
                        break
        else:
            debug_print(f"{MessagePrefix.DEBUG.value}{gitignore_path} does not exist. Creating it.")
            gitignore_path.touch()

        if not pattern_found:
            debug_print(f"{MessagePrefix.DEBUG.value}Ignore pattern '{ignore_pattern}' not found. Adding it to {gitignore_path}.")
            with open(gitignore_path, "a") as f:
                # Add a newline before the pattern if the file is not empty and doesn't end with one
                if gitignore_path.stat().st_size > 0:
                    with open(gitignore_path, 'rb+') as check_f:
                        try: # Handle potential error if file is exactly 1 byte
                            check_f.seek(-1, os.SEEK_END)
                            if check_f.read() != b'\n':
                                f.write("\n")
                        except OSError:
                             f.write("\n") # Assume newline needed if seek fails on small file

                f.write(f"\n# Ignore Contrast AI SmartFix script directory and cache\n")
                f.write(f"{ignore_pattern}\n")
            debug_print(f"{MessagePrefix.DEBUG.value}Ignore pattern added successfully.")
        else:
            debug_print(f"{MessagePrefix.DEBUG.value}Ignore pattern '{ignore_pattern}' already exists in {gitignore_path}.")

    except Exception as e:
        print(f"{MessagePrefix.WARNING.value}Failed to check or update {gitignore_path}: {e}", file=sys.stderr)
        print(f"{MessagePrefix.INFO.value}Proceeding without guaranteed .gitignore update.", file=sys.stderr)

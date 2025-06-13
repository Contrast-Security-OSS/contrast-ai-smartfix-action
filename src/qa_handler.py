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
import shlex
import subprocess
from pathlib import Path
from typing import Tuple, List, Optional

# Import configurations and utilities
import config
from utils import debug_print, run_command
import agent_handler
import git_handler

def run_build_command(command: str, repo_root: Path) -> Tuple[bool, str]:
    """
    Runs the specified build command in the repository root.

    Args:
        command: The build command string (e.g., "mvn clean install").
        repo_root: The Path object representing the repository root directory.

    Returns:
        A tuple containing:
        - bool: True if the command succeeded (exit code 0), False otherwise.
        - str: The combined stdout and stderr output of the command.
    """
    print(f"\n--- Running Build Command: {command} ---")
    try:
        # Use shell=True if the command might contain shell operators like &&, ||, > etc.
        # Be cautious with shell=True if the command comes from untrusted input.
        # Here, it's from an environment variable, assumed to be controlled.
        result = subprocess.run(
            command,
            cwd=repo_root,
            shell=True,
            check=False, # Don't raise exception on non-zero exit
            capture_output=True,
            text=True,
            encoding='utf-8', # Explicitly set encoding
            errors='replace' # Handle potential encoding errors in output
        )
        output = result.stdout + result.stderr
        if result.returncode == 0:
            print("Build command succeeded.")
            # debug_print(f"Build Output (truncated):\n---\n{output[:1000]}...\n---")
            return True, output
        else:
            debug_print(f"Build command failed with exit code {result.returncode}.")
            # debug_print(f"Build Output:\n---\n{output}\n---")
            return False, output
    except FileNotFoundError:
        print(f"Error: Build command '{command}' not found. Is it installed and in PATH?", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while running the build command: {e}", file=sys.stderr)
        sys.exit(1)

def run_formatting_command(formatting_command: Optional[str], repo_root: Path) -> List[str]:
    """
    Runs the formatting command if provided.
    
    Args:
        formatting_command: The formatting command to run (or None).
        repo_root: The repository root path.
        
    Returns:
        List[str]: List of files changed by the formatting command, empty list if none or no command.
    """
    changed_files = []
    if not formatting_command:
        return changed_files
        
    print(f"\n--- Running Formatting Command: {formatting_command} ---", flush=True)
    # Modified to match run_command signature which returns only stdout
    current_dir = os.getcwd()
    try:
        os.chdir(str(repo_root))  # Change to repo root directory
        try:
            format_output = run_command(
                formatting_command.split(),  # Split string into list for Popen
                check=False  # Don't exit on failure, we'll check status
            )
            format_success = True  # If no exception was raised, consider it successful
        except Exception as e:
            format_success = False
            format_output = str(e)
    finally:
        os.chdir(current_dir)  # Change back to original directory
    
    if format_success:
        debug_print("Formatting command successful.")
        git_handler.stage_changes()  # Stage any changes made by the formatter
        if not git_handler.check_status():  # Check if formatter made changes
            print("Formatting command ran but made no changes to commit.")
        else:
            debug_print("Formatting command made changes. Committing them.")
            git_handler.commit_changes(f"Apply formatting via: {formatting_command}")
            changed_files = git_handler.get_last_commit_changed_files()
    else:
        print(f"::error::Error executing formatting command: {formatting_command}")
        print(f"::error::Error details: {format_output}", file=sys.stderr)
        sys.exit(1)
        
    return changed_files

def run_qa_loop(
    build_command: Optional[str],
    repo_root: Path,
    max_qa_attempts: int,
    initial_changed_files: List[str],
    formatting_command: Optional[str],
    qa_system_prompt: Optional[str] = None,
    qa_user_prompt: Optional[str] = None
) -> Tuple[bool, List[str], Optional[str], List[str]]:
    """
    Runs the build and QA agent loop.

    Args:
        build_command: The build command string.
        repo_root: Path to the repository root.
        max_qa_attempts: Maximum number of QA attempts.
        initial_changed_files: List of files changed by the initial fix agent.
        formatting_command: The formatting command string.
        qa_system_prompt: The QA system prompt from API (optional).
        qa_user_prompt: The QA user prompt from API (optional).

    Returns:
        A tuple containing:
        - bool: True if the final build was successful, False otherwise.
        - List[str]: The final list of changed files (potentially updated by QA).
        - str: The build command used (or None).
        - List[str]: A log of QA summaries.
    """
    print("\n--- Starting QA Review Process ---", flush=True)
    qa_attempts = 0
    build_success = False
    build_output = "Build not run."
    changed_files = initial_changed_files[:] # Copy the list
    qa_summary_log = [] # Log QA agent summaries

    if not build_command:
        print("Skipping QA loop: No build command provided.")
        return True, changed_files, build_command, qa_summary_log # Assume success if no build command

    # Run formatting command before initial build if specified
    if formatting_command:
        formatting_changed_files = run_formatting_command(formatting_command, repo_root)
        if formatting_changed_files:
            changed_files.extend([f for f in formatting_changed_files if f not in changed_files])

    # Try initial build first
    print("\n--- Running Initial Build After Fix ---", flush=True)
    initial_build_success, initial_build_output = run_build_command(build_command, repo_root)
    build_output = initial_build_output # Store the latest output

    if initial_build_success:
        print("\n\u2705 Initial build successful after fix. No QA intervention needed.", flush=True)
        build_success = True
        return build_success, changed_files, build_command, qa_summary_log

    # If initial build failed, enter the QA loop
    print("\n\u274c Initial build failed. Starting QA agent intervention loop.", flush=True)
    
    # Analyze build failure and show error summary
    error_analysis = extract_build_errors(initial_build_output)
    print("\n--- BUILD FAILURE ANALYSIS ---")
    print(error_analysis)
    print("--- END BUILD FAILURE ANALYSIS ---\n")
    while qa_attempts < max_qa_attempts:
        qa_attempts += 1
        print(f"\n::group::---- QA Attempt #{qa_attempts}/{max_qa_attempts} ---")

        # Truncate build output if too long for the agent
        max_output_length = 15000 # Adjust as needed
        truncated_output = build_output
        if len(build_output) > max_output_length:
            truncated_output = "...build output may be cut off prior to here...\n" + build_output[-max_output_length:]

        # Run QA agent
        qa_summary = agent_handler.run_qa_agent(
            build_output=truncated_output,
            changed_files=changed_files, # Pass the current list of changed files
            build_command=build_command,
            repo_root=config.REPO_ROOT,
            formatting_command=formatting_command, # <<< ADDED
            qa_history=qa_summary_log, # Pass the history of previous QA attempts
            qa_system_prompt=qa_system_prompt, # <<< ADDED for API prompts
            qa_user_prompt=qa_user_prompt # <<< ADDED for API prompts
        )
        
        # Check if QA agent encountered an error
        if qa_summary.startswith("Error during QA agent execution:"):
            print(f"QA Agent encountered an unrecoverable error: {qa_summary}")
            print("Continuing with build process, but PR creation may be skipped.")
            # Note: The branch cleanup will be handled in main.py after checking build_success
        
        debug_print(f"QA Agent Summary: {qa_summary}")
        qa_summary_log.append(qa_summary) # Log the summary

        print("\n::endgroup::") # TODO: Needs to be in a try finally so a failure doesn't jack up the groups.

        # --- Handle QA Agent Output ---
        git_handler.stage_changes()
        if git_handler.check_status():
            git_handler.amend_commit()
            changed_files = git_handler.get_last_commit_changed_files() # Update changed files list
            print("Amended commit with QA agent fixes.")
            
            # Always run formatting command before build, if specified
            if formatting_command:
                formatting_changed_files = run_formatting_command(formatting_command, repo_root)
                if formatting_changed_files:
                    changed_files.extend([f for f in formatting_changed_files if f not in changed_files])

            # Re-run the main build command to check if the QA fix worked
            print("\n--- Re-running Build Command After QA Fix ---")
            build_success, build_output = run_build_command(build_command, repo_root)
            if build_success:
                print("\n\u2705 Build successful after QA agent fix.")
                break # Exit QA loop
            else:
                print("\n\u274c Build still failing after QA agent fix.")
                continue # Continue to next QA iteration
        else:
            print("QA agent did not request a command and made no file changes. Build still failing.")
            # Break the loop if QA agent isn't making progress
            build_success = False
            break

    if not build_success:
        print(f"\n\u274c Build failed after {qa_attempts} QA attempts.")

    return build_success, changed_files, build_command, qa_summary_log


def extract_build_errors(build_output):
    """
    Extract the most relevant error information from build output.
    
    This function captures error blocks with context before and after errors,
    and intelligently extends blocks when errors are found in sequence.
    
    Args:
        build_output: The complete output from the build command
        
    Returns:
        str: A condensed report of the most relevant error regions
    """
    # If output is small enough, just return it all
    if len(build_output) < 2000:
        return build_output
    
    lines = build_output.splitlines()
    
    # Look at the last part of the output (where errors typically appear)
    tail_lines = lines[-500:] if len(lines) > 500 else lines
    
    # Common error indicators across build systems
    error_indicators = ["error", "exception", "failed", "failure", "fatal"]
    
    # Process the lines to find error regions with their context
    context_size = 5  # Number of lines to include before an error
    error_regions = []  # Will hold start and end indices of error regions
    
    # First pass: identify all error lines
    error_line_indices = []
    for i, line in enumerate(tail_lines):
        line_lower = line.lower()
        if any(indicator in line_lower for indicator in error_indicators):
            error_line_indices.append(i)
    
    # Second pass: merge nearby errors into regions
    if error_line_indices:
        current_region_start = max(0, error_line_indices[0] - context_size)
        current_region_end = error_line_indices[0] + context_size
        
        for idx in error_line_indices[1:]:
            # If this error is within or close to current region, extend the region
            if idx - context_size <= current_region_end + 2:  # Allow small gaps
                current_region_end = idx + context_size
            else:
                # This error is far from the previous region, save current region
                # and start a new one
                error_regions.append((current_region_start, min(current_region_end, len(tail_lines) - 1)))
                current_region_start = max(0, idx - context_size)
                current_region_end = idx + context_size
        
        # Don't forget the last region
        error_regions.append((current_region_start, min(current_region_end, len(tail_lines) - 1)))
    
    # Extract the text from each error region
    error_blocks = []
    for start, end in error_regions:
        region_lines = tail_lines[start:end + 1]
        error_blocks.append("\n".join(region_lines))
    
    # If we found error blocks, return them (up to 3 most recent)
    if error_blocks:
        result_blocks = error_blocks[-3:] if len(error_blocks) > 3 else error_blocks
        return "BUILD FAILURE - KEY ERRORS:\n\n" + "\n\n...\n\n".join(result_blocks)
    
    # Fallback: just return the last part of the build output
    return "BUILD FAILURE - LAST OUTPUT:\n\n" + "\n".join(tail_lines[-50:])


# %%

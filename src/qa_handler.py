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
from pathlib import Path
from typing import Tuple, List, Optional

# Import configurations and utilities
import config
from utils import debug_log, run_command, log, error_exit
import agent_handler
import git_handler
import telemetry_handler
from build_output_analyzer import extract_build_errors

def run_build_command(command: str, repo_root: Path, new_branch_name: str) -> Tuple[bool, str]:
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
    log(f"\n--- Running Build Command: {command} ---")
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
        telemetry_handler.update_telemetry("configInfo.buildCommandRunTestsIncluded", True);
        output = result.stdout + result.stderr
        if result.returncode == 0:
            log("Build command succeeded.")
            return True, output
        else:
            debug_log(f"Build command failed with exit code {result.returncode}.")

            return False, output
    except FileNotFoundError:
        log(f"Error: Build command '{command}' not found. Is it installed and in PATH?", is_error=True)
        error_exit(new_branch_name)
    except Exception as e:
        log(f"An unexpected error occurred while running the build command: {e}", is_error=True)
        error_exit(new_branch_name)

def run_formatting_command(formatting_command: Optional[str], repo_root: Path, new_branch_name: str) -> List[str]:
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
        
    log(f"\n--- Running Formatting Command: {formatting_command} ---")
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
        debug_log("Formatting command successful.")
        git_handler.stage_changes()  # Stage any changes made by the formatter
        if not git_handler.check_status():  # Check if formatter made changes
            log("Formatting command ran but made no changes to commit.")
        else:
            debug_log("Formatting command made changes. Committing them.")
            git_handler.commit_changes(f"Apply formatting via: {formatting_command}")
            changed_files = git_handler.get_last_commit_changed_files()
    else:
        log(f"::error::Error executing formatting command: {formatting_command}")
        log(f"::error::Error details: {format_output}", is_error=True)
        error_exit(new_branch_name)
        
    return changed_files

def run_qa_loop(
    build_command: Optional[str],
    repo_root: Path,
    max_qa_attempts: int,
    initial_changed_files: List[str],
    formatting_command: Optional[str],
    new_branch_name: str,
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
    log("\n--- Starting QA Review Process ---")
    qa_attempts = 0
    build_success = False
    build_output = "Build not run."
    changed_files = initial_changed_files[:] # Copy the list
    qa_summary_log = [] # Log QA agent summaries

    if not build_command:
        log("Skipping QA loop: No build command provided.")
        return True, changed_files, build_command, qa_summary_log # Assume success if no build command

    # Run formatting command before initial build if specified
    if formatting_command:
        formatting_changed_files = run_formatting_command(formatting_command, repo_root, new_branch_name)
        if formatting_changed_files:
            changed_files.extend([f for f in formatting_changed_files if f not in changed_files])

    # Try initial build first
    log("\n--- Running Initial Build After Fix ---")
    initial_build_success, initial_build_output = run_build_command(build_command, repo_root, new_branch_name)
    build_output = initial_build_output # Store the latest output

    if initial_build_success:
        log("\n\u2705 Initial build successful after fix. No QA intervention needed.")
        telemetry_handler.update_telemetry("resultInfo.filesModified", len(changed_files))
        build_success = True
        return build_success, changed_files, build_command, qa_summary_log

    # If initial build failed, enter the QA loop
    log("\n\u274c Initial build failed. Starting QA agent intervention loop.")
    
    # Analyze build failure and show error summary
    error_analysis = extract_build_errors(initial_build_output)
    debug_log("\n--- BUILD FAILURE ANALYSIS ---")
    debug_log(error_analysis)
    debug_log("--- END BUILD FAILURE ANALYSIS ---\n")
    while qa_attempts < max_qa_attempts:
        qa_attempts += 1
        log(f"\n::group::---- QA Attempt #{qa_attempts}/{max_qa_attempts} ---")

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
            new_branch_name=new_branch_name,
            qa_history=qa_summary_log, # Pass the history of previous QA attempts
            qa_system_prompt=qa_system_prompt,
            qa_user_prompt=qa_user_prompt
        )
        
        # Check if QA agent encountered an error
        if qa_summary.startswith("Error during QA agent execution:"):
            log(f"QA Agent encountered an unrecoverable error: {qa_summary}")
            log("Continuing with build process, but PR creation may be skipped.")
            # Note: The branch cleanup will be handled in main.py after checking build_success
        
        debug_log(f"QA Agent Summary: {qa_summary}")
        qa_summary_log.append(qa_summary) # Log the summary

        # Ensure the group is closed even if errors occur later in the loop
        try:
            # --- Handle QA Agent Output ---
            git_handler.stage_changes()
            if git_handler.check_status():
                git_handler.amend_commit()
                changed_files = git_handler.get_last_commit_changed_files() # Update changed files list
                log("Amended commit with QA agent fixes.")
                
                # Always run formatting command before build, if specified
                if formatting_command:
                    formatting_changed_files = run_formatting_command(formatting_command, repo_root, new_branch_name)
                    if formatting_changed_files:
                        changed_files.extend([f for f in formatting_changed_files if f not in changed_files])
                    telemetry_handler.update_telemetry("resultInfo.filesModified", len(changed_files))

                # Re-run the main build command to check if the QA fix worked
                log("\n--- Re-running Build Command After QA Fix ---")
                build_success, build_output = run_build_command(build_command, repo_root, new_branch_name)
                if build_success:
                    log("\n\u2705 Build successful after QA agent fix.")
                    break # Exit QA loop
                else:
                    log("\n\u274c Build still failing after QA agent fix.")
                    continue # Continue to next QA iteration
            else:
                log("QA agent did not request a command and made no file changes. Build still failing.")
                # Break the loop if QA agent isn't making progress
                build_success = False
                break
        finally:
            log("\n::endgroup::") # Close the group for the QA attempt

    if not build_success:
        log(f"\n\u274c Build failed after {qa_attempts} QA attempts.")

    return build_success, changed_files, build_command, qa_summary_log
# %%

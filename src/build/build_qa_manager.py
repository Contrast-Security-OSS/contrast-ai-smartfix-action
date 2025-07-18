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

import subprocess
import os
from pathlib import Path
from typing import Tuple, List, Optional, TYPE_CHECKING
from src.utils import log, debug_log, error_exit, run_command
from src.build_output_analyzer import extract_build_errors
from src.api.contrast_api_client import FailureCategory
from src.agent.agent_interfaces import AgentRunnerInterface
from src.agent.agent_prompts import AgentPrompts

class BuildQaManager:
    """
    Manages the building and quality assurance processes of the code.
    """
    
    def __init__(self, telemetry_handler, git_handler=None):
        """
        Initialize the BuildQaManager with required components.
        
        Args:
            telemetry_handler: Handler for telemetry data collection
            git_handler: Optional GitHandler instance for git operations
        """
        self.telemetry_handler = telemetry_handler
        self.git_handler = git_handler
        
    def run_build(self, remediation_id: str, build_command: str, repo_root: str) -> Tuple[bool, str]:
        """
        Runs the build command in the repository.
        
        Args:
            remediation_id: The ID of the remediation
            build_command: The command to build the application
            repo_root: The root directory of the repository
            
        Returns:
            Tuple[bool, str]: Success status and build output
            
        Raises:
            SystemExit: On unrecoverable error
        """
        log(f"\n--- Running Build Command: {build_command} ---")
        try:
            # Use shell=True if the command might contain shell operators like &&, ||, > etc.
            # Be cautious with shell=True if the command comes from untrusted input.
            # Here, it's from an environment variable, assumed to be controlled.
            result = subprocess.run(
                build_command,
                cwd=repo_root,
                shell=True,
                check=False, # Don't raise exception on non-zero exit
                capture_output=True,
                text=True,
                encoding='utf-8', # Explicitly set encoding
                errors='replace' # Handle potential encoding errors in output
            )
            self.telemetry_handler.update_telemetry("configInfo.buildCommandRunTestsIncluded", True)
            output = result.stdout + result.stderr
            if result.returncode == 0:
                log("Build command succeeded.")
                return True, output
            else:
                debug_log(f"Build command failed with exit code {result.returncode}.")
                return False, output
        except FileNotFoundError:
            log(f"Error: Build command '{build_command}' not found. Is it installed and in PATH?", is_error=True)
            error_exit(remediation_id)
        except Exception as e:
            log(f"An unexpected error occurred while running the build command: {e}", is_error=True)
            error_exit(remediation_id)
    
    def run_formatting(self, remediation_id: str, formatting_command: str, repo_root: Path) -> List[str]:
        """
        Runs the formatting command on the repository.
        
        Args:
            remediation_id: The ID of the remediation
            formatting_command: The command to format the code
            repo_root: The root directory of the repository
            
        Returns:
            List[str]: List of files changed during formatting
            
        Raises:
            SystemExit: On unrecoverable error
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

        if format_success and self.git_handler:
            changed_files = self.git_handler.get_list_changed_files()
        elif format_success:
            # If no git_handler provided, try to get it from main.py
            try:
                from src.main import git_handler_obj
                if git_handler_obj:
                    changed_files = git_handler_obj.get_list_changed_files()
                else:
                    log("git_handler_obj not initialized. Cannot get changed files.", is_error=True)
                    changed_files = []
            except (ImportError, AttributeError):
                log("Cannot access git_handler_obj. Cannot get changed files.", is_error=True)
                changed_files = []
        else:
            log(f"::error::Error executing formatting command: {formatting_command}")
            log(f"::error::Error details: {format_output}", is_error=True)
            error_exit(remediation_id)

        return changed_files
    
    def run_qa_process(
        self,
        qa_agent_runner: AgentRunnerInterface,
        qa_agent: AgentPrompts, 
        remediation_id: str, 
        build_command: str,
        formatting_command: str,
        repo_root: Path, 
        max_qa_attempts_setting: int,
        agent_model: str,
        max_events_per_agent: int,
        notify_failure_callback=None
    ) -> Tuple[bool, str]:
        """
        Manages the QA process for fixing build issues.
        
        Args:
            qa_agent_runner: The agent runner for QA operations
            qa_agent: The QA agent prompts
            remediation_id: The ID of the remediation
            build_command: The command to build the application
            formatting_command: The command to format the code
            repo_root: The root directory of the repository
            max_qa_attempts_setting: Maximum number of QA attempts
            agent_model: The AI model to use for QA
            max_events_per_agent: Maximum number of agent events
            notify_failure_callback: Optional callback for failure notifications
            
        Returns:
            Tuple[bool, str]: Success status and QA result summary
        """
        qa_result = ""
        log("\n--- Starting QA Review Process ---")
        
        # Get changed files using git_handler
        if self.git_handler:
            changed_files = self.git_handler.get_list_changed_files()
        else:
            # Try to get git_handler from main.py
            try:
                from src.main import git_handler_obj
                if git_handler_obj:
                    changed_files = git_handler_obj.get_list_changed_files()
                else:
                    log("git_handler_obj not initialized. Cannot get changed files.", is_error=True)
                    changed_files = []
            except (ImportError, AttributeError):
                log("Cannot access git_handler_obj. Cannot get changed files.", is_error=True)
                changed_files = []
            
        build_success = False
        build_output = "Build not run."
        qa_summary_log = [] # Log QA agent summaries

        # Run formatting command before initial build if specified
        if formatting_command:
            formatting_changed_files = self.run_formatting(remediation_id, formatting_command, repo_root)
            if formatting_changed_files:
                changed_files.extend([f for f in formatting_changed_files if f not in changed_files])

        # Try initial build first
        log("\n--- Running Initial Build After Fix ---")
        initial_build_success, initial_build_output = self.run_build(remediation_id, build_command, repo_root)

        qa_result = "\n\n---\n\n## Review \n\n"
        qa_result += f"*   **Build Run:** Yes (`{build_command}`)\n"

        if initial_build_success:
            log("\n\u2705 Initial build successful after fix. No QA intervention needed.")
            self.telemetry_handler.update_telemetry("resultInfo.filesModified", len(changed_files))
            qa_result += "*   **Final Build Status:** Success \n"
            return True, qa_result

        # If initial build failed, enter the QA loop
        log("\n\u274c Initial build failed. Starting QA agent intervention loop.")
        
        # Analyze build failure and show error summary
        error_analysis = extract_build_errors(initial_build_output)
        debug_log("\n--- BUILD FAILURE ANALYSIS ---")
        debug_log(error_analysis)
        debug_log("--- END BUILD FAILURE ANALYSIS ---\n")
        build_output = initial_build_output

        qa_attempts = 0
        while qa_attempts < max_qa_attempts_setting:
            qa_attempts += 1
            log(f"\n::group::---- QA Attempt #{qa_attempts}/{max_qa_attempts_setting} ---")

            # Truncate build output if too long for the agent
            max_output_length = 15000 # Adjust as needed
            truncated_output = build_output
            if len(build_output) > max_output_length:
                truncated_output = "...build output may be cut off prior to here...\n" + build_output[-max_output_length:]

            # Run QA agent
            qa_summary = qa_agent_runner.run_qa_agent(
                build_output=truncated_output,
                changed_files=changed_files, # Pass the current list of changed files
                build_command=build_command,
                repo_root=repo_root,
                remediation_id=remediation_id,
                agent_model=agent_model,
                max_events_per_agent=max_events_per_agent,
                qa_history=qa_summary_log, # Pass the history of previous QA attempts
                qa_system_prompt=qa_agent.system_prompt,
                qa_user_prompt=qa_agent.user_prompt
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
                if self.git_handler:
                    changed_files = self.git_handler.get_list_changed_files() # Update changed files list
                else:
                    # Try to get git_handler from main.py
                    try:
                        from src.main import git_handler_obj
                        if git_handler_obj:
                            changed_files = git_handler_obj.get_list_changed_files()
                        else:
                            log("git_handler_obj not initialized. Cannot get changed files.", is_warning=True)
                            changed_files = []
                    except (ImportError, AttributeError):
                        log("Cannot access git_handler_obj. Cannot get changed files.", is_warning=True)
                        changed_files = []
                
                # Always run formatting command before build, if specified
                if formatting_command:
                    formatting_changed_files = self.run_formatting(remediation_id, formatting_command, repo_root)
                    if formatting_changed_files:
                        changed_files.extend([f for f in formatting_changed_files if f not in changed_files])
                    self.telemetry_handler.update_telemetry("resultInfo.filesModified", len(changed_files))

                # Re-run the main build command to check if the QA fix worked
                log("\n--- Re-running Build Command After QA Fix ---")
                build_success, build_output = self.run_build(remediation_id, build_command, repo_root)
                if build_success:
                    log("\n\u2705 Build successful after QA agent fix.")
                    qa_result += "*   **Final Build Status:** Success \n"
                    return True, qa_result
                else:
                    log("\n\u274c Build still failing after QA agent fix.")
                    continue # Continue to next QA iteration
            finally:
                log("\n::endgroup::") # Close the group for the QA attempt

        log(f"\n\u274c Build failed after {qa_attempts} QA attempts.")
        qa_result += "*   **Final Build Status:** Failure \n"
        failure_category = FailureCategory.EXCEEDED_QA_ATTEMPTS.value
        
        # Use notify_failure_callback if provided, otherwise try to use the OO implementation
        if notify_failure_callback:
            remediation_notified = notify_failure_callback(
                remediation_id=remediation_id,
                failure_category=failure_category
            )
        else:
            # Try to use the ContrastApiClient from main.py
            try:
                from src.main import contrast_api_client_obj
                if contrast_api_client_obj:
                    remediation_notified = contrast_api_client_obj.notify_remediation_failed(
                        remediation_id=remediation_id,
                        failure_category=failure_category
                    )
                else:
                    log("contrast_api_client_obj not initialized. Cannot notify remediation failure.", is_error=True)
                    remediation_notified = False
            except (ImportError, AttributeError):
                log("Cannot access contrast_api_client_obj. Cannot notify remediation failure.", is_error=True)
                remediation_notified = False
                
        if remediation_notified:
            log(f"Successfully notified Remediation service about {failure_category} for remediation {remediation_id}.")
        else:
            log(f"Failed to notify Remediation service about {failure_category} for remediation {remediation_id}.", is_warning=True)
            return False, qa_result
        
        return True, qa_result
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

import subprocess
import os

from pathlib import Path
from typing import Tuple, List

from src import git_handler

from src.utils import singleton, log, debug_log, error_exit, run_command
from src.build_output_analyzer import extract_build_errors
from src.contrast_api import FailureCategory, notify_remediation_failed
#from src.telemetry_handler import update_telemetry

from src.agent.agent_prompts import AgentPrompts
from src.agent.agent_runner import AgentRunner


@singleton
class AgentManager:
    def __init__(self, telemetry_handler):
        debug_log("Initializing AgentManager")
        self.telemetry_handler = telemetry_handler
        self.agent_runner = AgentRunner(telemetry_handler)

    def _build(self, remediation_id: str, build_command: str, repo_root: str) -> Tuple[bool, str]:
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
            self.telemetry_handler.update_telemetry("configInfo.buildCommandRunTestsIncluded", True);
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

    def _format(self, remediation_id: str, formatting_command: str, repo_root: Path) -> List[str]:
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
            changed_files = git_handler.get_list_changed_files()
        else:
            log(f"::error::Error executing formatting command: {formatting_command}")
            log(f"::error::Error details: {format_output}", is_error=True)
            error_exit(remediation_id)

        return changed_files

    def _qa(
        self, 
        qa_agent: AgentPrompts, 
        remediation_id: str, 
        build_command: str,
        formatting_command: str,
        repo_root: Path, 
        max_qa_attempts_setting: int,
        agent_model: str,
        max_events_per_agent: int
    ) -> Tuple[bool, str]:
        qa_result = ""
        log("\n--- Starting QA Review Process ---")
        changed_files = git_handler.get_list_changed_files()
        
### Start run_qa_loop
        build_success = False
        build_output = "Build not run."
        qa_summary_log = [] # Log QA agent summaries

        # Run formatting command before initial build if specified
        if formatting_command:
            formatting_changed_files = self._format(remediation_id, formatting_command, repo_root)
            if formatting_changed_files:
                changed_files.extend([f for f in formatting_changed_files if f not in changed_files])

        # Try initial build first
        log("\n--- Running Initial Build After Fix ---")
        initial_build_success, initial_build_output = self._build(remediation_id, build_command, repo_root)

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
            qa_summary = self.agent_runner.run_qa_agent(
                build_output=truncated_output,
                changed_files=changed_files, # Pass the current list of changed files
                build_command=build_command,
                repo_root=repo_root,
                max_events_per_agent=max_events_per_agent,
                remediation_id=remediation_id,
                agent_model=agent_model,
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
#                git_handler.stage_changes()
#                if git_handler.check_status():
#                    git_handler.amend_commit()
                    changed_files = git_handler.get_list_changed_files() # Update changed files list
#                    log("Amended commit with QA agent fixes.")
                    
                    # Always run formatting command before build, if specified
                    if formatting_command:
                        formatting_changed_files = self._format(remediation_id, formatting_command, repo_root)
                        if formatting_changed_files:
                            changed_files.extend([f for f in formatting_changed_files if f not in changed_files])
                        self.telemetry_handler.update_telemetry("resultInfo.filesModified", len(changed_files))

                    # Re-run the main build command to check if the QA fix worked
                    log("\n--- Re-running Build Command After QA Fix ---")
                    build_success, build_output = self._build(remediation_id, build_command, repo_root)
                    if build_success:
                        log("\n\u2705 Build successful after QA agent fix.")
                        qa_result += "*   **Final Build Status:** Success \n"
                        return True, qa_result
                    else:
                        log("\n\u274c Build still failing after QA agent fix.")
                        continue # Continue to next QA iteration
#                else:
#                    log("QA agent did not request a command and made no file changes. Build still failing.")
#                    # Break the loop if QA agent isn't making progress
#                    build_success = False
#                    break
            finally:
                log("\n::endgroup::") # Close the group for the QA attempt

#        if not build_success:
        log(f"\n\u274c Build failed after {qa_attempts} QA attempts.")

#        return build_success, changed_files, build_command, qa_summary_log
### End run qa loop
### remove this call to run_qa_loop()
#        build_success, final_changed_files, used_build_command, qa_summary_log = qa_handler.run_qa_loop(
#            build_command=build_command,
#            repo_root=repo_root,
#            max_qa_attempts=max_qa_attempts_setting,
#            initial_changed_files=initial_changed_files,
#            formatting_command=formatting_command,
#            remediation_id=remediation_id,
#            qa_system_prompt=qa_system_prompt,
#            qa_user_prompt=qa_user_prompt
#        )

#        if build_success:
#            qa_result += "*   **Final Build Status:** Success \n"
#        else:
        qa_result += "*   **Final Build Status:** Failure \n"
        
        # Skip PR creation if QA was run and the build is failing
        # or if the QA agent encountered an error (detected by checking qa_summary_log entries)
#        if not build_success or any(s.startswith("Error during QA agent execution:") for s in qa_summary_log):
#            failure_category = ""
            
#            if any(s.startswith("Error during QA agent.execution:") for s in qa_summary_log):
#                log("\n--- Skipping PR creation as QA Agent encountered an error ---")
#                failure_category = FailureCategory.QA_AGENT_FAILURE.value
#            else:
#                log("\n--- Skipping PR creation as QA Agent failed to fix build issues ---")
                # Check if we've exhausted all retry attempts
#                if len(qa_summary_log) >= max_qa_attempts_setting:
        failure_category = FailureCategory.EXCEEDED_QA_ATTEMPTS.value
            
            # Notify the Remediation service about the failed remediation if we have a failure category
#            if failure_category:
        remediation_notified = notify_remediation_failed(
            remediation_id=remediation_id,
            failure_category=failure_category
        )
                
        if remediation_notified:
            log(f"Successfully notified Remediation service about {failure_category} for remediation {remediation_id}.")
        else:
            log(f"Failed to notify Remediation service about {failure_category} for remediation {remediation_id}.", is_warning=True)
            return False, qa_result
        
        return True, qa_result
        
    def remediate_vulnerability(
        self, 
        fix_agent: AgentPrompts, 
        qa_agent: AgentPrompts, 
        remediation_id: str, 
        build_command: str,
        formatting_command: str,
        repo_root: Path, 
        skip_qa_review: bool, 
        max_qa_attempts_setting: int,
        max_events_per_agent:int,
        skip_writing_security_test: bool,
        agent_model: str
    ) -> Tuple[bool,str]:
        result = ""
    
        """Resolve a vulnerability using the provided agents."""        
        # Ensure the build is not broken before running the fix agent
        log("\n--- Running Build Before Fix ---")
        prefix_build_success, prefix_build_output = self._build(remediation_id, build_command, repo_root)
        if not prefix_build_success:
            # Analyze build failure and show error summary
            error_analysis = extract_build_errors(prefix_build_output)
            log("\n❌ Build is broken ❌ -- No fix attempted.")
            log(f"Build output:\n{error_analysis}")
            error_exit(remediation_id, FailureCategory.INITIAL_BUILD_FAILURE.value) # Exit if the build is broken, no point in proceeding
        
        result += self.agent_runner.run_fix_agent(fix_agent, remediation_id, repo_root, max_events_per_agent, skip_writing_security_test, agent_model)

        # Check if the fix agent encountered an error
        if result.startswith("Error during AI fix agent execution:"):
            log("Fix agent encountered an unrecoverable error. Skipping this vulnerability.")
            error_message = result[len("Error during AI fix agent execution:"):].strip()
            log(f"Error details: {error_message}")
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        if skip_qa_review:
            log("Skipping QA Review based on SKIP_QA_REVIEW setting.")
            return True, result

        qa_success, qa_result = self._qa(qa_agent=qa_agent,
                                         remediation_id=remediation_id,
                                         build_command=build_command,
                                         formatting_command=formatting_command,
                                         repo_root=repo_root,
                                         max_qa_attempts_setting=max_qa_attempts_setting,
                                         agent_model=agent_model,
                                         max_events_per_agent=max_events_per_agent)

        return qa_success, result + qa_result

# %%

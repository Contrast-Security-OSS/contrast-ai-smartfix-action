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

import sys
import os
import re
import asyncio
import warnings
import atexit
import platform
from datetime import datetime, timedelta
from asyncio.proactor_events import _ProactorBasePipeTransport

# Add the project root to the Python path to allow for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import utilities and check version
from src.utils import debug_log, log, error_exit
from src.version_check import do_version_check

# Import for compatibility with existing code
# Import this first since other modules might import from config
import src.config_compat as config

# Import domain-specific modules - new OO classes
from src.config.smart_fix_config import SmartFixConfig
from src.telemetry.telemetry_handler import TelemetryHandler
from src.api.contrast_api_client import ContrastApiClient, FailureCategory
from src.git.git_handler import GitHandler
from src.agent.agent_manager import AgentManager, AgentManagerFactory
from src.agent.agent_prompts import AgentPrompts
from src.orchestrator.smart_fix_orchestrator import SmartFixOrchestrator

# Legacy modules are kept but not imported
# We'll use only the OO implementations

# NOTE: Google ADK appears to have issues with asyncio event loop cleanup, and has had attempts to address them in versions 1.4.0-1.5.0
# Configure warnings to ignore asyncio ResourceWarnings during shutdown
warnings.filterwarnings("ignore", category=ResourceWarning, 
                        message="unclosed.*<asyncio.sslproto._SSLProtocolTransport.*")
warnings.filterwarnings("ignore", category=ResourceWarning, 
                        message="unclosed transport")
warnings.filterwarnings("ignore", category=ResourceWarning, 
                        message="unclosed.*<asyncio.*")

# Patch asyncio to handle event loop closed errors during shutdown
_original_loop_check_closed = asyncio.base_events.BaseEventLoop._check_closed

def _patched_loop_check_closed(self):
    try:
        _original_loop_check_closed(self)
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            return  # Suppress the error
        raise
asyncio.BaseEventLoop._check_closed = _patched_loop_check_closed

# Add a specific fix for _ProactorBasePipeTransport.__del__ on Windows
if platform.system() == 'Windows':
    # Import the specific module that contains ProactorBasePipeTransport
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
        
        # Store the original __del__ method
        _original_pipe_del = _ProactorBasePipeTransport.__del__
        
        # Define a safe replacement for __del__
        def _patched_pipe_del(self):
            try:
                # Check if the event loop is closed or finalizing
                if self._loop.is_closed() or sys.is_finalizing():
                    # Skip the original __del__ which would trigger the error
                    return

                # Otherwise use the original __del__ implementation
                _original_pipe_del(self)
            except (AttributeError, RuntimeError, ImportError, TypeError):
                # Catch and ignore all attribute or runtime errors during shutdown
                pass
        
        # Apply the patch to the __del__ method
        _ProactorBasePipeTransport.__del__ = _patched_pipe_del
        
        debug_log("Successfully patched _ProactorBasePipeTransport.__del__ for Windows")
    except (ImportError, AttributeError) as e:
        debug_log(f"Could not patch _ProactorBasePipeTransport: {str(e)}")

def cleanup_asyncio():
    """
    Cleanup function registered with atexit to properly handle asyncio resources during shutdown.
    This helps prevent the "Event loop is closed" errors during program exit.
    """
    # Suppress stderr temporarily to avoid printing shutdown errors
    original_stderr = sys.stderr
    try:
        # Create a dummy stderr to suppress errors during cleanup
        class DummyStderr:
            def write(self, *args, **kwargs):
                pass
            
            def flush(self):
                pass
        
        # Only on Windows do we need the more aggressive error suppression
        if platform.system() == 'Windows':
            sys.stderr = DummyStderr()
            
            # Windows-specific: ensure the proactor event loop resources are properly cleaned
            try:
                # Try to access the global WindowsProactorEventLoopPolicy
                loop_policy = asyncio.get_event_loop_policy()
                
                # If we have any running loops, close them properly
                try:
                    loop = loop_policy.get_event_loop()
                    if not loop.is_closed():
                        if loop.is_running():
                            loop.stop()
                        
                        # Cancel all tasks
                        pending = asyncio.all_tasks(loop)
                        if pending:
                            for task in pending:
                                task.cancel()
                            
                            # Give tasks a chance to respond to cancellation with a timeout
                            try:
                                loop.run_until_complete(asyncio.wait_for(
                                    asyncio.gather(*pending, return_exceptions=True), 
                                    timeout=1.0
                                ))
                            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                                pass
                        
                        # Close transports and other resources
                        try:
                            loop.run_until_complete(loop.shutdown_asyncgens())
                        except Exception:
                            pass
                            
                        try:
                            loop.close()
                        except Exception:
                            pass
                except Exception:
                    pass
                    
                # Force garbage collection to ensure __del__ methods are called
                try:
                    import gc
                    gc.collect()
                except Exception:
                    pass
                    
            except Exception:
                pass  # Ignore any errors during Windows-specific cleanup
        else:
            # For non-Windows platforms, perform regular cleanup
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.stop()
                
                # Cancel all tasks
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task in pending:
                        task.cancel()
                    
                    # Give tasks a chance to respond to cancellation
                    if not loop.is_closed():
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                # Close the loop
                if not loop.is_closed():
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.close()
            except Exception:
                pass  # Ignore any errors during cleanup
    finally:
        # Restore stderr
        sys.stderr = original_stderr

# Register the cleanup function
atexit.register(cleanup_asyncio)


# Import service classes
from src.api.contrast_api_client import ContrastApiClient
from src.telemetry.telemetry_handler import TelemetryHandler
from src.git.git_handler import GitHandler

def create_contrast_api_client():
    """Create and initialize the ContrastApiClient singleton."""
    return ContrastApiClient(
        host=config.CONTRAST_HOST,
        org_id=config.CONTRAST_ORG_ID,
        app_id=config.CONTRAST_APP_ID,
        auth_key=config.CONTRAST_AUTHORIZATION_KEY,
        api_key=config.CONTRAST_API_KEY,
        user_agent=config.USER_AGENT
    )

def create_telemetry_handler(contrast_api_client=None):
    """Create and initialize the TelemetryHandler singleton."""
    if contrast_api_client is None:
        contrast_api_client = create_contrast_api_client()
    return TelemetryHandler(
        contrast_api_client=contrast_api_client,
        enable_full_telemetry=config.ENABLE_FULL_TELEMETRY
    )

def create_git_handler():
    """Create and initialize the GitHandler singleton."""
    return GitHandler(
        github_token=config.GITHUB_TOKEN,
        github_repository=config.GITHUB_REPOSITORY,
        base_branch=config.BASE_BRANCH
    )

def main():
    """Main orchestration logic using the object-oriented structure."""
    start_time = datetime.now()
    log("--- Starting Contrast AI SmartFix Script ---")
    debug_log(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # --- Version Check ---
    do_version_check()

    # --- Initialize OO Classes ---
    # Initialize singletons using factory functions
    contrast_api_client = create_contrast_api_client()
    telemetry_handler = create_telemetry_handler(contrast_api_client)
    git_handler = create_git_handler()
    
    # --- Run the main process with OO code ---
    start_time = datetime.now()
    debug_log(f"Process start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Process all the logic that was previously in run_main_process
    # Use config values from config module
    build_command = config.BUILD_COMMAND
    debug_log(f"Build command specified: {build_command}")

    formatting_command = config.FORMATTING_COMMAND
    if formatting_command:
        debug_log(f"Formatting command specified: {formatting_command}")
    else:
        debug_log("FORMATTING_COMMAND not set or empty, formatting will be skipped.")

    # Use the validated and normalized settings from config module
    max_qa_attempts_setting = config.MAX_QA_ATTEMPTS
    max_open_prs_setting = config.MAX_OPEN_PRS

    # Configure Git
    git_handler.configure_git_user()

    # Check Open PR Limit
    log("\n::group::--- Checking Open PR Limit ---")
    label_prefix_to_check = "contrast-vuln-id:"
    current_open_pr_count = git_handler.count_open_prs_with_prefix(label_prefix_to_check)
    if current_open_pr_count >= max_open_prs_setting:
        log(f"Found {current_open_pr_count} open PR(s) with label prefix '{label_prefix_to_check}'.")
        log(f"This meets or exceeds the configured limit of {max_open_prs_setting}.")
        log("Exiting script to avoid creating more PRs.")
        sys.exit(0)
    else:
        log(f"Found {current_open_pr_count} open PR(s) with label prefix '{label_prefix_to_check}' (Limit: {max_open_prs_setting}). Proceeding...")
    log("\n::endgroup::")

    # Main processing loop and the rest of the logic
    # See original run_main_process for the full implementation
    
    # Clean up any dangling asyncio resources
    try:
        # Force asyncio resource cleanup before exit
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if not loop.is_closed():
            # Cancel all pending tasks
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    try:
                        task.cancel()
                    except Exception:
                        pass
                
                # Give tasks a chance to respond to cancellation
                try:
                    # Wait with a timeout to prevent hanging
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except (asyncio.CancelledError, Exception):
                    pass
            
            try:
                # Shut down asyncgens
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
                
            try:
                # Close the loop
                loop.close()
            except Exception:
                pass
                
        # On Windows, specifically force garbage collection
        if platform.system() == 'Windows':
            try:
                import gc
                gc.collect()
            except Exception:
                pass
    except Exception as e:
        # Ignore any errors during cleanup
        debug_log(f"Ignoring error during asyncio cleanup: {str(e)}")
        pass


# Following code moved to main() function
# def run_main_process(contrast_api_client, telemetry_handler, git_handler):
#    """Main orchestration logic using object-oriented architecture.
#    
#    Args:
#        contrast_api_client: The ContrastApiClient instance
#        telemetry_handler: The TelemetryHandler instance
#        git_handler: The GitHandler instance
#    """
    
    start_time = datetime.now()
    debug_log(f"Process start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # --- Use Build Command and Max Attempts/PRs from Config ---
    build_command = config.BUILD_COMMAND
    debug_log(f"Build command specified: {build_command}")


    formatting_command = config.FORMATTING_COMMAND
    if formatting_command:
        debug_log(f"Formatting command specified: {formatting_command}")
    else:
        debug_log("FORMATTING_COMMAND not set or empty, formatting will be skipped.")

    # Use the validated and normalized settings from config module
    # These values are already processed in config.py with appropriate validation and defaults
    max_qa_attempts_setting = config.MAX_QA_ATTEMPTS
    max_open_prs_setting = config.MAX_OPEN_PRS

    # GitHandler instance is already created globally
    
    # --- Initial Setup ---
    git_handler_obj.configure_git_user()

    # Check Open PR Limit
    log("\n::group::--- Checking Open PR Limit ---")
    label_prefix_to_check = "contrast-vuln-id:"
    current_open_pr_count = git_handler_obj.count_open_prs_with_prefix(label_prefix_to_check)
    if current_open_pr_count >= max_open_prs_setting:
        log(f"Found {current_open_pr_count} open PR(s) with label prefix '{label_prefix_to_check}'.")
        log(f"This meets or exceeds the configured limit of {max_open_prs_setting}.")
        log("Exiting script to avoid creating more PRs.")
        sys.exit(0)
    else:
        log(f"Found {current_open_pr_count} open PR(s) with label prefix '{label_prefix_to_check}' (Limit: {max_open_prs_setting}). Proceeding...")
    log("\n::endgroup::")
    # END Check Open PR Limit

    # --- Main Processing Loop ---
    processed_one = False
    max_runtime = timedelta(hours=3)  # Set maximum runtime to 3 hours
    
    # Construct GitHub repository URL (used for each API call)
    github_repo_url = f"https://github.com/{config.GITHUB_REPOSITORY}"
    debug_log(f"GitHub repository URL: {github_repo_url}")
    skipped_vulns = set()  # TS-39904
    remediation_id = "unknown"

    while True:
        telemetry_handler.reset_vuln_specific_telemetry()
        # Check if we've exceeded the maximum runtime
        current_time = datetime.now()
        elapsed_time = current_time - start_time
        if elapsed_time > max_runtime:
            log(f"\n--- Maximum runtime of 3 hours exceeded (actual: {elapsed_time}). Stopping processing. ---")
            # Use the global ContrastApiClient
            remediation_notified = contrast_api_client_obj.notify_remediation_failed(
                remediation_id=remediation_id,
                failure_category=FailureCategory.EXCEEDED_TIMEOUT.value
            )

            if remediation_notified:
                log(f"Successfully notified Remediation service about exceeded timeout for remediation {remediation_id}.")
            else:
                log(f"Failed to notify Remediation service about exceeded timeout for remediation {remediation_id}.", is_warning=True)
            break
            
        # Check if we've reached the max PR limit
        current_open_pr_count = git_handler.count_open_prs_with_prefix(label_prefix_to_check)
        if current_open_pr_count >= max_open_prs_setting:
            log(f"\n--- Reached max PR limit ({max_open_prs_setting}). Current open PRs: {current_open_pr_count}. Stopping processing. ---")
            break

        # --- Fetch Next Vulnerability and Prompts from New API ---
        log("\n::group::--- Fetching next vulnerability and prompts from Contrast API ---")
        
        # Use the global ContrastApiClient instance
        vulnerability_data = contrast_api_client_obj.get_vulnerability_with_prompts(
            max_open_prs=max_open_prs_setting,
            github_repo_url=github_repo_url,
            vulnerability_severities=config.VULNERABILITY_SEVERITIES
        )
        log("\n::endgroup::")

        if not vulnerability_data:
            log("No more vulnerabilities found to process or API error occurred. Stopping processing.")
            break

        # Extract vulnerability details and prompts from the response
        vuln_uuid = vulnerability_data['vulnerabilityUuid']
        vuln_title = vulnerability_data['vulnerabilityTitle']
        remediation_id = vulnerability_data['remediationId']
        fix_system_prompt = vulnerability_data['fixSystemPrompt']
        fix_user_prompt = vulnerability_data['fixUserPrompt']
        qa_system_prompt = vulnerability_data['qaSystemPrompt']
        qa_user_prompt = vulnerability_data['qaUserPrompt']
        
        # Populate vulnInfo in telemetry
        telemetry_handler_obj.update_telemetry("vulnInfo.vulnId", vuln_uuid)
        telemetry_handler_obj.update_telemetry("vulnInfo.vulnRule", vulnerability_data['vulnerabilityRuleName'])
        telemetry_handler_obj.update_telemetry("additionalAttributes.remediationId", remediation_id)

        log(f"\n::group::--- Considering Vulnerability: {vuln_title} (UUID: {vuln_uuid}) ---")

        # --- Check for Existing PRs ---
        label_name, _, _ = git_handler_obj.generate_label_details(vuln_uuid)
        pr_status = git_handler_obj.check_pr_status_for_label(label_name)

        # Changed this logic to check only for OPEN PRs for dev purposes
        if pr_status == "OPEN":
            log(f"Skipping vulnerability {vuln_uuid} as an OPEN PR with label '{label_name}' already exists.")
            log("\n::endgroup::")
            if vuln_uuid in skipped_vulns:
                log(f"Already skipped {vuln_uuid} before, breaking loop to avoid infinite loop.")
                break
            skipped_vulns.add(vuln_uuid)
            continue
        else:
            log(f"No existing OPEN or MERGED PR found for vulnerability {vuln_uuid}. Proceeding with fix attempt.")
        log("\n::endgroup::")
        log(f"\n\033[0;33m Selected vuln to fix: {vuln_title} \033[0m")

        # Prepare a clean repository state and branch for the fix
        new_branch_name = git_handler_obj.get_branch_name(remediation_id)
        try:
            git_handler_obj.prepare_feature_branch(remediation_id)
        except SystemExit:
            log(f"Error preparing feature branch {new_branch_name}. Skipping to next vulnerability.")
            continue

        agent_manager = AgentManager(telemetry_handler=telemetry_handler)
        
        remediation_success, ai_fix_summary_full = agent_manager.remediate_vulnerability(
            fix_agent = AgentPrompts(
                system_prompt=fix_system_prompt,
                user_prompt=AgentPrompts.process_fix_user_prompt(fix_user_prompt, config.SKIP_WRITING_SECURITY_TEST)
            ),
            qa_agent=AgentPrompts(
                system_prompt=qa_system_prompt,
                user_prompt=qa_user_prompt
            ),
            repo_root=config.REPO_ROOT,
            skip_qa_review=config.SKIP_QA_REVIEW,
            remediation_id=remediation_id,
            build_command=build_command,
            formatting_command=formatting_command,
            max_qa_attempts_setting=max_qa_attempts_setting,
            max_events_per_agent=config.MAX_EVENTS_PER_AGENT,
            skip_writing_security_test=config.SKIP_WRITING_SECURITY_TEST,
            agent_model=config.AGENT_MODEL
        )

        if not remediation_success:
            git_handler_obj.cleanup_branch(new_branch_name)
            # Send telemetry using the telemetry handler
            telemetry_handler_obj.send_telemetry_data()
            continue # Move to the next vulnerability

        # --- Git and GitHub Operations ---
        log("\n--- Proceeding with Git & GitHub Operations ---")
        git_handler_obj.stage_changes()

        if git_handler_obj.check_status():
            commit_message = git_handler_obj.generate_commit_message(vuln_title, vuln_uuid)
            git_handler_obj.commit_changes(commit_message)

            # --- Create Pull Request ---
            pr_title = git_handler_obj.generate_pr_title(vuln_title)
            # Use the result from fix_agent directly as the base PR body.
            # (extracted from <pr_body> tags) or the full agent summary if extraction fails.
            debug_log("Using agent's output as PR body base.")

            # --- Push and Create PR ---
            git_handler_obj.push_branch(new_branch_name) # Push the final commit (original or amended)

            label_name, label_desc, label_color = git_handler_obj.generate_label_details(vuln_uuid)
            label_created = git_handler_obj.ensure_label(label_name, label_desc, label_color)
            
            if not label_created:
                log(f"Could not create GitHub label '{label_name}'. PR will be created without a label.", is_warning=True)
                label_name = ""  # Clear label_name to avoid using it in PR creation

            pr_title = git_handler_obj.generate_pr_title(vuln_title)
            # Create a brief summary for the telemetry aiSummaryReport (limited to 255 chars in DB)
            # Generate an optimized summary using the dedicated function in telemetry_handler
            brief_summary = telemetry_handler_obj.create_ai_summary_report(ai_fix_summary_full)
            
            # Update telemetry with our optimized summary
            telemetry_handler_obj.update_telemetry("resultInfo.aiSummaryReport", brief_summary)

            try:
                # Set a flag to track if we should try the fallback approach
                pr_creation_success = False
                pr_url = "" # Initialize pr_url
                
                # Try to create the PR using the GitHub CLI
                log("Attempting to create a pull request...")
                pr_url = git_handler_obj.create_pr(pr_title, ai_fix_summary_full, remediation_id, config.BASE_BRANCH, label_name)
                
                if pr_url:
                    pr_creation_success = True
                    
                    # Extract PR number from PR URL
                    # PR URL format is like: https://github.com/org/repo/pull/123
                    pr_number = None
                    try:
                        # Use a more robust method to extract the PR number
                        
                        pr_match = re.search(r'/pull/(\d+)', pr_url)
                        debug_log(f"Extracting PR number from URL '{pr_url}', match object: {pr_match}")
                        if pr_match:
                            pr_number = int(pr_match.group(1))
                            debug_log(f"Successfully extracted PR number: {pr_number}")
                        else:
                            log(f"Could not find PR number pattern in URL: {pr_url}", is_warning=True)
                    except (ValueError, IndexError, AttributeError) as e:
                        log(f"Could not extract PR number from URL: {pr_url} - Error: {str(e)}")
                    
                    # Notify the Remediation backend service about the PR
                    if pr_number is None:
                        pr_number = 1;

                    # Use the global ContrastApiClient instance
                    remediation_notified = contrast_api_client_obj.notify_remediation_pr_opened(
                        remediation_id=remediation_id,
                        pr_number=pr_number,
                        pr_url=pr_url
                    )
                    if remediation_notified:
                        log(f"Successfully notified Remediation service about PR for remediation {remediation_id}.")
                    else:
                        log(f"Failed to notify Remediation service about PR for remediation {remediation_id}.", is_warning=True)
                else:
                    # This case should ideally be handled by create_pr exiting or returning empty
                    # However, if create_pr somehow returns without a URL but doesn't cause an exit:
                    log("PR creation did not return a URL. Assuming failure.")

                telemetry_handler_obj.update_telemetry("resultInfo.prCreated", pr_creation_success)
                
                if not pr_creation_success:
                    log("\n--- PR creation failed ---")
                    error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)
                
                processed_one = True # Mark that we successfully processed one
                log(f"\n--- Successfully processed vulnerability {vuln_uuid}. Continuing to look for next vulnerability... ---")
            except Exception as e:
                log(f"Error creating PR: {e}")
                log("\n--- PR creation failed ---")
                error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)
        else:
            log("Skipping commit, push, and PR creation as no changes were detected by the agent.")
            # Clean up the branch if no changes were made
            git_handler_obj.cleanup_branch(new_branch_name)
            continue # Try the next vulnerability

        # Send telemetry using the telemetry handler
        telemetry_handler_obj.send_telemetry_data()

    # Calculate total runtime
    end_time = datetime.now()
    total_runtime = end_time - start_time

    if not processed_one:
        log("\n--- No vulnerabilities were processed in this run. ---")
    else:
        log("\n--- Finished processing vulnerabilities. At least one vulnerability was successfully processed. ---")

    log(f"\n--- Script finished (total runtime: {total_runtime}) ---")


if __name__ == "__main__":
    main()
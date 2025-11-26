# -
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

import sys
import re
import asyncio
import warnings
import atexit
import platform
from datetime import datetime, timedelta
from asyncio.proactor_events import _ProactorBasePipeTransport
from urllib.parse import urlparse

# Import configurations and utilities
from src.config import get_config
from src.smartfix.shared.coding_agents import CodingAgents
from src.utils import debug_log, log, error_exit
from src import telemetry_handler
from src.version_check import do_version_check
from src.smartfix.domains.workflow.session_handler import create_session_handler, QASectionConfig
from src.smartfix.shared.failure_categories import FailureCategory

# Import domain-specific handlers
from src import contrast_api
from src import git_handler

# Import domain models
from src.smartfix.domains.vulnerability.context import RemediationContext, PromptConfiguration, BuildConfiguration, RepositoryConfiguration
from src.smartfix.domains.vulnerability.models import Vulnerability

# Import GitHub-specific agent factory
from src.github.agent_factory import GitHubAgentFactory

config = get_config()
telemetry_handler.initialize_telemetry()

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

    # Add a specific fix for BaseSubprocessTransport.__del__ on Windows
    try:
        from asyncio.base_subprocess import BaseSubprocessTransport

        # Store the original __del__ method
        _original_subprocess_del = BaseSubprocessTransport.__del__

        # Define a safe replacement for __del__
        def _patched_subprocess_del(self):
            try:
                # Check if the event loop is closed or finalizing
                if hasattr(self, '_loop') and self._loop is not None and (self._loop.is_closed() or sys.is_finalizing()):
                    # Skip the original __del__ which would trigger the error
                    return

                # Otherwise use the original __del__ implementation
                _original_subprocess_del(self)
            except (AttributeError, RuntimeError, ImportError, TypeError, ValueError):
                # Catch and ignore all attribute, runtime, or value errors during shutdown
                # ValueError specifically handles "I/O operation on closed pipe"
                pass

        # Apply the patch to the __del__ method
        BaseSubprocessTransport.__del__ = _patched_subprocess_del

        debug_log("Successfully patched BaseSubprocessTransport.__del__ for Windows")
    except (ImportError, AttributeError) as e:
        debug_log(f"Could not patch BaseSubprocessTransport: {str(e)}")


def cleanup_asyncio():  # noqa: C901
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


def main():  # noqa: C901
    """Main orchestration logic."""

    start_time = datetime.now()
    log("--- Starting Contrast AI SmartFix Script ---")
    debug_log(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # --- Version Check ---
    do_version_check()

    # --- Create Configuration Objects ---
    build_config = BuildConfiguration.from_config(config)
    repo_config = RepositoryConfiguration.from_config(config)

    debug_log(f"Build command: {build_config.build_command}")
    debug_log(f"Formatting command: {build_config.formatting_command}")
    debug_log(f"Max QA attempts: {config.MAX_QA_ATTEMPTS}")
    debug_log(f"Repository path: {repo_config.repo_path}")

    # Use the validated and normalized settings from config module
    # These values are already processed in config.py with appropriate validation and defaults
    max_open_prs_setting = config.MAX_OPEN_PRS

    # --- Initial Setup ---
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
    # END Check Open PR Limit

    # --- Main Processing Loop ---
    processed_one = False
    max_runtime = timedelta(hours=3)  # Set maximum runtime to 3 hours

    # Construct GitHub repository URL (used for each API call)
    parsed = urlparse(config.GITHUB_SERVER_URL)
    github_host = parsed.netloc
    github_repo_url = f"{github_host}/{config.GITHUB_REPOSITORY}"
    debug_log(f"GitHub repository URL: {github_repo_url}")
    skipped_vulns = set()  # TS-39904
    remediation_id = "unknown"
    previous_vuln_uuid = None  # Track previous vulnerability UUID to detect duplicates

    # Log initial credit tracking status if using Contrast LLM (only for SMARTFIX agent)
    if config.CODING_AGENT == CodingAgents.SMARTFIX.name and config.USE_CONTRAST_LLM:
        initial_credit_info = contrast_api.get_credit_tracking(
            contrast_host=config.CONTRAST_HOST,
            contrast_org_id=config.CONTRAST_ORG_ID,
            contrast_app_id=config.CONTRAST_APP_ID,
            contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
            contrast_api_key=config.CONTRAST_API_KEY
        )
        if initial_credit_info:
            log(initial_credit_info.to_log_message())
            # Log any initial warnings
            if initial_credit_info.should_log_warning():
                warning_msg = initial_credit_info.get_credit_warning_message()
                if initial_credit_info.is_exhausted:
                    log(warning_msg, is_error=True)
                    error_exit(remediation_id, FailureCategory.GENERAL_FAILURE.value)
                else:
                    log(warning_msg, is_warning=True)
        else:
            log("Could not retrieve initial credit tracking information", is_error=True)
            error_exit(remediation_id, FailureCategory.GENERAL_FAILURE.value)

    while True:
        telemetry_handler.reset_vuln_specific_telemetry()
        # Check if we've exceeded the maximum runtime
        current_time = datetime.now()
        elapsed_time = current_time - start_time
        if elapsed_time > max_runtime:
            log(f"\n--- Maximum runtime of 3 hours exceeded (actual: {elapsed_time}). Stopping processing. ---")
            remediation_notified = contrast_api.notify_remediation_failed(
                remediation_id=remediation_id,
                failure_category=FailureCategory.EXCEEDED_TIMEOUT.value,
                contrast_host=config.CONTRAST_HOST,
                contrast_org_id=config.CONTRAST_ORG_ID,
                contrast_app_id=config.CONTRAST_APP_ID,
                contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                contrast_api_key=config.CONTRAST_API_KEY
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

        # Check credit exhaustion for Contrast LLM usage
        if config.USE_CONTRAST_LLM:
            current_credit_info = contrast_api.get_credit_tracking(
                contrast_host=config.CONTRAST_HOST,
                contrast_org_id=config.CONTRAST_ORG_ID,
                contrast_app_id=config.CONTRAST_APP_ID,
                contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                contrast_api_key=config.CONTRAST_API_KEY
            )
            if current_credit_info and current_credit_info.is_exhausted:
                log("\n--- Credits exhausted. Stopping processing. ---")
                log("Credits have been exhausted. Contact your CSM to request additional credits.", is_error=True)
                break

        # --- Fetch Next Vulnerability Data from API ---
        if config.CODING_AGENT == CodingAgents.SMARTFIX.name:
            # For SMARTFIX, get vulnerability with prompts
            log("\n::group::--- Fetching next vulnerability and prompts from Contrast API ---")
            vulnerability_data = contrast_api.get_vulnerability_with_prompts(
                config.CONTRAST_HOST, config.CONTRAST_ORG_ID, config.CONTRAST_APP_ID,
                config.CONTRAST_AUTHORIZATION_KEY, config.CONTRAST_API_KEY,
                max_open_prs_setting, github_repo_url, config.VULNERABILITY_SEVERITIES
            )
            log("\n::endgroup::")

            if not vulnerability_data:
                log("No more vulnerabilities found to process. Stopping processing.")
                break

            # Extract vulnerability details and prompts from the response
            vuln_uuid = vulnerability_data['vulnerabilityUuid']

            # Check if this is the same vulnerability UUID as the previous iteration
            if vuln_uuid == previous_vuln_uuid:
                log(f"Error: Backend provided the same vulnerability UUID ({vuln_uuid}) as the previous iteration. This indicates a backend error.", is_warning=True)
                error_exit(remediation_id, FailureCategory.GENERAL_FAILURE.value)

            vuln_title = vulnerability_data['vulnerabilityTitle']
            remediation_id = vulnerability_data['remediationId']
            session_id = vulnerability_data.get('sessionId')

            # Validate and create prompt configuration for SmartFix agent
            try:
                PromptConfiguration.validate_raw_prompts_data(vulnerability_data)
                prompts = PromptConfiguration.for_smartfix_agent(
                    fix_system_prompt=vulnerability_data['fixSystemPrompt'],
                    fix_user_prompt=vulnerability_data['fixUserPrompt'],
                    qa_system_prompt=vulnerability_data['qaSystemPrompt'],
                    qa_user_prompt=vulnerability_data['qaUserPrompt']
                )
            except ValueError as e:
                log(f"Error: Invalid prompts from backend: {e}", is_error=True)
                error_exit(remediation_id, FailureCategory.GENERAL_FAILURE.value)
        else:
            # For external coding agents (GITHUB_COPILOT/CLAUDE_CODE), get vulnerability details
            log("\n::group::--- Fetching next vulnerability details from Contrast API ---")
            vulnerability_data = contrast_api.get_vulnerability_details(
                config.CONTRAST_HOST, config.CONTRAST_ORG_ID, config.CONTRAST_APP_ID,
                config.CONTRAST_AUTHORIZATION_KEY, config.CONTRAST_API_KEY,
                github_repo_url, max_open_prs_setting, config.VULNERABILITY_SEVERITIES
            )
            log("\n::endgroup::")

            if not vulnerability_data:
                log("No more vulnerabilities found to process. Stopping processing.")
                break

            # Extract vulnerability details from the response (no prompts for external agents)
            vuln_uuid = vulnerability_data['vulnerabilityUuid']

            # Check if this is the same vulnerability UUID as the previous iteration
            if vuln_uuid == previous_vuln_uuid:
                log(f"Error: Backend provided the same vulnerability UUID ({vuln_uuid}) as the previous iteration. This indicates a backend error.", is_warning=True)
                error_exit(remediation_id, FailureCategory.GENERAL_FAILURE.value)

            vuln_title = vulnerability_data['vulnerabilityTitle']
            remediation_id = vulnerability_data['remediationId']
            session_id = None  # External agents don't use Contrast LLM sessions

            # Create prompt configuration for external agent (no prompts required)
            prompts = PromptConfiguration.for_external_agent()

        # Populate vulnInfo in telemetry
        telemetry_handler.update_telemetry("vulnInfo.vulnId", vuln_uuid)
        telemetry_handler.update_telemetry("vulnInfo.vulnRule", vulnerability_data['vulnerabilityRuleName'])
        telemetry_handler.update_telemetry("additionalAttributes.remediationId", remediation_id)

        log(f"\n::group::--- Considering Vulnerability: {vuln_title} (UUID: {vuln_uuid}) ---")

        # --- Check for Existing PRs ---
        label_name, _, _ = git_handler.generate_label_details(vuln_uuid)
        pr_status = git_handler.check_pr_status_for_label(label_name)

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

        # Update tracking variable now that we know we're actually processing this vuln
        previous_vuln_uuid = vuln_uuid

        log(f"\n\033[0;33m Selected vuln to fix: {vuln_title} \033[0m")

        # --- Create Common Remediation Context ---
        # Create vulnerability and context from config - single source of truth
        vulnerability = Vulnerability.from_api_data(vulnerability_data)
        context = RemediationContext.from_config(remediation_id, vulnerability, config, prompts=prompts, session_id=session_id)

        # --- Check if we need to use the external coding agent ---
        if config.CODING_AGENT != CodingAgents.SMARTFIX.name:
            # Create agent using GitHubAgentFactory
            agent_type = CodingAgents[config.CODING_AGENT]
            external_agent = GitHubAgentFactory.create_agent(agent_type, config)
            # Assemble the issue body from vulnerability details
            issue_body = external_agent.assemble_issue_body(vulnerability_data)
            # Add issue_body for external agent compatibility
            context.issue_body = issue_body

            result = external_agent.remediate(context)

            if result.success:
                log("\n\n--- External Coding Agent successfully generated fixes ---")
                processed_one = True
                contrast_api.send_telemetry_data()
            continue  # Skip the built-in SmartFix code and PR creation

        telemetry_handler.update_telemetry("additionalAttributes.codingAgent", "INTERNAL-SMARTFIX")

        # Prepare a clean repository state and branch for the fix
        new_branch_name = git_handler.get_branch_name(remediation_id)
        try:
            git_handler.prepare_feature_branch(remediation_id)
        except SystemExit:
            log(f"Error preparing feature branch {new_branch_name}. Skipping to next vulnerability.")
            continue

        # --- Run SmartFix Agent ---
        # NOTE: The agent will validate the initial build before attempting fixes
        # Create SmartFix agent (no config needed - gets everything from context)
        smartfix_agent = GitHubAgentFactory.create_agent(CodingAgents.SMARTFIX)

        # Run the agent remediation process
        # The agent will run the fix agent and QA loop without doing any git operations
        # All git operations (staging, committing) happen in main.py after remediate() completes
        session = smartfix_agent.remediate(context)

        # Extract results from the session
        session_handler = create_session_handler()
        session_result = session_handler.handle_session_result(session)

        if not session_result.should_continue:
            # QA Agent failed to fix the build
            log(f"Agent failed with reason: {session_result.failure_category}")
            git_handler.cleanup_branch(new_branch_name)
            contrast_api.notify_remediation_failed(
                remediation_id=remediation_id,
                failure_category=session_result.failure_category,
                contrast_host=config.CONTRAST_HOST,
                contrast_org_id=config.CONTRAST_ORG_ID,
                contrast_app_id=config.CONTRAST_APP_ID,
                contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                contrast_api_key=config.CONTRAST_API_KEY
            )
            continue  # Move to next vulnerability

        ai_fix_summary_full = session_result.ai_fix_summary
        # Generate QA section based on session results
        # The SmartFix agent already handled the QA loop internally
        qa_config = QASectionConfig(
            skip_qa_review=config.SKIP_QA_REVIEW,
            has_build_command=build_config.has_build_command(),
            build_command=build_config.build_command
        )
        qa_section = session_handler.generate_qa_section(session, qa_config)

        # --- Git and GitHub Operations ---
        # All file changes from the agent (fix + QA + formatting) are uncommitted at this point
        # Stage and commit everything together
        log("\n--- Proceeding with Git & GitHub Operations ---")
        git_handler.stage_changes()

        # Check if there are changes to commit
        if not git_handler.check_status():
            # No changes detected - agent didn't make any modifications
            log("No changes detected from agent execution. Skipping PR creation.")
            git_handler.cleanup_branch(new_branch_name)
            continue

        # Commit all changes together (fix + QA fixes + formatting)
        commit_message = git_handler.generate_commit_message(vuln_title, vuln_uuid)
        git_handler.commit_changes(commit_message)
        log("Committed all agent changes.")

        # --- Create Pull Request ---
        pr_title = git_handler.generate_pr_title(vuln_title)
        # Use the result from SmartFix agent remediation as the base PR body.
        # The agent returns the PR body content (extracted from <pr_body> tags)
        # or the full agent summary if extraction fails.
        pr_body_base = ai_fix_summary_full
        debug_log("Using SmartFix agent's output as PR body base.")

        # --- Push and Create PR ---
        git_handler.push_branch(new_branch_name)  # Push the final commit (original or amended)

        label_name, label_desc, label_color = git_handler.generate_label_details(vuln_uuid)
        label_created = git_handler.ensure_label(label_name, label_desc, label_color)

        if not label_created:
            log(f"Could not create GitHub label '{label_name}'. PR will be created without a label.", is_warning=True)
            label_name = ""  # Clear label_name to avoid using it in PR creation

        pr_title = git_handler.generate_pr_title(vuln_title)

        updated_pr_body = pr_body_base + qa_section

        # Append credit tracking information to PR body if using Contrast LLM
        if config.CODING_AGENT == CodingAgents.SMARTFIX.name and config.USE_CONTRAST_LLM:
            current_credit_info = contrast_api.get_credit_tracking(
                contrast_host=config.CONTRAST_HOST,
                contrast_org_id=config.CONTRAST_ORG_ID,
                contrast_app_id=config.CONTRAST_APP_ID,
                contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                contrast_api_key=config.CONTRAST_API_KEY
            )
            if current_credit_info:
                # Increment credits used to account for this PR about to be created
                projected_credit_info = current_credit_info.with_incremented_usage()
                updated_pr_body += projected_credit_info.to_pr_body_section()

                # Show countdown message and warnings
                credits_after = projected_credit_info.credits_remaining
                log(f"Credit consumed. {credits_after} credits remaining")
                if projected_credit_info.should_log_warning():
                    warning_msg = projected_credit_info.get_credit_warning_message()
                    if projected_credit_info.is_exhausted:
                        log(warning_msg, is_error=True)
                    else:
                        log(warning_msg, is_warning=True)

        # Create a brief summary for the telemetry aiSummaryReport (limited to 255 chars in DB)
        # Generate an optimized summary using the dedicated function in telemetry_handler
        brief_summary = telemetry_handler.create_ai_summary_report(updated_pr_body)

        # Update telemetry with our optimized summary
        telemetry_handler.update_telemetry("resultInfo.aiSummaryReport", brief_summary)

        try:
            # Set a flag to track if we should try the fallback approach
            pr_creation_success = False
            pr_url = ""  # Initialize pr_url

            # Try to create the PR using the GitHub CLI
            log("Attempting to create a pull request...")
            pr_url = git_handler.create_pr(pr_title, updated_pr_body, remediation_id, config.BASE_BRANCH, label_name)

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
                    pr_number = 1

                remediation_notified = contrast_api.notify_remediation_pr_opened(
                    remediation_id=remediation_id,
                    pr_number=pr_number,
                    pr_url=pr_url,
                    contrastProvidedLlm=config.CODING_AGENT == CodingAgents.SMARTFIX.name and config.USE_CONTRAST_LLM,
                    contrast_host=config.CONTRAST_HOST,
                    contrast_org_id=config.CONTRAST_ORG_ID,
                    contrast_app_id=config.CONTRAST_APP_ID,
                    contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                    contrast_api_key=config.CONTRAST_API_KEY
                )
                if remediation_notified:
                    log(f"Successfully notified Remediation service about PR for remediation {remediation_id}.")

                    # Log updated credit tracking status after PR notification (only for SMARTFIX agent)
                    if config.CODING_AGENT == CodingAgents.SMARTFIX.name and config.USE_CONTRAST_LLM:
                        updated_credit_info = contrast_api.get_credit_tracking(
                            contrast_host=config.CONTRAST_HOST,
                            contrast_org_id=config.CONTRAST_ORG_ID,
                            contrast_app_id=config.CONTRAST_APP_ID,
                            contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                            contrast_api_key=config.CONTRAST_API_KEY
                        )
                        if updated_credit_info:
                            log(updated_credit_info.to_log_message())
                        else:
                            debug_log("Could not retrieve updated credit tracking information")
                else:
                    log(f"Failed to notify Remediation service about PR for remediation {remediation_id}.", is_warning=True)
            else:
                # This case should ideally be handled by create_pr exiting or returning empty
                # and then the logic below for SKIP_PR_ON_FAILURE would trigger.
                # However, if create_pr somehow returns without a URL but doesn't cause an exit:
                log("PR creation did not return a URL. Assuming failure.")

            telemetry_handler.update_telemetry("resultInfo.prCreated", pr_creation_success)

            if not pr_creation_success:
                log("\n--- PR creation failed ---")
                error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)

            processed_one = True  # Mark that we successfully processed one
            log(f"\n--- Successfully processed vulnerability {vuln_uuid}. Continuing to look for next vulnerability... ---")
        except Exception as e:
            log(f"Error creating PR: {e}")
            log("\n--- PR creation failed ---")
            error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)

        contrast_api.send_telemetry_data()

    # Calculate total runtime
    end_time = datetime.now()
    total_runtime = end_time - start_time

    if not processed_one:
        log("\n--- No vulnerabilities were processed in this run. ---")
    else:
        log("\n--- Finished processing vulnerabilities. At least one vulnerability was successfully processed. ---")

    log(f"\n--- Script finished (total runtime: {total_runtime}) ---")

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


if __name__ == "__main__":
    main()

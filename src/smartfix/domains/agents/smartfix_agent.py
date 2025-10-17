"""
SmartFixAgent - Internal Contrast AI SmartFix coding agent implementation.

This module contains the SmartFixAgent class which orchestrates the Fix Agent + QA Agent
workflow for vulnerability remediation without git operations.
"""

import datetime
import re
from typing import List, Optional, Tuple

from src.config import get_config
from src.smartfix.domains.workflow.build_runner import run_build_command
from src.smartfix.domains.workflow.formatter import run_formatting_command
from src.smartfix.domains.agents.event_loop_utils import _run_agent_in_event_loop, _run_agent_internal_with_prompts
from src.build_output_analyzer import extract_build_errors
from src.utils import debug_log, log, error_exit, tail_string
from src.smartfix.shared.failure_categories import FailureCategory
from src import telemetry_handler
from src.git_handler import get_uncommitted_changed_files

from .coding_agent import CodingAgentStrategy
from .agent_session import AgentSession, AgentSessionStatus, AgentEvent
from src.smartfix.domains.vulnerability import RemediationContext


class SmartFixAgent(CodingAgentStrategy):
    """
    Internal SmartFix coding agent that orchestrates the Fix Agent + QA Agent workflow.

    Encapsulates the vulnerability fixing and build validation logic without git operations.
    """

    def __init__(self):
        """Initialize SmartFixAgent using global configuration."""
        config = get_config()
        self.max_qa_attempts = config.MAX_QA_ATTEMPTS

    def remediate(self, context: RemediationContext) -> AgentSession:
        """
        Execute the complete remediation workflow for a vulnerability.

        Args:
            context: RemediationContext containing vulnerability details and configuration

        Returns:
            AgentSession containing the complete remediation attempt data
        """
        session = AgentSession()
        session.start_time = datetime.datetime.now()
        session.status = AgentSessionStatus.IN_PROGRESS

        try:
            # Step 1: Validate initial build
            if not self._validate_initial_build(session, context):
                session.complete_session(AgentSessionStatus.ERROR)
                return session

            # Step 2: Run fix agent
            fix_result = self._run_fix_agent(session, context)
            if not fix_result:
                session.complete_session(AgentSessionStatus.ERROR)
                return session

            # Step 3: Run QA loop (only if build command is available)
            if hasattr(context, 'build_config') and context.build_config and context.build_config.has_build_command():
                if not self._run_qa_loop(session, context, fix_result):
                    session.complete_session(AgentSessionStatus.ERROR)
                    return session
            else:
                # Skip QA loop when no build command is configured
                session.events.append(AgentEvent(
                    prompt="QA Review",
                    response="Skipping QA review: No build command configured"
                ))

            # Success!
            session.complete_session(AgentSessionStatus.SUCCESS, fix_result)
            return session

        except Exception:
            session.complete_session(AgentSessionStatus.ERROR)
            return session

    def _validate_initial_build(self, session: AgentSession, context: RemediationContext) -> bool:
        """
        Validate that the initial build works before attempting fixes.

        Args:
            session: Current agent session for tracking events
            context: Remediation context with build configuration

        Returns:
            bool: True if build passes, False if build fails
        """
        try:
            build_success, build_output = run_build_command(
                getattr(getattr(context, 'build_config', None), 'build_command', 'npm test'),
                getattr(getattr(context, 'repo_config', None), 'repo_path', '/tmp/test-repo'),
                getattr(context, 'remediation_id', 'test-123')
            )
        except SystemExit:
            # run_build_command called error_exit() due to build failure
            build_success = False
            build_output = "Build command failed with SystemExit"

        if not build_success:
            # Build failed - extract and log errors
            build_errors = extract_build_errors(build_output)
            error_message = f"Build failed before fix attempt. Build output:\n{build_errors}"

            event = AgentEvent(
                prompt="Running build command",
                response=error_message
            )
            session.events.append(event)
            return False

        # Build passed
        event = AgentEvent(
            prompt="Running build command",
            response="Initial build validation passed successfully"
        )
        session.events.append(event)
        return True

    def _run_fix_agent(self, session: AgentSession, context: RemediationContext) -> str:
        """
        Execute the AI fix agent to generate remediation code.

        Args:
            session: Current agent session for tracking events
            context: Remediation context with vulnerability details

        Returns:
            str: Fix result on success, None on failure
        """
        try:
            # Validate context has required attributes before calling run_ai_fix_agent
            if not hasattr(context, 'prompts') or not hasattr(context, 'repo_config'):
                # Context is missing required attributes (likely a mock), return error
                fix_result = "Error: RemediationContext missing required attributes (prompts, repo_config)"
            else:
                # Call the internal fix agent method
                fix_result = self._run_ai_fix_agent(context)
        except SystemExit:
            # run_ai_fix_agent called error_exit() due to failure
            fix_result = "Error: Fix agent failed with SystemExit"
        except Exception as e:
            # Other exception during fix agent execution
            event = AgentEvent(
                prompt="Run AI Fix Agent",
                response=f"Exception during fix agent execution: {str(e)}"
            )
            session.events.append(event)
            return None

        if fix_result and not fix_result.startswith("Error"):
            # Fix agent succeeded
            vulnerability_title = getattr(getattr(context, 'vulnerability', None), 'title', 'vulnerability')
            event = AgentEvent(
                prompt=f"Fix vulnerability: {vulnerability_title}",
                response=f"Fix agent completed successfully: {fix_result}"
            )
            session.events.append(event)
            return fix_result
        else:
            # Fix agent failed
            error_message = fix_result or "Fix agent failed with unknown error"
            event = AgentEvent(
                prompt="Run AI Fix Agent",
                response=f"Error: {error_message}"
            )
            session.events.append(event)
            return None

    def _run_qa_loop(self, session: AgentSession, context: RemediationContext, fix_result: str) -> bool:
        """
        Execute the QA review loop to validate and iterate on the fix.

        Args:
            session: Current agent session for tracking events
            context: Remediation context with QA configuration
            fix_result: Result from the fix agent to iterate on

        Returns:
            bool: True if QA loop succeeds, False otherwise
        """
        # Check if build command is available
        if not hasattr(context, 'build_config') or not context.build_config or not context.build_config.has_build_command():
            # No build command configured, skip QA and return success
            event = AgentEvent(
                prompt="QA Review",
                response="QA review skipped: No build command configured"
            )
            session.events.append(event)
            return True

        try:
            # Run the QA loop directly (no need for nested loops)
            success, changed_files, error_message, qa_logs = self._run_qa_loop_internal(
                context=context,
                max_qa_attempts=self.max_qa_attempts,  # Use the actual max attempts
                initial_changed_files=getattr(context, 'changed_files', []),
                current_attempt=1,
                total_attempts=self.max_qa_attempts
            )

            # Update session with final QA attempts count
            session.qa_attempts = len([log for log in qa_logs if log])  # Count non-empty logs

            if success:
                # QA loop succeeded
                event = AgentEvent(
                    prompt="QA Review",
                    response=f"QA review completed successfully after {session.qa_attempts} attempts"
                )
                session.events.append(event)
                return True
            else:
                # QA loop failed
                event = AgentEvent(
                    prompt="QA Review",
                    response=f"QA review failed after {session.qa_attempts} attempts: {error_message}"
                )
                session.events.append(event)
                return False

        except SystemExit:
            # run_qa_loop called error_exit() due to failure
            event = AgentEvent(
                prompt="QA Review",
                response="QA loop failed with SystemExit"
            )
            session.events.append(event)
            return False
        except Exception as e:
            # Exception during QA loop
            event = AgentEvent(
                prompt="QA Review",
                response=f"Exception during QA loop: {str(e)}"
            )
            session.events.append(event)
            return False

    def _run_ai_fix_agent(self, context: RemediationContext) -> str:
        """Synchronously runs the AI agent to analyze and apply a fix using API-provided prompts."""

        # Use the API-provided prompts (processing already handled by PromptConfiguration)
        debug_log("Using API-provided fix prompts")
        debug_log(f"Fix System Prompt Length: {len(context.prompts.fix_system_prompt)} chars")
        debug_log(f"Fix User Prompt Length: {len(context.prompts.fix_user_prompt)} chars")

        log("\n--- Preparing to run AI Agent to Apply Fix ---")
        debug_log(f"Repo Root for Agent Tools: {context.repo_config.repo_path}")
        config = get_config()
        debug_log(f"Skip Writing Security Test: {config.SKIP_WRITING_SECURITY_TEST}")

        try:
            # Execute the fix agent
            agent_summary_str = self._run_fix_agent_execution(context.repo_config, context.prompts, context.remediation_id)

            # Extract analytics data for telemetry
            self._extract_analytics_data(agent_summary_str)

            # Extract and return PR body content
            return self._extract_pr_body(agent_summary_str)

        except Exception as e:
            log(f"Error running AI fix agent: {e}", is_error=True)
            failure_code = FailureCategory.AGENT_FAILURE.value
            if "litellm." in str(e).lower():
                failure_code = FailureCategory.INVALID_LLM_CONFIG.value
            # Cleanup any changes made and revert to base branch (no branch name yet)
            error_exit(context.remediation_id, failure_code)

    def _run_fix_agent_execution(self, repo_config, prompts, remediation_id: str) -> str:
        """Execute the fix agent and return the summary."""
        agent_summary_str = _run_agent_in_event_loop(
            _run_agent_internal_with_prompts,
            'fix',
            repo_config.repo_path,
            prompts.fix_user_prompt,
            prompts.fix_system_prompt,
            remediation_id
        )

        log("--- AI Agent Fix Attempt Completed ---")
        debug_log("\n--- Full Agent Summary ---")
        debug_log(agent_summary_str)
        debug_log("--------------------------")

        # Check if the agent was unable to use filesystem tools
        if "No MCP tools available" in agent_summary_str or "Proceeding without filesystem tools" in agent_summary_str:
            log("Error during AI fix agent execution: No filesystem tools were available. The agent cannot make changes to files.")
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        return agent_summary_str

    def _extract_analytics_data(self, agent_summary_str: str):
        """Extract analytics data from agent response and update telemetry."""
        analytics_match = re.search(r"<analytics>(.*?)</analytics>", agent_summary_str, re.DOTALL)
        if not analytics_match:
            debug_log("Warning: <analytics> tags not found in agent response.")
            return

        analytics_content = analytics_match.group(1).strip()
        debug_log(f"Analytics content found:\\n{analytics_content}")

        # Extract Confidence_Score
        confidence_score_line_match = re.search(r"Confidence_Score:\s*(.*)", analytics_content)
        if confidence_score_line_match:
            confidence_str = confidence_score_line_match.group(1).strip()
            if confidence_str:
                telemetry_handler.update_telemetry("resultInfo.confidence", confidence_str)
        else:
            debug_log("Confidence_Score not found in analytics or is empty.")

        # Extract Programming_Language
        prog_lang_match = re.search(r"Programming_Language:\s*(.*)", analytics_content)
        if prog_lang_match:
            programming_language_str = prog_lang_match.group(1).strip()
            if programming_language_str:
                telemetry_handler.update_telemetry("appInfo.programmingLanguage", programming_language_str)
        else:
            debug_log("Programming_Language not found in analytics.")

        # Extract Technical_Stack
        tech_stack_match = re.search(r"Technical_Stack:\s*(.*)", analytics_content)
        if tech_stack_match:
            technical_stack_str = tech_stack_match.group(1).strip()
            if technical_stack_str:
                telemetry_handler.update_telemetry("appInfo.technicalStackInfo", technical_stack_str)
        else:
            debug_log("Technical_Stack not found in analytics.")

        # Extract Frameworks
        frameworks_match = re.search(r"Frameworks:\s*(.*)", analytics_content)
        if frameworks_match:
            frameworks_raw_str = frameworks_match.group(1).strip()
            if frameworks_raw_str:
                frameworks_list = [fw.strip() for fw in frameworks_raw_str.split(',') if fw.strip()]
                if frameworks_list:
                    telemetry_handler.update_telemetry("appInfo.frameworksAndLibraries", frameworks_list)
        else:
            debug_log("Frameworks not found in analytics.")

    def _extract_pr_body(self, agent_summary_str: str) -> str:
        """Extract PR body content from agent response."""
        pr_body_match = re.search(r"<pr_body>(.*?)</pr_body>", agent_summary_str, re.DOTALL)
        if pr_body_match:
            extracted_pr_body = pr_body_match.group(1).strip()
            debug_log("\n--- Extracted PR Body ---")
            debug_log(extracted_pr_body)
            debug_log("-------------------------")
            return extracted_pr_body
        else:
            debug_log("Warning: <pr_body> tags not found in agent response. Using full summary for PR body.")
            return agent_summary_str

    def _run_qa_loop_internal(
        self,
        context: RemediationContext,
        max_qa_attempts: int,
        initial_changed_files: List[str],
        current_attempt: int = 1,
        total_attempts: int = None
    ) -> Tuple[bool, List[str], Optional[str], List[str]]:
        """
        Runs the build and QA agent loop.

        Args:
            context: RemediationContext containing vulnerability and configuration.
            max_qa_attempts: Maximum number of QA attempts.
            initial_changed_files: List of files changed by the initial fix agent.
            current_attempt: Current attempt number from outer loop (for display).
            total_attempts: Total attempts from outer loop (for display).

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
        # Get the current list of uncommitted changed files from git
        # This is the minimal git operation needed to track what files the agents are modifying
        changed_files = get_uncommitted_changed_files()
        debug_log(f"Detected {len(changed_files)} uncommitted changed files at start of QA loop")
        qa_summary_log = []  # Log QA agent summaries

        # Extract values from domain objects
        build_command = context.build_config.build_command
        formatting_command = context.build_config.formatting_command
        repo_root = context.repo_config.repo_path
        remediation_id = context.remediation_id

        if not build_command:
            log("Skipping QA loop: No build command provided.")
            return True, changed_files, build_command, qa_summary_log  # Assume success if no build command

        # NOTE: The initial commit for the fix agent's changes should be handled by the caller (main.py)
        # before entering the QA loop. This keeps git operations out of the smartfix domain.

        # Run formatting command before initial build if specified
        if formatting_command:
            run_formatting_command(formatting_command, repo_root, remediation_id)
            # Update changed_files list after formatting
            changed_files = get_uncommitted_changed_files()
            debug_log(f"After formatting: {len(changed_files)} uncommitted changed files")

        # Try initial build first (before entering QA loop)
        log("\n--- Running Initial Build After Fix ---")
        initial_build_success, initial_build_output = run_build_command(build_command, repo_root, remediation_id)
        build_output = initial_build_output  # Store the latest output

        if initial_build_success:
            log("\n✅ Initial build successful after fix. No QA intervention needed.")
            telemetry_handler.update_telemetry("resultInfo.filesModified", len(changed_files))
            build_success = True
            return build_success, changed_files, build_command, qa_summary_log

        # If initial build failed, enter the QA loop
        log("\n❌ Initial build failed. Starting QA agent intervention loop.")
        # Analyze build failure and show error summary
        error_analysis = extract_build_errors(initial_build_output)
        debug_log("\n--- BUILD FAILURE ANALYSIS ---")
        debug_log(error_analysis)
        debug_log("--- END BUILD FAILURE ANALYSIS ---\n")

        while qa_attempts < max_qa_attempts:
            qa_attempts += 1
            # Use total_attempts for display if provided (from outer loop), otherwise use max_qa_attempts
            display_total = total_attempts if total_attempts else max_qa_attempts
            log(f"\n::group::---- QA Attempt #{qa_attempts}/{display_total} ---")

            # Truncate build output if too long for the agent
            max_output_length = 15000  # Adjust as needed
            truncated_output = build_output
            if len(build_output) > max_output_length:
                truncated_output = tail_string(build_output, max_output_length, prefix="...build output may be cut off prior to here...\n")

            # Run QA agent to fix the build
            try:
                qa_summary = self._run_qa_agent(
                    context=context,
                    build_output=truncated_output,
                    changed_files=changed_files,  # Pass the current list of changed files
                    qa_history=qa_summary_log  # Pass the history of previous QA attempts
                )

                # Check if QA agent encountered an error
                if qa_summary.startswith("Error during QA agent execution:"):
                    log(f"QA Agent encountered an unrecoverable error: {qa_summary}")
                    log("Continuing with build process, but PR creation may be skipped.")
                    # Note: The branch cleanup will be handled in main.py after checking build_success

                debug_log(f"QA Agent Summary: {qa_summary}")
                qa_summary_log.append(qa_summary)  # Log the summary

                # --- Handle QA Agent Output ---
                # NOTE: Git operations (staging, committing) are handled by main.py after remediate() completes
                # The QA agent has made changes to files, and we just need to check if the build passes now

                # Update changed_files list after QA agent made modifications
                changed_files = get_uncommitted_changed_files()
                debug_log(f"After QA agent: {len(changed_files)} uncommitted changed files")

                # Always run formatting command before build, if specified
                if formatting_command:
                    run_formatting_command(formatting_command, repo_root, remediation_id)
                    # Update changed_files list after formatting
                    changed_files = get_uncommitted_changed_files()
                    debug_log(f"After QA formatting: {len(changed_files)} uncommitted changed files")

                telemetry_handler.update_telemetry("resultInfo.filesModified", len(changed_files))

                # Re-run the main build command to check if the QA fix worked
                log("\n--- Re-running Build Command After QA Fix ---")
                build_success, build_output = run_build_command(build_command, repo_root, remediation_id)
                if build_success:
                    log("\n✅ Build successful after QA agent fix.")
                    log("\n::endgroup::")  # Close the group for the QA attempt
                    break  # Exit QA loop
                else:
                    log("\n❌ Build still failing after QA agent fix.")
                    log("\n::endgroup::")  # Close the group for the QA attempt
                    continue  # Continue to next QA iteration

            except Exception as e:
                error_msg = f"Error during QA agent execution: {str(e)}"
                log(error_msg, is_error=True)
                qa_summary_log.append(error_msg)
                log("\n::endgroup::")  # Close the group for the QA attempt
                return False, changed_files, error_msg, qa_summary_log

        if not build_success:
            log(f"\n❌ Build failed after {qa_attempts} QA attempts.")

        return build_success, changed_files, build_command, qa_summary_log

    def _run_qa_agent(self, context: RemediationContext, build_output: str, changed_files: List[str], qa_history: Optional[List[str]] = None) -> str:
        """
        Synchronously runs the QA AI agent to fix build/test errors using API-provided prompts.

        Args:
            context: RemediationContext containing vulnerability and configuration.
            build_output: The output from the build command.
            changed_files: A list of files that were changed by the fix agent.
            qa_history: Optional history of previous QA attempts.

        Returns:
            A summary string of the QA agent's actions.
        """
        # Check if we have QA prompts available
        if not context.prompts or not context.prompts.has_qa_prompts():
            log("No QA prompts available. Skipping QA agent execution.")
            return "No QA prompts available for execution"

        debug_log("Using API-provided QA prompts")
        debug_log(f"QA System Prompt Length: {len(context.prompts.qa_system_prompt)} chars")
        debug_log(f"QA User Prompt Length: {len(context.prompts.qa_user_prompt)} chars")

        log("\n--- Preparing to run QA Agent to Fix Build/Test Errors ---")
        debug_log(f"Repo Root for QA Agent Tools: {context.repo_config.repo_path}")
        debug_log(f"Build Command Used: {context.build_config.build_command}")
        debug_log(f"Files Changed by Fix Agent: {changed_files}")
        debug_log(f"Build Output Provided (truncated):\n---\n{tail_string(build_output, 1000)}\n---")

        # Format QA history
        qa_history_section = ""
        if qa_history:
            qa_history_section = "\n\n".join([f"Previous QA Attempt {i+1}:\n{summary}" for i, summary in enumerate(qa_history)])

        # Get processed QA user prompt
        qa_query = context.prompts.get_processed_qa_user_prompt(changed_files, build_output, qa_history_section)

        try:
            # Execute the QA agent
            qa_summary = _run_agent_in_event_loop(
                _run_agent_internal_with_prompts,
                'qa',
                context.repo_config.repo_path,
                qa_query,
                context.prompts.qa_system_prompt,
                context.remediation_id
            )

            log("--- QA Agent Execution Completed ---")
            debug_log(f"\n--- QA Agent Summary ---\n{qa_summary}\n--------------------------")

            return qa_summary

        except Exception as e:
            log(f"Error running QA agent: {e}", is_error=True)
            failure_code = FailureCategory.QA_AGENT_FAILURE.value
            if "litellm." in str(e).lower():
                failure_code = FailureCategory.INVALID_LLM_CONFIG.value
            error_exit(context.remediation_id, failure_code)

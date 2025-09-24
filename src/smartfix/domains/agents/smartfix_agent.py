"""
SmartFixAgent - Internal Contrast AI SmartFix coding agent implementation.

This module contains the SmartFixAgent class which orchestrates the Fix Agent + QA Agent
workflow for vulnerability remediation without git operations.
"""

import datetime
import re
from typing import List, Optional, Tuple

from src.qa_handler import run_build_command  # Note: will migrate run_qa_loop
from src.agent_handler import _run_agent_in_event_loop, _run_agent_internal_with_prompts
from src.build_output_analyzer import extract_build_errors
from src.utils import debug_log, log, error_exit, tail_string
from src.smartfix.shared.failure_categories import FailureCategory
from src import telemetry_handler

from .coding_agent import CodingAgentStrategy
from .agent_session import AgentSession, AgentSessionStatus, AgentEvent
from src.smartfix.domains.vulnerability import RemediationContext


class SmartFixAgent(CodingAgentStrategy):
    """
    Internal SmartFix coding agent that orchestrates the Fix Agent + QA Agent workflow.

    Encapsulates the vulnerability fixing and build validation logic without git operations.
    """

    def __init__(self, max_qa_attempts: int = 5):
        """
        Initialize SmartFixAgent.

        Args:
            max_qa_attempts: Maximum number of QA attempts allowed (default: 5)
        """
        self.max_qa_attempts = max_qa_attempts

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

        qa_attempts = 0

        while qa_attempts < self.max_qa_attempts:
            qa_attempts += 1
            session.qa_attempts = qa_attempts

            try:
                # Extract initial_changed_files if available
                initial_changed_files = getattr(context, 'changed_files', [])

                try:
                    # Use the internal QA loop method
                    success, changed_files, error_message, qa_logs = self._run_qa_loop_internal(
                        context=context,
                        max_qa_attempts=1,  # Single attempt per iteration
                        initial_changed_files=initial_changed_files
                    )
                    # Convert to expected format for compatibility
                    qa_result = {
                        'success': success,
                        'error': error_message,
                        'changed_files': changed_files,
                        'logs': qa_logs
                    }
                except SystemExit:
                    # run_qa_loop called error_exit() due to failure
                    qa_result = {'success': False, 'error': 'QA loop failed with SystemExit'}

                if qa_result and qa_result.get('success', False):
                    # QA loop succeeded
                    event = AgentEvent(
                        prompt=f"QA Loop Attempt {qa_attempts}",
                        response=f"QA review completed successfully after {qa_attempts} attempts"
                    )
                    session.events.append(event)
                    return True

                # QA loop failed but we can retry
                failure_reason = qa_result.get('error', 'Unknown QA failure') if qa_result else 'QA loop returned None'
                event = AgentEvent(
                    prompt=f"QA Loop Attempt {qa_attempts}",
                    response=f"QA attempt {qa_attempts} failed: {failure_reason}"
                )
                session.events.append(event)

                if qa_attempts >= self.max_qa_attempts:
                    # Max attempts reached
                    final_event = AgentEvent(
                        prompt="QA Loop Final Result",
                        response=f"QA loop failed after {qa_attempts} attempts. Max attempts ({self.max_qa_attempts}) reached."
                    )
                    session.events.append(final_event)
                    return False

            except Exception as e:
                # Exception during QA loop
                event = AgentEvent(
                    prompt=f"QA Loop Attempt {qa_attempts}",
                    response=f"Exception during QA loop attempt {qa_attempts}: {str(e)}"
                )
                session.events.append(event)

                if qa_attempts >= self.max_qa_attempts:
                    return False

        return False

    def _run_ai_fix_agent(self, context: RemediationContext) -> str:
        """Synchronously runs the AI agent to analyze and apply a fix using API-provided prompts."""

        # Use the API-provided prompts (processing already handled by PromptConfiguration)
        debug_log("Using API-provided fix prompts")
        debug_log(f"Fix System Prompt Length: {len(context.prompts.fix_system_prompt)} chars")
        debug_log(f"Fix User Prompt Length: {len(context.prompts.fix_user_prompt)} chars")

        log("\n--- Preparing to run AI Agent to Apply Fix ---")
        debug_log(f"Repo Root for Agent Tools: {context.repo_config.repo_path}")

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

    def _run_qa_loop_internal(self, context: RemediationContext, max_qa_attempts: int, initial_changed_files: List[str]) -> Tuple[bool, List[str], Optional[str], List[str]]:
        """
        Runs the build and QA agent loop.

        Args:
            context: RemediationContext containing vulnerability and configuration.
            max_qa_attempts: Maximum number of QA attempts.
            initial_changed_files: List of files changed by the initial fix agent.

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
        changed_files = initial_changed_files[:]  # Copy the list
        qa_summary_log = []  # Log QA agent summaries

        # Extract values from domain objects
        build_command = context.build_config.build_command
        repo_root = context.repo_config.repo_path
        remediation_id = context.remediation_id

        while qa_attempts < max_qa_attempts:
            qa_attempts += 1
            log(f"\n--- QA Attempt {qa_attempts}/{max_qa_attempts} ---")

            # Try building first
            build_success, build_output = run_build_command(build_command, repo_root, remediation_id)

            if build_success:
                log(f"✅ Build succeeded on QA attempt {qa_attempts}")
                break
            else:
                log(f"❌ Build failed on QA attempt {qa_attempts}")
                error_analysis = extract_build_errors(build_output)
                log(f"Build errors:\n{error_analysis}")

                # Run QA agent to fix the build
                try:
                    qa_summary = self._run_qa_agent(context, build_output, changed_files)
                    qa_summary_log.append(qa_summary)

                    # Update changed files list from git status (files that have been modified)
                    import src.git_handler as git_handler
                    changed_files = git_handler.get_last_commit_changed_files()

                    log(f"QA Agent completed attempt {qa_attempts}.")

                except Exception as e:
                    error_msg = f"Error during QA agent execution: {str(e)}"
                    log(error_msg, is_error=True)
                    qa_summary_log.append(error_msg)
                    return False, changed_files, error_msg, qa_summary_log

        # Final result
        used_build_command = build_command if build_command else None

        return build_success, changed_files, used_build_command, qa_summary_log

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

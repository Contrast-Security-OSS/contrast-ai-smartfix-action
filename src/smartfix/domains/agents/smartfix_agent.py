"""
SmartFixAgent - Internal Contrast AI SmartFix coding agent implementation.

This module contains the SmartFixAgent class which orchestrates the Fix Agent + QA Agent
workflow for vulnerability remediation without git operations.
"""

import datetime

from src.qa_handler import run_qa_loop, run_build_command
from src.agent_handler import run_ai_fix_agent
from src.build_output_analyzer import extract_build_errors

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
                # Call the real agent_handler function with the context
                fix_result = run_ai_fix_agent(context)
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
                    # Use the new run_qa_loop signature that accepts RemediationContext
                    success, changed_files, error_message, qa_logs = run_qa_loop(
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

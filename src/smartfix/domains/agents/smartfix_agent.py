"""
SmartFixAgent - Internal Contrast AI SmartFix coding agent implementation.

This module contains the SmartFixAgent class which orchestrates the Fix Agent
workflow for vulnerability remediation. The Fix agent uses a BuildTool to
verify its changes compile correctly — no separate QA agent is needed.
"""

import re
from typing import Optional

from src.smartfix.domains.agents.event_loop_utils import _run_agent_in_event_loop, _run_agent_internal_with_prompts
from src.smartfix.domains.agents.build_tool import (
    create_build_tool,
    get_successful_build_command,
    reset_storage,
)
from src.utils import debug_log, log, error_exit
from src.smartfix.shared.failure_categories import FailureCategory
from src import telemetry_handler

from .coding_agent import CodingAgentStrategy
from .directory_tree_utils import get_directory_tree_for_agent_prompt
from .agent_session import AgentSession
from src.smartfix.domains.vulnerability import RemediationContext


class SmartFixAgent(CodingAgentStrategy):
    """
    Internal SmartFix coding agent that runs the Fix Agent with a BuildTool.

    The Fix agent has access to a BuildTool that lets it run builds to verify
    changes. A successful recorded build is required (PR gate) before a PR
    can be created.
    """

    def __init__(self) -> None:
        """Initialize SmartFixAgent. Configuration comes from RemediationContext."""
        pass

    def remediate(self, context: RemediationContext) -> AgentSession:
        """
        Execute the complete remediation workflow for a vulnerability.

        Args:
            context: RemediationContext containing vulnerability details and configuration

        Returns:
            AgentSession containing the complete remediation attempt data
        """
        session = AgentSession()

        # Reset BuildTool storage for this remediation run
        reset_storage()

        try:
            # Run fix agent (with BuildTool for build verification)
            fix_result = self._run_fix_agent(session, context)
            if not fix_result:
                return session

            # PR gate: check if the agent verified its changes with a successful build
            if not self._check_pr_gate(session, context):
                return session

            # Success!
            session.complete_session(pr_body=fix_result)
            return session

        except Exception as ex:
            debug_log(f"SmartFix agent failed with error: {str(ex)}")
            session.complete_session(
                failure_category=FailureCategory.AGENT_FAILURE,
                pr_body=f"SmartFix agent failed with error: {str(ex)}"
            )
            return session

    def _check_pr_gate(self, session: AgentSession, context: RemediationContext) -> bool:
        """
        Check PR gate: a successful recorded build is required before PR creation.

        If no build command was available (neither configured nor detected),
        the gate is skipped. Otherwise, the agent must have called BuildTool
        with a real build command that succeeded.

        Returns:
            bool: True if gate passes, False if gate fails
        """
        has_build_config = (
            hasattr(context, 'build_config')
            and context.build_config
            and context.build_config.has_build_command()
        )

        if not has_build_config:
            # No build command available — skip gate
            debug_log("PR gate skipped: no build command configured or detected")
            return True

        recorded_cmd = get_successful_build_command()
        if recorded_cmd is not None:
            # If a configured command exists, the recorded command must match it
            configured_cmd = getattr(context.build_config, 'user_build_command', None)
            if configured_cmd and recorded_cmd.strip() != configured_cmd.strip():
                log(f"PR gate failed: recorded build '{recorded_cmd}' does not match configured '{configured_cmd}'", is_error=True)
                session.complete_session(
                    failure_category=FailureCategory.BUILD_VERIFICATION_FAILED,
                    pr_body=f"Fix agent ran '{recorded_cmd}' but the configured build command is '{configured_cmd}'"
                )
                return False
            debug_log(f"PR gate passed: verified build with '{recorded_cmd}'")
            return True

        # Gate failed — agent had a build command but never verified a successful build
        log("PR gate failed: agent did not verify a successful build", is_error=True)
        session.complete_session(
            failure_category=FailureCategory.BUILD_VERIFICATION_FAILED,
            pr_body="Fix agent did not verify a successful build"
        )
        return False

    def _run_fix_agent(self, session: AgentSession, context: RemediationContext) -> Optional[str]:
        """
        Execute the AI fix agent to generate remediation code.

        Returns:
            str: Fix result on success, None on failure
        """
        try:
            if not hasattr(context, 'prompts') or not hasattr(context, 'repo_config'):
                fix_result = "Error: RemediationContext missing required attributes (prompts, repo_config)"
            else:
                fix_result = self._run_ai_fix_agent(context)
        except Exception as ex:
            debug_log(f"Exception during fix agent execution: {str(ex)}")
            session.complete_session(
                failure_category=FailureCategory.AGENT_FAILURE,
                pr_body="Exception during fix agent execution"
            )
            return None

        if fix_result and not fix_result.startswith("Error"):
            return fix_result
        else:
            debug_log("Fix agent failed with unknown error")
            session.complete_session(
                failure_category=FailureCategory.AGENT_FAILURE,
                pr_body="Fix agent failed with unknown error"
            )
            return None

    def _run_ai_fix_agent(self, context: RemediationContext) -> str:
        """Synchronously runs the AI agent to analyze and apply a fix using API-provided prompts."""

        debug_log("Using API-provided fix prompts")
        debug_log(f"Fix System Prompt Length: {len(context.prompts.fix_system_prompt)} chars")
        debug_log(f"Fix User Prompt Length: {len(context.prompts.fix_user_prompt)} chars")

        log("\n--- Preparing to run AI Agent to Apply Fix ---")
        debug_log(f"Repo Root for Agent Tools: {context.repo_config.repo_path}")
        debug_log(f"Skip Writing Security Test: {context.skip_writing_security_test}")

        try:
            agent_summary_str = self._run_fix_agent_execution(context)
            self._extract_analytics_data(agent_summary_str)
            return self._extract_pr_body(agent_summary_str)

        except Exception as ex:
            log(f"Error running AI fix agent: {ex}", is_error=True)
            failure_code = FailureCategory.AGENT_FAILURE.value
            if "litellm." in str(ex).lower():
                failure_code = FailureCategory.INVALID_LLM_CONFIG.value
            error_exit(context.remediation_id, failure_code)

    def _run_fix_agent_execution(self, context) -> str:
        """Execute the fix agent with BuildTool and return the summary."""
        repo_path = context.repo_config.repo_path
        build_config = context.build_config

        # Create BuildTool for this remediation run
        build_tool = create_build_tool(
            repo_root=repo_path,
            remediation_id=context.remediation_id,
            user_build_command=getattr(build_config, 'user_build_command', None) if build_config else None,
            user_format_command=getattr(build_config, 'user_format_command', None) if build_config else None,
        )

        directory_tree = get_directory_tree_for_agent_prompt(repo_path)

        # Append build/format command instructions if configured
        build_instruction = ""
        if build_config and getattr(build_config, 'user_build_command', None):
            cmd = build_config.user_build_command
            fmt = getattr(build_config, 'user_format_command', None)
            build_instruction = (
                f"\n\nIMPORTANT: A build command has been configured for this project: `{cmd}`. "
                f"You MUST run this exact command using the build_tool at least once to verify "
                f"your changes do not break existing tests. Do NOT add scoping flags like "
                f"`-Dtest=...` or `--tests=...` — run the full configured command as-is."
            )
            if fmt:
                build_instruction += (
                    f"\n\nA formatting command has also been configured: `{fmt}`. "
                    f"Pass this as the `format_command` parameter when calling build_tool "
                    f"so that code is formatted before the build runs."
                )

        fix_user_prompt_with_tree = context.prompts.fix_user_prompt + build_instruction + directory_tree
        agent_summary_str = _run_agent_in_event_loop(
            _run_agent_internal_with_prompts,
            'fix',
            repo_path,
            fix_user_prompt_with_tree,
            context.prompts.fix_system_prompt,
            context.remediation_id,
            context.session_id,
            additional_tools=[build_tool],
        )

        log("--- AI Agent Fix Attempt Completed ---")
        debug_log("\n--- Full Agent Summary ---")
        debug_log(agent_summary_str)
        debug_log("--------------------------")

        if "No MCP tools available" in agent_summary_str or "Proceeding without filesystem tools" in agent_summary_str:
            log("Error during AI fix agent execution: No filesystem tools were available. The agent cannot make changes to files.")
            error_exit(context.remediation_id, FailureCategory.AGENT_FAILURE.value)

        return agent_summary_str

    def _extract_analytics_data(self, agent_summary_str: str) -> None:
        """Extract analytics data from agent response and update telemetry."""
        analytics_match = re.search(r"<analytics>(.*?)</analytics>", agent_summary_str, re.DOTALL)
        if not analytics_match:
            debug_log("Warning: <analytics> tags not found in agent response.")
            return

        analytics_content = analytics_match.group(1).strip()
        debug_log(f"Analytics content found:\\n{analytics_content}")

        confidence_score_line_match = re.search(r"Confidence_Score:\s*(.*)", analytics_content)
        if confidence_score_line_match:
            confidence_str = confidence_score_line_match.group(1).strip()
            if confidence_str:
                telemetry_handler.update_telemetry("resultInfo.confidence", confidence_str)
        else:
            debug_log("Confidence_Score not found in analytics or is empty.")

        prog_lang_match = re.search(r"Programming_Language:\s*(.*)", analytics_content)
        if prog_lang_match:
            programming_language_str = prog_lang_match.group(1).strip()
            if programming_language_str:
                telemetry_handler.update_telemetry("appInfo.programmingLanguage", programming_language_str)
        else:
            debug_log("Programming_Language not found in analytics.")

        tech_stack_match = re.search(r"Technical_Stack:\s*(.*)", analytics_content)
        if tech_stack_match:
            technical_stack_str = tech_stack_match.group(1).strip()
            if technical_stack_str:
                telemetry_handler.update_telemetry("appInfo.technicalStackInfo", technical_stack_str)
        else:
            debug_log("Technical_Stack not found in analytics.")

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

# -
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

"""
Session handling workflow for SmartFix agent results.

This module provides object-oriented handling of agent session results,
including QA section generation, success/failure determination, and validation.
"""

from typing import Optional
from src.smartfix.shared.failure_categories import FailureCategory
from src.utils import log


class SessionResult:
    """
    Encapsulates the result of processing an agent session.

    Attributes:
        should_continue: Whether processing should continue to PR creation
        failure_category: Failure category if session failed
        ai_fix_summary: Summary for successful sessions
    """

    def __init__(self, should_continue: bool, failure_category: Optional[str] = None, ai_fix_summary: Optional[str] = None):
        self.should_continue = should_continue
        self.failure_category = failure_category
        self.ai_fix_summary = ai_fix_summary


class QASectionConfig:
    """
    Configuration for QA section generation.

    Attributes:
        skip_qa_review: Whether QA review was skipped by configuration
        has_build_command: Whether a build command is available
        build_command: The build command used
    """

    def __init__(self, has_build_command: bool, build_command: str):
        self.has_build_command = has_build_command
        self.build_command = build_command


class SessionHandler:
    """
    Handles SmartFix agent session results and generates appropriate responses.

    This class encapsulates the business logic for:
    - Determining session success/failure outcomes
    - Generating QA sections for PR bodies
    """

    def __init__(self):
        pass

    def handle_session_result(self, session) -> SessionResult:
        """
        Handle session result and determine next action.

        Args:
            session: AgentSession with success, failure_category, pr_body properties

        Returns:
            SessionResult: Result indicating whether to continue processing
        """
        if session.success:
            ai_fix_summary = session.pr_body if session.pr_body else "Fix completed successfully"
            return SessionResult(should_continue=True, ai_fix_summary=ai_fix_summary)
        else:
            # Agent failed - determine failure category
            failure_category = (
                session.failure_category.value
                if session.failure_category
                else FailureCategory.AGENT_FAILURE.value
            )
            return SessionResult(should_continue=False, failure_category=failure_category)

    def generate_qa_section(self, session, config: QASectionConfig) -> str:
        """
        Generate the Review section for PR body based on session results.

        Args:
            session: AgentSession with build verification properties
            config: Review section configuration

        Returns:
            str: Review section for PR body
        """

        # Note: At this point session.success must be True
        # (failures are handled by handle_session_result earlier)
        if config.has_build_command:
            qa_section = "\n\n---\n\n## Review \n\n"
            qa_section += f"*   **Build Run:** Yes (`{config.build_command}`)\n"
            qa_section += "*   **Final Build Status:** Success\n"
        else:
            qa_section = ""
            log("Review section skipped: no BUILD_COMMAND was provided.")

        return qa_section


# Factory function for backward compatibility and easy instantiation
def create_session_handler() -> SessionHandler:
    """
    Create a SessionHandler instance.

    Returns:
        SessionHandler: Configured session handler
    """
    return SessionHandler()

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

This module provides structured handling of agent session results,
including QA section generation and success/failure determination.
"""

from typing import NamedTuple, Optional
from src.smartfix.shared.failure_categories import FailureCategory
from src.utils import log


class SessionOutcome(NamedTuple):
    """Structured result of processing an agent session."""
    should_continue: bool
    failure_category: Optional[str]
    ai_fix_summary: Optional[str]


def handle_session_result(session) -> SessionOutcome:
    """
    Handle session result and determine next action.

    Args:
        session: AgentSession with success, failure_category, pr_body properties

    Returns:
        SessionOutcome indicating whether to continue processing
    """
    if session.success:
        return SessionOutcome(
            should_continue=True,
            failure_category=None,
            ai_fix_summary=session.pr_body if session.pr_body else "Fix completed successfully",
        )
    category = (
        session.failure_category.value
        if session.failure_category
        else FailureCategory.AGENT_FAILURE.value
    )
    return SessionOutcome(should_continue=False, failure_category=category, ai_fix_summary=None)


def generate_qa_section(build_command: Optional[str]) -> str:
    """
    Generate the Review section for PR body.

    Only called on the success path, so 'Final Build Status: Success' is intentional.

    Args:
        build_command: The build command used, or None if no build command configured

    Returns:
        Review section string, or empty string if no build command
    """
    if not build_command:
        log("Review section skipped: no BUILD_COMMAND was provided.")
        return ""
    return (
        "\n\n---\n\n## Review \n\n"
        f"*   **Build Run:** Yes (`{build_command}`)\n"
        "*   **Final Build Status:** Success\n"
    )

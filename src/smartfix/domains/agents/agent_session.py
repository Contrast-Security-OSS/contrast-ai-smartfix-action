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

from dataclasses import dataclass
from typing import Optional

from src.smartfix.shared.failure_categories import FailureCategory


@dataclass
class AgentSession:
    """
    Tracks the state and history of a single, complete remediation attempt.
    """
    qa_attempts: int = 0
    final_pr_body: Optional[str] = None
    failure_category: Optional[FailureCategory] = None
    is_complete: bool = False

    def complete_session(self, failure_category: Optional[FailureCategory] = None,
                         pr_body: Optional[str] = None) -> None:
        """Marks the session as complete with optional failure category."""
        self.failure_category = failure_category
        self.final_pr_body = pr_body
        self.is_complete = True

    @property
    def success(self) -> bool:
        """Returns True if the session completed successfully."""
        return self.is_complete and self.failure_category is None

    @property
    def pr_body(self) -> Optional[str]:
        """Returns the final PR body content."""
        return self.final_pr_body

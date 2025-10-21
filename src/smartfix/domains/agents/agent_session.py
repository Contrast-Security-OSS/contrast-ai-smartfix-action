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

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import List, Optional


class AgentSessionStatus(Enum):
    """The final status of an agent session."""
    SUCCESS = auto()
    BUILD_FAILURE = auto()
    MAX_ATTEMPTS_REACHED = auto()
    ERROR = auto()
    IN_PROGRESS = auto()
    FAILURE = auto()  # Used by external_coding_agent


@dataclass
class AgentEvent:
    """Represents a single interaction (prompt/response) with the LLM."""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    prompt: Optional[str] = None
    response: Optional[str] = None


@dataclass
class AgentSession:
    """
    Tracks the state and history of a single, complete remediation attempt.
    """
    status: AgentSessionStatus = AgentSessionStatus.IN_PROGRESS
    events: List[AgentEvent] = field(default_factory=list)
    qa_attempts: int = 0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    final_pr_body: Optional[str] = None

    def complete_session(self, status: AgentSessionStatus, pr_body: Optional[str] = None) -> None:
        """Marks the session as complete."""
        self.status = status
        self.final_pr_body = pr_body
        self.end_time = datetime.now(timezone.utc)

    @property
    def success(self) -> bool:
        """Returns True if the session completed successfully."""
        return self.status == AgentSessionStatus.SUCCESS

    @property
    def pr_body(self) -> Optional[str]:
        """Returns the final PR body content."""
        return self.final_pr_body

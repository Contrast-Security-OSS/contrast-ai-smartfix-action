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

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

from src.smartfix.domains.vulnerability import RemediationContext
from .agent_session import AgentSession


class CodingAgents(Enum):
    """Enumeration of available coding agent types."""
    SMARTFIX = "SMARTFIX"
    GITHUB_COPILOT = "GITHUB_COPILOT"
    CLAUDE_CODE = "CLAUDE_CODE"


class CodingAgentStrategy(ABC):
    """
    Abstract base class defining the interface for a coding agent.
    This allows for a "plug-and-play" architecture where different agents
    (e.g., SmartFix internal, GitHub Copilot) can be used interchangeably.
    """

    @abstractmethod
    def remediate(self, context: RemediationContext) -> AgentSession:
        """
        The primary entry point for an agent to attempt a remediation.

        Args:
            context: The remediation context containing all necessary information
                     about the vulnerability, repository, and configuration.

        Returns:
            An AgentSession object containing the complete remediation attempt,
            including success status, events, costs, and final PR content.
        """
        pass

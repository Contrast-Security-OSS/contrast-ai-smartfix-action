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

from .coding_agent import CodingAgentStrategy
from src.smartfix.shared.coding_agents import CodingAgents
from .smartfix_agent import SmartFixAgent


class AgentFactory:
    """
    Factory class for creating and configuring coding agent instances.

    Provides centralized agent creation with strategy selection logic.
    Configuration is passed through RemediationContext, not at agent creation.
    """

    @staticmethod
    def create_agent(agent_type: CodingAgents) -> CodingAgentStrategy:
        """
        Create a coding agent instance based on the specified type.

        Args:
            agent_type: The type of agent to create

        Returns:
            CodingAgentStrategy: Configured coding agent instance

        Raises:
            ValueError: If agent_type is not supported
        """
        if agent_type == CodingAgents.SMARTFIX:
            return SmartFixAgent()
        else:
            raise ValueError(f"Domain factory only supports SMARTFIX agents. Got: {agent_type}")

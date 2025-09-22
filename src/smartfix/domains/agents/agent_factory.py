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

from typing import Optional, Dict, Any

from .coding_agent import CodingAgentStrategy, CodingAgents
from .smartfix_agent import SmartFixAgent


class AgentFactory:
    """
    Factory class for creating and configuring coding agent instances.

    Provides centralized agent creation with strategy selection logic
    and configuration management.
    """

    @staticmethod
    def create_agent(
        agent_type: CodingAgents,
        config: Optional[Dict[str, Any]] = None
    ) -> CodingAgentStrategy:
        """
        Create a coding agent instance based on the specified type.

        Args:
            agent_type: The type of agent to create
            config: Optional configuration dictionary for agent setup

        Returns:
            CodingAgentStrategy: Configured coding agent instance

        Raises:
            ValueError: If agent_type is not supported
            NotImplementedError: If agent type is not yet implemented
        """
        config = config or {}

        if agent_type == CodingAgents.SMARTFIX:
            max_qa_attempts = config.get('max_qa_attempts', 5)
            return SmartFixAgent(max_qa_attempts=max_qa_attempts)
        else:
            raise ValueError(f"Domain factory only supports SMARTFIX agents. Got: {agent_type}")

    @staticmethod
    def get_default_agent(config: Optional[Dict[str, Any]] = None) -> CodingAgentStrategy:
        """
        Create the default coding agent (SmartFix internal).

        Args:
            config: Optional configuration dictionary

        Returns:
            CodingAgentStrategy: Default SmartFix internal agent
        """
        return AgentFactory.create_agent(CodingAgents.SMARTFIX, config)

    @staticmethod
    def get_available_coding_agents() -> list[CodingAgents]:
        """
        Get list of available coding agent types in the domain layer.

        Returns:
            list[CodingAgents]: List of domain-supported coding agents (SMARTFIX only)
        """
        return [CodingAgents.SMARTFIX]

    @staticmethod
    def is_coding_agent_available(coding_agent: CodingAgents) -> bool:
        """
        Check if a specific coding agent type is available.

        Args:
            coding_agent: Coding agent type to check

        Returns:
            bool: True if coding agent type is available, False otherwise
        """
        return coding_agent in AgentFactory.get_available_coding_agents()

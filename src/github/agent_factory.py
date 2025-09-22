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

from src.smartfix.domains.agents.coding_agent import CodingAgentStrategy, CodingAgents
from src.smartfix.domains.agents.agent_factory import AgentFactory as DomainAgentFactory
from .external_coding_agent import ExternalCodingAgent


class GitHubAgentFactory:
    """
    GitHub-specific agent factory that extends the domain factory capabilities.

    Provides creation of both domain agents (SMARTFIX) and GitHub-specific
    external agents (GITHUB_COPILOT, CLAUDE_CODE).
    """

    @staticmethod
    def create_agent(
        agent_type: CodingAgents,
        config: Optional[Dict[str, Any]] = None
    ) -> CodingAgentStrategy:
        """
        Create a coding agent instance based on the specified type.

        Supports both domain agents and GitHub-specific external agents.

        Args:
            agent_type: The type of agent to create
            config: Optional configuration dictionary for agent setup

        Returns:
            CodingAgentStrategy: Configured coding agent instance

        Raises:
            ValueError: If agent_type is not supported
        """
        config = config or {}

        # Delegate domain agents to the domain factory
        if agent_type == CodingAgents.SMARTFIX:
            return DomainAgentFactory.create_agent(agent_type, config)

        # Handle GitHub-specific external agents
        elif agent_type == CodingAgents.GITHUB_COPILOT:
            from src.config import get_config
            full_config = get_config()
            return ExternalCodingAgent(full_config)

        elif agent_type == CodingAgents.CLAUDE_CODE:
            from src.config import get_config
            full_config = get_config()
            return ExternalCodingAgent(full_config)

        else:
            raise ValueError(f"Unsupported agent type: {agent_type}")

    @staticmethod
    def get_default_agent(config: Optional[Dict[str, Any]] = None) -> CodingAgentStrategy:
        """
        Create the default coding agent (SmartFix internal).

        Args:
            config: Optional configuration dictionary

        Returns:
            CodingAgentStrategy: Default SmartFix internal agent
        """
        return GitHubAgentFactory.create_agent(CodingAgents.SMARTFIX, config)

    @staticmethod
    def get_available_coding_agents() -> list[CodingAgents]:
        """
        Get list of all available coding agent types (domain + GitHub-specific).

        Returns:
            list[CodingAgents]: List of all supported coding agents
        """
        return [
            CodingAgents.SMARTFIX,
            CodingAgents.GITHUB_COPILOT,
            CodingAgents.CLAUDE_CODE
        ]

    @staticmethod
    def is_coding_agent_available(coding_agent: CodingAgents) -> bool:
        """
        Check if a specific coding agent type is available.

        Args:
            coding_agent: Coding agent type to check

        Returns:
            bool: True if coding agent type is available, False otherwise
        """
        return coding_agent in GitHubAgentFactory.get_available_coding_agents()

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

from src.config import Config
from src.smartfix.domains.agents.coding_agent import CodingAgentStrategy, CodingAgents
from src.smartfix.domains.agents.agent_factory import AgentFactory
from .external_coding_agent import ExternalCodingAgent


class GitHubAgentFactory(AgentFactory):
    """
    GitHub-specific agent factory that extends the domain factory capabilities.

    Provides creation of both domain agents (SMARTFIX) and GitHub-specific
    external agents (GITHUB_COPILOT, CLAUDE_CODE).
    """

    @staticmethod
    def create_agent(agent_type: CodingAgents, config: Config) -> CodingAgentStrategy:
        """
        Create a coding agent instance based on the specified type.

        Supports both domain agents and GitHub-specific external agents.

        Args:
            agent_type: The type of agent to create
            config: The application configuration object

        Returns:
            CodingAgentStrategy: Configured coding agent instance

        Raises:
            ValueError: If agent_type is not supported
        """
        # Delegate domain agents to the parent factory
        if agent_type == CodingAgents.SMARTFIX:
            return AgentFactory.create_agent(agent_type, config)

        # Handle GitHub-specific external agents
        elif agent_type in (CodingAgents.GITHUB_COPILOT, CodingAgents.CLAUDE_CODE):
            return ExternalCodingAgent(config)

        else:
            raise ValueError(f"Unsupported agent type: {agent_type}")

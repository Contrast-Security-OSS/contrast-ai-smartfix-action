"""AI Agent Orchestration Domain

This domain handles AI agent management, coding strategies, and
agent coordination for vulnerability remediation.

Key Components:
- SmartFixAgent: Main agent interface and implementation
- AgentSession: Stateful agent interaction management
- CodingAgentStrategy: Strategy pattern for different coding agents
- AgentFactory: Factory for creating and configuring agents
"""

from .coding_agent import CodingAgentStrategy, CodingAgents
from .smartfix_agent import SmartFixAgent
from .agent_factory import AgentFactory
from .agent_session import AgentSession, AgentSessionStatus, AgentEvent

__all__ = [
    'CodingAgentStrategy',
    'CodingAgents',
    'SmartFixAgent',
    'AgentFactory',
    'AgentSession',
    'AgentSessionStatus',
    'AgentEvent',
]

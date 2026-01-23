"""Shared patches for agent orchestration tests.

This module provides reusable patch lists for testing agent-related functionality
including AI agents, event loops, sub-agents, and MCP server management.
"""

# Agent execution patches - prevent actual AI agent calls
AGENT_EXECUTION_PATCHES = [
    'src.smartfix.domains.agents.smartfix_agent.SmartFixAgent._run_ai_fix_agent',
    'src.smartfix.domains.agents.smartfix_agent.SmartFixAgent._run_ai_qa_agent',
    'src.smartfix.domains.agents.external_coding_agent.create_external_coding_agent',
]

# Event loop patches - prevent actual async event loop operations
EVENT_LOOP_PATCHES = [
    'src.smartfix.domains.agents.event_loop_utils._run_agent_in_event_loop',
    'asyncio.new_event_loop',
    'asyncio.set_event_loop',
    'asyncio.get_event_loop',
]

# Sub-agent execution patches - prevent actual sub-agent spawning
SUB_AGENT_PATCHES = [
    'src.smartfix.domains.agents.sub_agent_executor.execute_sub_agent',
    'src.smartfix.domains.agents.sub_agent_executor.collect_results',
]

# MCP server patches - prevent actual MCP connections
MCP_PATCHES = [
    'src.smartfix.domains.agents.mcp_manager.MCPManager.connect',
    'src.smartfix.domains.agents.mcp_manager.MCPManager.disconnect',
    'src.smartfix.domains.agents.mcp_manager.MCPManager.discover_tools',
]

# Combined agent orchestration patches (all of the above)
AGENT_ORCHESTRATION_PATCHES = (
    AGENT_EXECUTION_PATCHES
    + EVENT_LOOP_PATCHES
    + SUB_AGENT_PATCHES
    + MCP_PATCHES
)

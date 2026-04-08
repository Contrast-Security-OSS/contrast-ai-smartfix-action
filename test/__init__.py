# This file makes the test directory a Python package.
# It also installs sys.modules mocks for google.adk BEFORE any test file is
# imported, so that modules depending on google.adk can be imported without a
# real (and potentially broken) google-adk installation.
# Note: conftest.py does the same thing for pytest runs; this file covers
# plain `python -m unittest discover` runs.

import sys
from unittest.mock import MagicMock


class _MockLlmAgent:
    """Mock base class for LlmAgent."""
    def __init__(self, *args, **kwargs):
        self.name = kwargs.get('name', 'mock-agent')
        self.model = kwargs.get('model')

    @property
    def canonical_model(self):
        return self.model


_mock_llm_agent_module = MagicMock()
_mock_llm_agent_module.Agent = MagicMock

_mock_agents_module = MagicMock()
_mock_agents_module.llm_agent = _mock_llm_agent_module
_mock_agents_module.LlmAgent = _MockLlmAgent

_mock_mcp_tool_module = MagicMock()
_mock_mcp_tool_module.mcp_toolset = MagicMock()
_mock_mcp_tool_module.mcp_toolset.MCPToolset = MagicMock
_mock_mcp_tool_module.mcp_toolset.StdioServerParameters = MagicMock
_mock_mcp_tool_module.mcp_toolset.StdioConnectionParams = MagicMock

_mock_tools_module = MagicMock()
_mock_tools_module.mcp_tool = _mock_mcp_tool_module

_mock_models_module = MagicMock()
_mock_models_module.lite_llm = MagicMock()
_mock_models_module.lite_llm.LiteLlm = MagicMock
_mock_models_module.lite_llm._get_completion_inputs = MagicMock()
_mock_models_module.llm_request = MagicMock()
_mock_models_module.llm_request.LlmRequest = MagicMock
_mock_models_module.llm_response = MagicMock()
_mock_models_module.llm_response.LlmResponse = MagicMock

_mock_adk = MagicMock()
_mock_adk.agents = _mock_agents_module
_mock_adk.models = _mock_models_module
_mock_adk.tools = _mock_tools_module

sys.modules.setdefault('google', MagicMock())
sys.modules['google.adk'] = _mock_adk
sys.modules['google.adk.agents'] = _mock_agents_module
sys.modules['google.adk.agents.llm_agent'] = _mock_llm_agent_module
sys.modules['google.adk.tools'] = _mock_tools_module
sys.modules['google.adk.tools.mcp_tool'] = _mock_mcp_tool_module
sys.modules['google.adk.tools.mcp_tool.mcp_toolset'] = _mock_mcp_tool_module.mcp_toolset
sys.modules['google.adk.models'] = _mock_models_module
sys.modules['google.adk.models.lite_llm'] = _mock_models_module.lite_llm
sys.modules['google.adk.models.llm_request'] = _mock_models_module.llm_request
sys.modules['google.adk.models.llm_response'] = _mock_models_module.llm_response
sys.modules.setdefault('google.genai', MagicMock())
sys.modules.setdefault('google.genai.types', MagicMock())

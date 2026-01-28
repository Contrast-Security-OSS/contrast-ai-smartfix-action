"""Test configuration and setup for pytest.

This file is automatically loaded by pytest and sets up the Python path
so that all test files can import from src without path manipulation.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add the project root to Python path so that 'src' imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Add test directory to path for test helpers
test_dir = Path(__file__).parent
sys.path.insert(0, str(test_dir))

# === Global ADK Mock Setup ===
# Set up comprehensive ADK mocks BEFORE any test files import ADK modules.
# This ensures all tests use the same mock hierarchy and prevents import errors.

# Create a mock LlmAgent class that can be inherited from
class MockLlmAgent:
    """Mock base class for LlmAgent to allow SmartFixLlmAgent to inherit properly."""
    def __init__(self, *args, **kwargs):
        self.name = kwargs.get('name', 'mock-agent')
        self.model = kwargs.get('model')

    @property
    def canonical_model(self):
        """Return the model, mimicking LlmAgent behavior."""
        return self.model

# Create comprehensive mock hierarchy for google.adk to prevent __init__.py import errors
mock_llm_agent_module = MagicMock()
mock_llm_agent_module.Agent = MagicMock

mock_agents_module = MagicMock()
mock_agents_module.llm_agent = mock_llm_agent_module
mock_agents_module.LlmAgent = MockLlmAgent

mock_mcp_tool_module = MagicMock()
mock_mcp_tool_module.mcp_toolset = MagicMock()
mock_mcp_tool_module.mcp_toolset.MCPToolset = MagicMock
mock_mcp_tool_module.mcp_toolset.StdioServerParameters = MagicMock
mock_mcp_tool_module.mcp_toolset.StdioConnectionParams = MagicMock

mock_tools_module = MagicMock()
mock_tools_module.mcp_tool = mock_mcp_tool_module

mock_models_module = MagicMock()
mock_models_module.lite_llm = MagicMock()
mock_models_module.lite_llm.LiteLlm = MagicMock
mock_models_module.lite_llm._get_completion_inputs = MagicMock()
mock_models_module.llm_request = MagicMock()
mock_models_module.llm_request.LlmRequest = MagicMock
mock_models_module.llm_response = MagicMock()
mock_models_module.llm_response.LlmResponse = MagicMock

mock_adk = MagicMock()
mock_adk.agents = mock_agents_module
mock_adk.models = mock_models_module
mock_adk.tools = mock_tools_module

# Set up all the module mocks to prevent import errors
sys.modules['google'] = MagicMock()
sys.modules['google.adk'] = mock_adk
sys.modules['google.adk.agents'] = mock_agents_module
sys.modules['google.adk.agents.llm_agent'] = mock_llm_agent_module
sys.modules['google.adk.tools'] = mock_tools_module
sys.modules['google.adk.tools.mcp_tool'] = mock_mcp_tool_module
sys.modules['google.adk.tools.mcp_tool.mcp_toolset'] = mock_mcp_tool_module.mcp_toolset
sys.modules['google.adk.models'] = mock_models_module
sys.modules['google.adk.models.lite_llm'] = mock_models_module.lite_llm
sys.modules['google.adk.models.llm_request'] = mock_models_module.llm_request
sys.modules['google.adk.models.llm_response'] = mock_models_module.llm_response
sys.modules['google.genai'] = MagicMock()
sys.modules['google.genai.types'] = MagicMock()

# === Test Fixture: Reset Config Detection Flag ===
# Import pytest for fixture creation
try:
    import pytest

    @pytest.fixture(autouse=True)
    def reset_config_detection_flag():
        """Reset Config._detection_completed flag before each test.

        This ensures that each test can trigger build/format command detection
        without being blocked by the recursion prevention flag.
        """
        from src.config import Config
        Config._detection_completed = False
        yield
        # Cleanup after test (optional, but good practice)
        Config._detection_completed = False
except ImportError:
    # pytest not available (e.g., when running with unittest directly)
    # Tests using unittest will need to manually reset the flag
    pass

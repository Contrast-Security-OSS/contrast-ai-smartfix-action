#!/usr/bin/env python3
"""Unit tests for agent infrastructure components.

This module tests the low-level agent infrastructure including:
- MCPToolsetManager: MCP server connection and tool management
- SubAgentExecutor: Sub-agent creation and execution logic
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
import asyncio
import os
import tempfile

# ADK mocks are set up globally in conftest.py before any imports
from src.smartfix.domains.agents.mcp_manager import MCPToolsetManager  # noqa: E402
from src.smartfix.domains.agents.sub_agent_executor import SubAgentExecutor  # noqa: E402


class TestMCPToolsetManager(unittest.TestCase):
    """Test cases for MCPToolsetManager."""

    def setUp(self):
        """Set up required environment variables for tests."""
        # Store original values to restore in tearDown
        self._original_env = {
            'GITHUB_WORKSPACE': os.environ.get('GITHUB_WORKSPACE'),
            'GITHUB_REPOSITORY': os.environ.get('GITHUB_REPOSITORY'),
            'GITHUB_SERVER_URL': os.environ.get('GITHUB_SERVER_URL'),
            'GITHUB_TOKEN': os.environ.get('GITHUB_TOKEN'),
        }

        os.environ['GITHUB_WORKSPACE'] = tempfile.gettempdir()
        os.environ['GITHUB_REPOSITORY'] = 'test/repo'
        os.environ['GITHUB_SERVER_URL'] = 'https://github.com'
        os.environ['GITHUB_TOKEN'] = 'test-token'
        os.environ.setdefault('CONTRAST_HOST', 'test.contrastsecurity.com')
        os.environ.setdefault('CONTRAST_ORG_ID', 'test-org')
        os.environ.setdefault('CONTRAST_APP_ID', 'test-app')
        os.environ.setdefault('CONTRAST_AUTHORIZATION_KEY', 'test-auth')
        os.environ.setdefault('CONTRAST_API_KEY', 'test-api-key')

    def tearDown(self):
        """Restore original environment variables."""
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_initialization_default_platform(self):
        """Test MCPToolsetManager initialization with default platform."""
        manager = MCPToolsetManager()

        self.assertIsNotNone(manager.platform)
        self.assertIsInstance(manager.max_retries, int)
        self.assertEqual(manager.max_retries, 3)
        self.assertEqual(manager.retry_delay, 2)
        self.assertIsNotNone(manager.mcp_package)

    def test_initialization_windows_platform(self):
        """Test MCPToolsetManager initialization with Windows platform."""
        manager = MCPToolsetManager(platform_name='Windows')

        self.assertEqual(manager.platform, 'Windows')
        self.assertTrue(manager.is_windows)
        self.assertEqual(manager.connection_timeout, 180)
        self.assertEqual(manager.tools_timeout, 120.0)

    def test_initialization_non_windows_platform(self):
        """Test MCPToolsetManager initialization with non-Windows platform."""
        manager = MCPToolsetManager(platform_name='Linux')

        self.assertEqual(manager.platform, 'Linux')
        self.assertFalse(manager.is_windows)
        self.assertEqual(manager.connection_timeout, 120)
        self.assertEqual(manager.tools_timeout, 30.0)

    def test_build_npx_args(self):
        """Test building npx arguments for MCP server."""
        manager = MCPToolsetManager()
        target_folder = '/test/folder'

        args = manager._build_npx_args(target_folder)

        self.assertIsInstance(args, list)
        self.assertIn('-y', args)
        self.assertIn('--cache', args)
        self.assertIn('--prefer-offline', args)
        self.assertIn(target_folder, args)
        self.assertTrue(any('@modelcontextprotocol/server-filesystem' in arg for arg in args))

    @patch('src.smartfix.domains.agents.mcp_manager.MCPToolset')
    def test_create_toolset(self, mock_toolset_class):
        """Test creating MCP toolset with proper parameters."""
        manager = MCPToolsetManager(platform_name='Linux')

        # Run async test
        async def test_async():
            return await manager._create_toolset('/test/folder')

        asyncio.run(test_async())

        # Verify MCPToolset was called with correct parameters
        mock_toolset_class.assert_called_once()
        call_kwargs = mock_toolset_class.call_args[1]
        self.assertIn('connection_params', call_kwargs)

    @patch('src.smartfix.domains.agents.mcp_manager.MCPToolset')
    def test_get_tools_success(self, mock_toolset_class):
        """Test successful get_tools call."""
        # Create mock toolset with async get_tools
        mock_toolset = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = 'test_tool'
        mock_toolset.get_tools = AsyncMock(return_value=[mock_tool])
        mock_toolset_class.return_value = mock_toolset

        manager = MCPToolsetManager()
        target_folder = Path('/test/folder')

        result = asyncio.run(manager.get_tools(target_folder, 'test-remediation-id'))

        self.assertEqual(result, mock_toolset)

    @patch('src.smartfix.domains.agents.mcp_manager.MCPToolset')
    def test_get_tools_failure(self, mock_toolset_class):
        """Test get_tools failure handling."""
        # Make get_tools raise an exception
        mock_toolset = MagicMock()
        mock_toolset.get_tools = AsyncMock(side_effect=Exception('Connection failed'))
        mock_toolset_class.return_value = mock_toolset

        manager = MCPToolsetManager()
        target_folder = Path('/test/folder')

        # Verify RuntimeError is raised when MCP connection fails
        with self.assertRaises(RuntimeError) as context:
            asyncio.run(manager.get_tools(target_folder, 'test-remediation-id'))

        # Verify error message contains expected text
        self.assertIn('Failed to connect to Filesystem MCP server', str(context.exception))

    @patch('subprocess.run')
    def test_clear_npm_cache_success(self, mock_subprocess):
        """Test successful npm cache clearing."""
        manager = MCPToolsetManager()

        asyncio.run(manager._clear_npm_cache())

        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        self.assertEqual(call_args, ['npm', 'cache', 'clean', '--force'])

    @patch('subprocess.run')
    def test_clear_npm_cache_failure(self, mock_subprocess):
        """Test npm cache clearing handles errors gracefully."""
        mock_subprocess.side_effect = Exception('npm not found')

        manager = MCPToolsetManager()

        # Should not raise exception
        asyncio.run(manager._clear_npm_cache())


class TestSubAgentExecutor(unittest.TestCase):
    """Test cases for SubAgentExecutor."""

    def test_initialization_default_max_events(self):
        """Test SubAgentExecutor initialization with default max_events."""
        with patch('src.config.get_config') as mock_config:
            config_mock = MagicMock()
            config_mock.MAX_EVENTS_PER_AGENT = 100
            mock_config.return_value = config_mock

            executor = SubAgentExecutor()

            self.assertEqual(executor.max_events, 100)
            self.assertIsNotNone(executor.mcp_manager)
            self.assertIsInstance(executor.mcp_manager, MCPToolsetManager)

    def test_initialization_custom_max_events(self):
        """Test SubAgentExecutor initialization with custom max_events."""
        with patch('src.config.get_config'):
            executor = SubAgentExecutor(max_events=50)

            self.assertEqual(executor.max_events, 50)

    @patch('src.smartfix.domains.agents.sub_agent_executor.SmartFixLlmAgent')
    @patch('src.smartfix.domains.agents.sub_agent_executor.SmartFixLiteLlm')
    @patch('src.config.get_config')
    def test_create_agent_success(self, mock_get_config, mock_litellm, mock_agent):
        """Test successful agent creation."""
        # Mock config
        config_mock = MagicMock()
        config_mock.AGENT_MODEL = 'test-model'
        config_mock.USE_CONTRAST_LLM = 'false'
        mock_get_config.return_value = config_mock

        # Mock MCP manager
        mock_mcp_tools = MagicMock()

        executor = SubAgentExecutor()
        executor.mcp_manager.get_tools = AsyncMock(return_value=mock_mcp_tools)

        # Mock agent creation
        mock_agent_instance = MagicMock()
        mock_agent.return_value = mock_agent_instance

        result = asyncio.run(executor.create_agent(
            target_folder=Path('/test'),
            remediation_id='test-123',
            session_id='test-session-123',
            agent_type='fix',
            system_prompt='Test prompt'
        ))

        self.assertEqual(result, mock_agent_instance)
        mock_agent.assert_called_once()

    @patch('src.smartfix.domains.agents.sub_agent_executor.SmartFixLlmAgent')
    @patch('src.smartfix.domains.agents.sub_agent_executor.SmartFixLiteLlm')
    @patch('src.config.get_config')
    def test_create_agent_with_contrast_llm(self, mock_get_config, mock_litellm, mock_agent):
        """Test agent creation with Contrast LLM configuration."""
        # Mock config with Contrast LLM enabled
        config_mock = MagicMock()
        config_mock.AGENT_MODEL = 'test-model'
        config_mock.USE_CONTRAST_LLM = 'true'
        config_mock.CONTRAST_API_KEY = 'test-api-key'
        config_mock.CONTRAST_AUTHORIZATION_KEY = 'test-auth-key'
        mock_get_config.return_value = config_mock

        # Mock MCP manager
        mock_mcp_tools = MagicMock()

        executor = SubAgentExecutor()
        executor.mcp_manager.get_tools = AsyncMock(return_value=mock_mcp_tools)

        # Mock agent creation
        mock_agent_instance = MagicMock()
        mock_agent.return_value = mock_agent_instance

        result = asyncio.run(executor.create_agent(
            target_folder=Path('/test'),
            remediation_id='test-123',
            session_id='session-456',
            agent_type='qa',
            system_prompt='QA test prompt'
        ))

        self.assertEqual(result, mock_agent_instance)
        mock_agent.assert_called_once()

        # Verify LiteLLM was called with extra_headers
        mock_litellm.assert_called_once()
        call_kwargs = mock_litellm.call_args[1]
        self.assertIn('extra_headers', call_kwargs)
        headers = call_kwargs['extra_headers']
        self.assertEqual(headers['Api-Key'], 'test-api-key')
        self.assertEqual(headers['Authorization'], 'test-auth-key')
        self.assertEqual(headers['x-contrast-llm-session-id'], 'session-456')

    @patch('src.smartfix.domains.agents.sub_agent_executor.error_exit')
    @patch('src.config.get_config')
    def test_create_agent_no_mcp_tools(self, mock_get_config, mock_error_exit):
        """Test agent creation fails when no MCP tools available."""
        # Mock config
        config_mock = MagicMock()
        mock_get_config.return_value = config_mock

        executor = SubAgentExecutor()
        executor.mcp_manager.get_tools = AsyncMock(return_value=None)

        asyncio.run(executor.create_agent(
            target_folder=Path('/test'),
            remediation_id='test-123',
            session_id='test-session-123',
            agent_type='fix',
            system_prompt='Test prompt'
        ))

        mock_error_exit.assert_called()

    @patch('src.smartfix.domains.agents.sub_agent_executor.error_exit')
    @patch('src.config.get_config')
    def test_create_agent_no_system_prompt(self, mock_get_config, mock_error_exit):
        """Test agent creation fails when no system prompt provided."""
        # Mock config
        config_mock = MagicMock()
        mock_get_config.return_value = config_mock

        executor = SubAgentExecutor()
        executor.mcp_manager.get_tools = AsyncMock(return_value=MagicMock())

        asyncio.run(executor.create_agent(
            target_folder=Path('/test'),
            remediation_id='test-123',
            session_id='test-session-123',
            agent_type='fix',
            system_prompt=None
        ))

        mock_error_exit.assert_called()

    def test_collect_statistics_success(self):
        """Test successful statistics collection."""
        executor = SubAgentExecutor()

        # Mock agent with stats
        mock_agent = MagicMock()
        mock_agent.gather_accumulated_stats_dict.return_value = {
            'token_usage': {'total_tokens': 1000},
            'cost_analysis': {'total_cost': 0.05}
        }

        total_tokens, total_cost = executor._collect_statistics(mock_agent)

        self.assertEqual(total_tokens, 1000)
        self.assertEqual(total_cost, 0.05)

    def test_collect_statistics_with_dollar_sign(self):
        """Test statistics collection with dollar sign in cost."""
        executor = SubAgentExecutor()

        # Mock agent with stats including $ sign
        mock_agent = MagicMock()
        mock_agent.gather_accumulated_stats_dict.return_value = {
            'token_usage': {'total_tokens': 1000},
            'cost_analysis': {'total_cost': '$0.05'}
        }

        total_tokens, total_cost = executor._collect_statistics(mock_agent)

        self.assertEqual(total_tokens, 1000)
        self.assertEqual(total_cost, 0.05)

    def test_collect_statistics_error_handling(self):
        """Test statistics collection handles errors gracefully."""
        executor = SubAgentExecutor()

        # Mock agent that raises AttributeError (one of the caught exceptions)
        mock_agent = MagicMock()
        mock_agent.gather_accumulated_stats_dict.side_effect = AttributeError('Stats error')

        total_tokens, total_cost = executor._collect_statistics(mock_agent)

        # Should return defaults on error
        self.assertEqual(total_tokens, 0)
        self.assertEqual(total_cost, 0.0)

    def test_process_content_with_text(self):
        """Test processing event content with text."""
        executor = SubAgentExecutor()

        # Mock event with text content
        mock_event = MagicMock()
        mock_event.content.text = 'Agent response text'

        result = executor._process_content(mock_event, 'fix')

        self.assertEqual(result, 'Agent response text')

    def test_process_content_with_parts(self):
        """Test processing event content with parts."""
        executor = SubAgentExecutor()

        # Mock event with parts (no text attribute)
        mock_event = MagicMock()
        # Remove the text attribute so hasattr returns False
        del mock_event.content.text
        mock_part = MagicMock()
        mock_part.text = 'Part text'
        mock_event.content.parts = [mock_part]

        result = executor._process_content(mock_event, 'fix')

        self.assertEqual(result, 'Part text')

    def test_process_content_no_content(self):
        """Test processing event with no content."""
        executor = SubAgentExecutor()

        # Mock event with no content
        mock_event = MagicMock()
        mock_event.content = None

        result = executor._process_content(mock_event, 'fix')

        self.assertIsNone(result)

    def test_process_function_calls(self):
        """Test processing function calls from event."""
        executor = SubAgentExecutor()
        telemetry = []

        # Mock event with function calls
        mock_event = MagicMock()
        mock_call = MagicMock()
        mock_call.name = 'read_file'
        mock_call.args = {'path': '/test/file.py'}
        mock_event.get_function_calls.return_value = [mock_call]

        executor._process_function_calls(mock_event, 'fix', telemetry)

        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]['tool'], 'read_file')
        self.assertEqual(telemetry[0]['result'], 'CALLING')

    def test_process_function_responses_success(self):
        """Test processing successful function responses."""
        executor = SubAgentExecutor()
        telemetry = []

        # Mock event with function response
        mock_event = MagicMock()
        mock_response = MagicMock()
        mock_response.name = 'read_file'
        mock_response.response = 'isError = False, content = file contents'
        mock_event.get_function_responses.return_value = [mock_response]

        executor._process_function_responses(mock_event, 'fix', telemetry)

        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]['tool'], 'read_file')
        self.assertEqual(telemetry[0]['result'], 'SUCCESS')

    def test_process_function_responses_failure(self):
        """Test processing failed function responses."""
        executor = SubAgentExecutor()
        telemetry = []

        # Mock event with error response
        mock_event = MagicMock()
        mock_response = MagicMock()
        mock_response.name = 'write_file'
        mock_response.response = 'isError = True, error = permission denied'
        mock_event.get_function_responses.return_value = [mock_response]

        executor._process_function_responses(mock_event, 'fix', telemetry)

        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]['tool'], 'write_file')
        self.assertEqual(telemetry[0]['result'], 'FAILURE')


def run_async_test(coro):
    """Helper to run async tests."""
    return asyncio.run(coro)


if __name__ == '__main__':
    unittest.main()

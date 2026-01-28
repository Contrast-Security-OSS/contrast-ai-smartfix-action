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

"""
Tests for sub_agent_executor.py module.

Tests the SubAgentExecutor class including:
- Agent creation (fix and qa agents)
- Event processing and execution
- Telemetry collection
- Error handling and cleanup
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import asyncio

from src.smartfix.domains.agents.sub_agent_executor import SubAgentExecutor


class TestSubAgentExecutorInitialization(unittest.TestCase):
    """Test SubAgentExecutor initialization"""

    def test_init_with_default_max_events(self):
        """
        When SubAgentExecutor is initialized without max_events,
        should use config default value.
        """
        # Arrange & Act
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        # Assert
        self.assertEqual(executor.max_events, 120)
        self.assertIsNotNone(executor.config)
        self.assertIsNotNone(executor.mcp_manager)

    def test_init_with_custom_max_events(self):
        """
        When SubAgentExecutor is initialized with custom max_events,
        should override config default.
        """
        # Arrange & Act
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor(max_events=50)

        # Assert
        self.assertEqual(executor.max_events, 50)


class TestSubAgentExecutorStatisticsCollection(unittest.TestCase):
    """Test statistics collection from agent"""

    def test_collect_statistics_with_valid_data(self):
        """
        When agent has valid statistics,
        should extract total tokens and cost correctly.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_agent = Mock()
        mock_agent.gather_accumulated_stats_dict.return_value = {
            "token_usage": {"total_tokens": 1500},
            "cost_analysis": {"total_cost": "$0.25"}
        }
        mock_agent.gather_accumulated_stats.return_value = '{"token_usage": {"total_tokens": 1500}}'

        # Act
        total_tokens, total_cost = executor._collect_statistics(mock_agent)

        # Assert
        self.assertEqual(total_tokens, 1500)
        self.assertEqual(total_cost, 0.25)

    def test_collect_statistics_with_numeric_cost(self):
        """
        When cost is already numeric (not string with $),
        should return the numeric value directly.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_agent = Mock()
        mock_agent.gather_accumulated_stats_dict.return_value = {
            "token_usage": {"total_tokens": 2000},
            "cost_analysis": {"total_cost": 0.50}
        }
        mock_agent.gather_accumulated_stats.return_value = '{}'

        # Act
        total_tokens, total_cost = executor._collect_statistics(mock_agent)

        # Assert
        self.assertEqual(total_tokens, 2000)
        self.assertEqual(total_cost, 0.50)

    def test_collect_statistics_with_missing_data_returns_defaults(self):
        """
        When agent statistics are missing or malformed,
        should return default values (0, 0.0).
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_agent = Mock()
        mock_agent.gather_accumulated_stats_dict.side_effect = AttributeError("No stats")
        mock_agent.gather_accumulated_stats.return_value = '{}'

        # Act
        total_tokens, total_cost = executor._collect_statistics(mock_agent)

        # Assert
        self.assertEqual(total_tokens, 0)
        self.assertEqual(total_cost, 0.0)


class TestSubAgentExecutorContentProcessing(unittest.TestCase):
    """Test agent content/message processing"""

    def test_process_content_with_text_attribute(self):
        """
        When event has content with text attribute,
        should extract and return the message text.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_event = Mock()
        mock_event.content = Mock()
        mock_event.content.text = "Agent is analyzing the code..."

        # Act
        result = executor._process_content(mock_event, "fix")

        # Assert
        self.assertEqual(result, "Agent is analyzing the code...")

    def test_process_content_with_parts_attribute(self):
        """
        When event has content with parts[0].text,
        should extract message from parts.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_event = Mock()
        # Use spec to ensure content only has 'parts' attribute, not 'text'
        mock_event.content = Mock(spec=['parts'])
        mock_event.content.parts = [Mock(text="Processing vulnerability...")]

        # Act
        result = executor._process_content(mock_event, "qa")

        # Assert
        self.assertEqual(result, "Processing vulnerability...")

    def test_process_content_with_no_content_returns_none(self):
        """
        When event has no content,
        should return None.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_event = Mock()
        mock_event.content = None

        # Act
        result = executor._process_content(mock_event, "fix")

        # Assert
        self.assertIsNone(result)


class TestSubAgentExecutorAgentCreation(unittest.TestCase):
    """Test agent creation functionality"""

    def test_create_agent_fails_when_no_mcp_tools(self):
        """
        When MCP manager returns no tools,
        should call error_exit with AGENT_FAILURE.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config, \
             patch('src.smartfix.domains.agents.sub_agent_executor.error_exit') as mock_error_exit:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            # Make error_exit raise SystemExit to stop execution (simulates real behavior)
            mock_error_exit.side_effect = SystemExit
            executor = SubAgentExecutor()

            # Mock MCP manager to return no tools
            executor.mcp_manager.get_tools = AsyncMock(return_value=None)

            # Act & Assert - should raise SystemExit
            with self.assertRaises(SystemExit):
                asyncio.run(executor.create_agent(
                    target_folder=Path("/tmp/test"),
                    remediation_id="test-123",
                    session_id="session-456",
                    agent_type="fix",
                    system_prompt="Test prompt"
                ))

            # Verify error_exit was called with correct arguments
            mock_error_exit.assert_called_once()
            call_args = mock_error_exit.call_args[0]
            self.assertEqual(call_args[0], "test-123")  # remediation_id
            self.assertIn("AGENT_FAILURE", call_args[1])  # failure category

    def test_create_agent_fails_when_no_system_prompt(self):
        """
        When system_prompt is None,
        should call error_exit with AGENT_FAILURE.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config, \
             patch('src.smartfix.domains.agents.sub_agent_executor.error_exit') as mock_error_exit:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            # Make error_exit raise SystemExit to stop execution
            mock_error_exit.side_effect = SystemExit
            executor = SubAgentExecutor()

            # Mock MCP manager to return tools (valid)
            executor.mcp_manager.get_tools = AsyncMock(return_value=[Mock()])

            # Act & Assert - should raise SystemExit
            with self.assertRaises(SystemExit):
                asyncio.run(executor.create_agent(
                    target_folder=Path("/tmp/test"),
                    remediation_id="test-123",
                    session_id="session-456",
                    agent_type="fix",
                    system_prompt=None
                ))

            # Verify error_exit was called with correct arguments
            mock_error_exit.assert_called_once()
            call_args = mock_error_exit.call_args[0]
            self.assertEqual(call_args[0], "test-123")

    def test_create_agent_success_with_standard_llm(self):
        """
        When all requirements are met and USE_CONTRAST_LLM is False,
        should create agent successfully with standard model.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config, \
             patch('src.smartfix.domains.agents.sub_agent_executor.SmartFixLiteLlm') as mock_llm_class, \
             patch('src.smartfix.domains.agents.sub_agent_executor.SmartFixLlmAgent') as mock_agent_class:

            # Setup config
            mock_config.return_value = Mock(
                MAX_EVENTS_PER_AGENT=120,
                AGENT_MODEL="claude-sonnet-4.5",
                USE_CONTRAST_LLM=False
            )
            executor = SubAgentExecutor()

            # Mock MCP tools
            mock_tools = [Mock()]
            executor.mcp_manager.get_tools = AsyncMock(return_value=mock_tools)

            # Mock LLM and agent creation
            mock_llm_instance = Mock()
            mock_llm_class.return_value = mock_llm_instance
            mock_agent_instance = Mock()
            mock_agent_class.return_value = mock_agent_instance

            # Act
            result = asyncio.run(executor.create_agent(
                target_folder=Path("/tmp/test"),
                remediation_id="test-123",
                session_id="session-456",
                agent_type="fix",
                system_prompt="You are a helpful fix agent"
            ))

            # Assert
            self.assertEqual(result, mock_agent_instance)
            # Verify LLM was created with correct model
            mock_llm_class.assert_called_once()
            call_kwargs = mock_llm_class.call_args[1]
            self.assertEqual(call_kwargs["model"], "claude-sonnet-4.5")
            self.assertEqual(call_kwargs["temperature"], 0.2)
            # Verify agent was created
            mock_agent_class.assert_called_once()
            agent_kwargs = mock_agent_class.call_args[1]
            self.assertEqual(agent_kwargs["name"], "contrast_fix_agent")
            self.assertEqual(agent_kwargs["instruction"], "You are a helpful fix agent")

    def test_create_agent_success_with_contrast_llm(self):
        """
        When USE_CONTRAST_LLM is True,
        should create agent with Contrast LLM and custom headers.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config, \
             patch('src.smartfix.domains.agents.sub_agent_executor.SmartFixLiteLlm') as mock_llm_class, \
             patch('src.smartfix.domains.agents.sub_agent_executor.SmartFixLlmAgent') as mock_agent_class, \
             patch('src.smartfix.domains.agents.sub_agent_executor.setup_contrast_provider') as mock_setup:

            # Setup config with Contrast LLM
            mock_config.return_value = Mock(
                MAX_EVENTS_PER_AGENT=120,
                USE_CONTRAST_LLM=True,
                CONTRAST_API_KEY="test-api-key",
                CONTRAST_AUTHORIZATION_KEY="test-auth-key"
            )
            executor = SubAgentExecutor()

            # Mock MCP tools
            mock_tools = [Mock()]
            executor.mcp_manager.get_tools = AsyncMock(return_value=mock_tools)

            # Mock LLM and agent creation
            mock_llm_instance = Mock()
            mock_llm_class.return_value = mock_llm_instance
            mock_agent_instance = Mock()
            mock_agent_class.return_value = mock_agent_instance

            # Act
            result = asyncio.run(executor.create_agent(
                target_folder=Path("/tmp/test"),
                remediation_id="test-123",
                session_id="session-456",
                agent_type="qa",
                system_prompt="You are a helpful QA agent"
            ))

            # Assert
            self.assertEqual(result, mock_agent_instance)
            # Verify setup_contrast_provider was called
            mock_setup.assert_called_once()
            # Verify LLM was created with Contrast config and headers
            mock_llm_class.assert_called_once()
            call_kwargs = mock_llm_class.call_args[1]
            self.assertIn("extra_headers", call_kwargs)
            headers = call_kwargs["extra_headers"]
            self.assertEqual(headers["Api-Key"], "test-api-key")
            self.assertEqual(headers["Authorization"], "test-auth-key")
            self.assertEqual(headers["x-contrast-llm-session-id"], "session-456")
            # Verify agent was created with qa name
            mock_agent_class.assert_called_once()
            agent_kwargs = mock_agent_class.call_args[1]
            self.assertEqual(agent_kwargs["name"], "contrast_qa_agent")

    def test_create_agent_handles_creation_exception(self):
        """
        When agent creation throws an exception,
        should call error_exit with INVALID_LLM_CONFIG.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config, \
             patch('src.smartfix.domains.agents.sub_agent_executor.SmartFixLiteLlm') as mock_llm_class, \
             patch('src.smartfix.domains.agents.sub_agent_executor.error_exit') as mock_error_exit:

            mock_config.return_value = Mock(
                MAX_EVENTS_PER_AGENT=120,
                AGENT_MODEL="claude-sonnet-4.5",
                USE_CONTRAST_LLM=False
            )
            # Make error_exit raise SystemExit
            mock_error_exit.side_effect = SystemExit
            executor = SubAgentExecutor()

            # Mock MCP tools
            executor.mcp_manager.get_tools = AsyncMock(return_value=[Mock()])

            # Make LLM creation throw an exception
            mock_llm_class.side_effect = Exception("Invalid model configuration")

            # Act & Assert - should raise SystemExit
            with self.assertRaises(SystemExit):
                asyncio.run(executor.create_agent(
                    target_folder=Path("/tmp/test"),
                    remediation_id="test-123",
                    session_id="session-456",
                    agent_type="fix",
                    system_prompt="Test prompt"
                ))

            # Verify error_exit was called with INVALID_LLM_CONFIG
            mock_error_exit.assert_called_once()
            call_args = mock_error_exit.call_args[0]
            self.assertEqual(call_args[0], "test-123")
            self.assertIn("INVALID_LLM_CONFIG", call_args[1])


class TestSubAgentExecutorFunctionProcessing(unittest.TestCase):
    """Test function call and response processing"""

    def test_process_function_calls_with_multiple_calls(self):
        """
        When event has multiple function calls,
        should process each call and add to telemetry.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_event = Mock()
        mock_call1 = Mock()
        mock_call1.name = "read_file"
        mock_call1.args = {"path": "/test/file.py"}
        mock_call2 = Mock()
        mock_call2.name = "write_file"
        mock_call2.args = {"path": "/test/output.py", "content": "test"}
        mock_event.get_function_calls.return_value = [mock_call1, mock_call2]

        telemetry = []

        # Act
        executor._process_function_calls(mock_event, "fix", telemetry)

        # Assert
        self.assertEqual(len(telemetry), 2)
        self.assertEqual(telemetry[0]["tool"], "read_file")
        self.assertEqual(telemetry[0]["result"], "CALLING")
        self.assertEqual(telemetry[1]["tool"], "write_file")
        self.assertEqual(telemetry[1]["result"], "CALLING")

    def test_process_function_calls_with_no_calls(self):
        """
        When event has no function calls,
        should not add anything to telemetry.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_event = Mock()
        mock_event.get_function_calls.return_value = None

        telemetry = []

        # Act
        executor._process_function_calls(mock_event, "fix", telemetry)

        # Assert
        self.assertEqual(len(telemetry), 0)

    def test_process_function_responses_with_success(self):
        """
        When response contains isError=False,
        should mark as SUCCESS in telemetry.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_event = Mock()
        mock_response = Mock()
        mock_response.name = "read_file"
        mock_response.response = "File read successfully, isError=False"
        mock_event.get_function_responses.return_value = [mock_response]

        telemetry = []

        # Act
        executor._process_function_responses(mock_event, "fix", telemetry)

        # Assert
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]["tool"], "read_file")
        self.assertEqual(telemetry[0]["result"], "SUCCESS")

    def test_process_function_responses_with_failure(self):
        """
        When response contains isError=True,
        should mark as FAILURE in telemetry.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_event = Mock()
        mock_response = Mock()
        mock_response.name = "write_file"
        mock_response.response = "Write failed, isError=True"
        mock_event.get_function_responses.return_value = [mock_response]

        telemetry = []

        # Act
        executor._process_function_responses(mock_event, "qa", telemetry)

        # Assert
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]["tool"], "write_file")
        self.assertEqual(telemetry[0]["result"], "FAILURE")

    def test_process_function_responses_without_error_flag(self):
        """
        When response has no isError flag,
        should mark as UNKNOWN in telemetry.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_event = Mock()
        mock_response = Mock()
        mock_response.name = "some_tool"
        mock_response.response = "Some response without error flag"
        mock_event.get_function_responses.return_value = [mock_response]

        telemetry = []

        # Act
        executor._process_function_responses(mock_event, "fix", telemetry)

        # Assert
        self.assertEqual(len(telemetry), 1)
        self.assertEqual(telemetry[0]["tool"], "some_tool")
        self.assertEqual(telemetry[0]["result"], "UNKNOWN")


class TestSubAgentExecutorExceptionHandling(unittest.TestCase):
    """Test exception handling"""

    def test_handle_exception_with_asyncio_error(self):
        """
        When exception is asyncio-related,
        should log at debug level and cleanup event stream without exiting.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config, \
             patch('src.smartfix.domains.agents.sub_agent_executor.error_exit') as mock_error_exit:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

            mock_event_stream = AsyncMock()
            mock_event_stream.aclose = AsyncMock()
            asyncio_error = Exception("CancelledError in cancel scope")

            # Act
            result = asyncio.run(executor._handle_exception(asyncio_error, mock_event_stream, "test-123"))

            # Assert - cleanup should be called, error_exit should NOT be called
            mock_event_stream.aclose.assert_called_once()
            mock_error_exit.assert_not_called()
            self.assertTrue(result)  # Should return True for asyncio errors

    def test_handle_exception_with_contrast_llm_access_denied(self):
        """
        When Contrast LLM access is denied,
        should log specific error message and call error_exit.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config, \
             patch('src.smartfix.domains.agents.sub_agent_executor.error_exit') as mock_error_exit:
            mock_config.return_value = Mock(
                MAX_EVENTS_PER_AGENT=120,
                USE_CONTRAST_LLM=True
            )
            # Make error_exit raise SystemExit to stop execution
            mock_error_exit.side_effect = SystemExit
            executor = SubAgentExecutor()

            mock_event_stream = AsyncMock()
            mock_event_stream.aclose = AsyncMock()
            access_error = Exception("AnthropicError: Access Denied")

            # Act & Assert - should raise SystemExit
            with self.assertRaises(SystemExit):
                asyncio.run(executor._handle_exception(access_error, mock_event_stream, "test-123"))

            # Assert - cleanup should be called and error_exit should be called
            mock_event_stream.aclose.assert_called_once()
            mock_error_exit.assert_called_once()


class TestSubAgentExecutorCleanup(unittest.TestCase):
    """Test event stream cleanup"""

    def test_cleanup_event_stream_with_valid_stream(self):
        """
        When event stream is valid,
        should call aclose to cleanup.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_stream = AsyncMock()
        mock_stream.aclose = AsyncMock()

        # Act
        asyncio.run(executor._cleanup_event_stream(mock_stream))

        # Assert
        mock_stream.aclose.assert_called_once()

    def test_cleanup_event_stream_with_none(self):
        """
        When event stream is None,
        should return early without error.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        # Act - should not raise exception
        asyncio.run(executor._cleanup_event_stream(None))

        # Assert - test passes if no exception raised

    def test_cleanup_event_stream_handles_timeout(self):
        """
        When aclose times out,
        should handle gracefully without raising.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_stream = AsyncMock()
        # Make aclose raise TimeoutError
        mock_stream.aclose.side_effect = asyncio.TimeoutError

        # Act - should not raise exception
        asyncio.run(executor._cleanup_event_stream(mock_stream, timeout=0.1))

        # Assert - test passes if no exception raised

    def test_cleanup_event_stream_handles_cancelled_error(self):
        """
        When aclose is cancelled,
        should handle gracefully without raising.
        """
        # Arrange
        with patch('src.config.get_config') as mock_config:
            mock_config.return_value = Mock(MAX_EVENTS_PER_AGENT=120)
            executor = SubAgentExecutor()

        mock_stream = AsyncMock()
        # Make aclose raise CancelledError
        mock_stream.aclose.side_effect = asyncio.CancelledError

        # Act - should not raise exception
        asyncio.run(executor._cleanup_event_stream(mock_stream, timeout=0.1))

        # Assert - test passes if no exception raised


if __name__ == '__main__':
    unittest.main()

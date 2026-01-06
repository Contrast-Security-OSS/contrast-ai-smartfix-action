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
Tests for event_loop_utils.py module.

Tests event loop management, platform-specific configuration, and
async agent execution wrapper functions.
"""

import asyncio
import sys
import unittest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Define test environment variables
TEST_ENV_VARS = {
    'GITHUB_REPOSITORY': 'mock/repo',
    'GITHUB_TOKEN': 'mock-token',
    'BASE_BRANCH': 'main',
    'CONTRAST_HOST': 'test.contrastsecurity.com',
    'CONTRAST_ORG_ID': 'test-org-id',
    'CONTRAST_APP_ID': 'test-app-id',
    'CONTRAST_AUTHORIZATION_KEY': 'test-auth-key',
    'CONTRAST_API_KEY': 'test-api-key',
    'GITHUB_WORKSPACE': '/tmp',
    'RUN_TASK': 'smartfix',
    'BUILD_COMMAND': 'echo "Test build command"',
    'REPO_ROOT': '/tmp/test_repo',
}

# Set environment variables before importing modules
os.environ.update(TEST_ENV_VARS)

# Import after environment setup
from src.smartfix.domains.agents import event_loop_utils  # noqa: E402
from src.config import reset_config, get_config  # noqa: E402


class TestEventLoopUtils(unittest.TestCase):
    """Tests for event_loop_utils module"""

    def setUp(self):
        """Set up test environment before each test"""
        reset_config()
        self.env_patcher = patch.dict(os.environ, TEST_ENV_VARS)
        self.env_patcher.start()
        self.config = get_config()

    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()
        reset_config()

    def test_run_agent_in_event_loop_success(self):
        """Test _run_agent_in_event_loop with successful async function"""
        async def simple_async_func():
            await asyncio.sleep(0.01)
            return "success"

        result = event_loop_utils._run_agent_in_event_loop(simple_async_func)
        self.assertEqual(result, "success")

    def test_run_agent_in_event_loop_with_args(self):
        """Test _run_agent_in_event_loop passes arguments correctly"""
        async def async_func_with_args(arg1, arg2, kwarg1=None):
            await asyncio.sleep(0.01)
            return f"{arg1}-{arg2}-{kwarg1}"

        result = event_loop_utils._run_agent_in_event_loop(
            async_func_with_args, "a", "b", kwarg1="c"
        )
        self.assertEqual(result, "a-b-c")

    def test_run_agent_in_event_loop_exception_handling(self):
        """Test _run_agent_in_event_loop handles exceptions and cleans up"""
        async def failing_async_func():
            await asyncio.sleep(0.01)
            raise RuntimeError("Test error")

        with self.assertRaises(RuntimeError) as context:
            event_loop_utils._run_agent_in_event_loop(failing_async_func)
        self.assertEqual(str(context.exception), "Test error")

    @patch('src.smartfix.domains.agents.event_loop_utils.platform.system')
    @patch('src.smartfix.domains.agents.event_loop_utils.asyncio.set_event_loop_policy')
    def test_run_agent_in_event_loop_windows_platform(self, mock_set_policy, mock_platform):
        """Test _run_agent_in_event_loop with Windows platform"""
        mock_platform.return_value = 'Windows'

        async def simple_async_func():
            return "windows_success"

        # Mock WindowsProactorEventLoopPolicy - patch at asyncio level
        mock_policy_class = MagicMock()
        with patch('asyncio.WindowsProactorEventLoopPolicy', mock_policy_class, create=True):
            result = event_loop_utils._run_agent_in_event_loop(simple_async_func)
            self.assertEqual(result, "windows_success")

    @patch('src.smartfix.domains.agents.event_loop_utils.platform.system')
    def test_run_agent_in_event_loop_unix_platform(self, mock_platform):
        """Test _run_agent_in_event_loop with Unix platform"""
        mock_platform.return_value = 'Linux'

        async def simple_async_func():
            return "unix_success"

        result = event_loop_utils._run_agent_in_event_loop(simple_async_func)
        self.assertEqual(result, "unix_success")

    def test_run_agent_in_event_loop_task_cancellation(self):
        """Test _run_agent_in_event_loop cancels tasks on exception"""
        async def async_func_with_pending_task():
            # Create a pending task that won't complete
            async def never_complete():
                await asyncio.sleep(100)

            task = asyncio.create_task(never_complete())
            raise RuntimeError("Intentional error")

        with self.assertRaises(RuntimeError):
            event_loop_utils._run_agent_in_event_loop(async_func_with_pending_task)

    @patch('src.smartfix.domains.agents.event_loop_utils.ADK_AVAILABLE', False)
    @patch('src.smartfix.domains.agents.event_loop_utils.error_exit')
    def test_run_agent_internal_adk_not_available(self, mock_error_exit):
        """Test _run_agent_internal_with_prompts when ADK not available"""
        # Mock error_exit to raise exception to stop execution
        mock_error_exit.side_effect = SystemExit(1)

        # Use asyncio.run to execute the async function - should exit early
        with self.assertRaises(SystemExit):
            asyncio.run(event_loop_utils._run_agent_internal_with_prompts(
                agent_type="fix",
                repo_root=Path("/tmp/repo"),
                query="Test query",
                system_prompt="Test prompt",
                remediation_id="REM-123"
            ))

        # Verify error_exit was called with correct args
        mock_error_exit.assert_called_once()
        call_args = mock_error_exit.call_args
        self.assertEqual(call_args[0][0], "REM-123")

    @patch('src.smartfix.domains.agents.event_loop_utils.ADK_AVAILABLE', True)
    @patch('src.smartfix.domains.agents.event_loop_utils.InMemorySessionService')
    @patch('src.smartfix.domains.agents.event_loop_utils.error_exit')
    def test_run_agent_internal_session_creation_error(self, mock_error_exit, mock_session_service):
        """Test _run_agent_internal_with_prompts with session creation error"""
        # Mock error_exit to raise exception to stop execution
        mock_error_exit.side_effect = SystemExit(1)

        # Mock session service to raise exception
        mock_service_instance = MagicMock()
        mock_service_instance.create_session = AsyncMock(side_effect=Exception("Session error"))
        mock_session_service.return_value = mock_service_instance

        with self.assertRaises(SystemExit):
            asyncio.run(event_loop_utils._run_agent_internal_with_prompts(
                agent_type="fix",
                repo_root=Path("/tmp/repo"),
                query="Test query",
                system_prompt="Test prompt",
                remediation_id="REM-456"
            ))

        # Verify error_exit was called
        mock_error_exit.assert_called_once()
        call_args = mock_error_exit.call_args
        self.assertEqual(call_args[0][0], "REM-456")

    @patch('src.smartfix.domains.agents.event_loop_utils.ADK_AVAILABLE', True)
    @patch('src.smartfix.domains.agents.event_loop_utils.InMemorySessionService')
    @patch('src.smartfix.domains.agents.event_loop_utils.InMemoryArtifactService')
    @patch('src.smartfix.domains.agents.event_loop_utils.SubAgentExecutor')
    @patch('src.smartfix.domains.agents.event_loop_utils.error_exit')
    def test_run_agent_internal_agent_creation_failure(
        self, mock_error_exit, mock_executor_class, mock_artifact_service, mock_session_service
    ):
        """Test _run_agent_internal_with_prompts when agent creation fails"""
        # Mock error_exit to raise exception to stop execution
        mock_error_exit.side_effect = SystemExit(1)

        # Mock services
        mock_service_instance = MagicMock()
        mock_service_instance.create_session = AsyncMock(return_value=MagicMock())
        mock_session_service.return_value = mock_service_instance

        # Mock executor to return None (agent creation failure)
        mock_executor = MagicMock()
        mock_executor.create_agent = AsyncMock(return_value=None)
        mock_executor_class.return_value = mock_executor

        with self.assertRaises(SystemExit):
            asyncio.run(event_loop_utils._run_agent_internal_with_prompts(
                agent_type="qa",
                repo_root=Path("/tmp/repo"),
                query="Test query",
                system_prompt="Test prompt",
                remediation_id="REM-789"
            ))

        # Verify error_exit was called
        mock_error_exit.assert_called_once()
        call_args = mock_error_exit.call_args
        self.assertEqual(call_args[0][0], "REM-789")

    @patch('src.smartfix.domains.agents.event_loop_utils.ADK_AVAILABLE', True)
    @patch('src.smartfix.domains.agents.event_loop_utils.InMemorySessionService')
    @patch('src.smartfix.domains.agents.event_loop_utils.InMemoryArtifactService')
    @patch('src.smartfix.domains.agents.event_loop_utils.SubAgentExecutor')
    @patch('src.smartfix.domains.agents.event_loop_utils.Runner')
    def test_run_agent_internal_success(
        self, mock_runner_class, mock_executor_class, mock_artifact_service, mock_session_service
    ):
        """Test _run_agent_internal_with_prompts with successful execution"""
        # Mock services
        mock_session = MagicMock()
        mock_service_instance = MagicMock()
        mock_service_instance.create_session = AsyncMock(return_value=mock_session)
        mock_session_service.return_value = mock_service_instance

        # Mock executor
        mock_agent = MagicMock()
        mock_executor = MagicMock()
        mock_executor.create_agent = AsyncMock(return_value=mock_agent)
        mock_executor.execute_agent = AsyncMock(return_value="Fix applied successfully")
        mock_executor_class.return_value = mock_executor

        result = asyncio.run(event_loop_utils._run_agent_internal_with_prompts(
            agent_type="fix",
            repo_root=Path("/tmp/repo"),
            query="Fix SQL injection",
            system_prompt="You are a security fix agent",
            remediation_id="REM-999",
            session_id="SESSION-123"
        ))

        self.assertEqual(result, "Fix applied successfully")
        mock_executor.create_agent.assert_called_once()
        mock_executor.execute_agent.assert_called_once()

    @patch('src.smartfix.domains.agents.event_loop_utils.platform.system')
    @patch('src.smartfix.domains.agents.event_loop_utils.ADK_AVAILABLE', True)
    @patch('src.smartfix.domains.agents.event_loop_utils.InMemorySessionService')
    @patch('src.smartfix.domains.agents.event_loop_utils.InMemoryArtifactService')
    @patch('src.smartfix.domains.agents.event_loop_utils.SubAgentExecutor')
    @patch('src.smartfix.domains.agents.event_loop_utils.Runner')
    @patch('src.smartfix.domains.agents.event_loop_utils.asyncio.set_event_loop_policy')
    def test_run_agent_internal_windows_platform_handling(
        self, mock_set_policy, mock_runner_class, mock_executor_class, mock_artifact_service,
        mock_session_service, mock_platform
    ):
        """Test _run_agent_internal_with_prompts with Windows platform"""
        mock_platform.return_value = 'Windows'

        # Mock services
        mock_session = MagicMock()
        mock_service_instance = MagicMock()
        mock_service_instance.create_session = AsyncMock(return_value=mock_session)
        mock_session_service.return_value = mock_service_instance

        # Mock executor
        mock_agent = MagicMock()
        mock_executor = MagicMock()
        mock_executor.create_agent = AsyncMock(return_value=mock_agent)
        mock_executor.execute_agent = AsyncMock(return_value="Windows fix success")
        mock_executor_class.return_value = mock_executor

        # Mock WindowsProactorEventLoopPolicy at asyncio level
        mock_policy = MagicMock()
        with patch('asyncio.WindowsProactorEventLoopPolicy', mock_policy, create=True):
            result = asyncio.run(event_loop_utils._run_agent_internal_with_prompts(
                agent_type="qa",
                repo_root=Path("/tmp/repo"),
                query="Verify fix",
                system_prompt="You are a QA agent",
                remediation_id="REM-WIN",
                session_id="SESSION-WIN"
            ))

            self.assertEqual(result, "Windows fix success")


if __name__ == '__main__':
    unittest.main()

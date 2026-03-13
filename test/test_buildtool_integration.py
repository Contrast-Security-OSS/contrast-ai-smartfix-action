"""
Integration tests for BuildTool + SmartFixAgent + PR Gate.

Tests the end-to-end flow:
- BuildTool records successful commands → PR gate passes
- BuildTool records no success → PR gate fails
- Cross-run persistence via BuildConfiguration
- Configured vs detected command source handling
- Non-recordable commands don't satisfy PR gate
"""

import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from src.smartfix.domains.agents.build_tool import (
    create_build_tool,
    get_successful_build_command,
    get_successful_format_command,
    reset_storage,
)
from src.smartfix.domains.agents.smartfix_agent import SmartFixAgent
from src.smartfix.domains.vulnerability.context import BuildConfiguration
from src.smartfix.shared.failure_categories import FailureCategory


class TestBuildToolPRGateIntegration(unittest.TestCase):
    """Test BuildTool recording → PR gate pass/fail flow."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    @patch('subprocess.run')
    def test_successful_build_records_command_and_pr_gate_passes(self, mock_subprocess):
        """Full flow: BuildTool records success → PR gate passes."""
        mock_subprocess.return_value = Mock(returncode=0, stdout="BUILD SUCCESS", stderr="")

        tool = create_build_tool(
            repo_root=Path("/tmp/test"),
            remediation_id="int-001",
            user_build_command="mvn test",
        )

        result = tool(build_command="mvn test")

        self.assertTrue(result["success"])
        self.assertTrue(result["recorded"])
        self.assertEqual(get_successful_build_command(), "mvn test")

        # PR gate should pass
        agent = SmartFixAgent()
        session = Mock()
        context = Mock()
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = True
        context.build_config.user_build_command = "mvn test"

        gate_result = agent._check_pr_gate(session, context)
        self.assertTrue(gate_result)

    def test_no_build_recorded_pr_gate_fails(self):
        """No successful build recorded → PR gate fails with BUILD_VERIFICATION_FAILED."""
        agent = SmartFixAgent()
        session = Mock()
        session.complete_session = Mock()
        context = Mock()
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = True

        gate_result = agent._check_pr_gate(session, context)

        self.assertFalse(gate_result)
        session.complete_session.assert_called_once()
        call_kwargs = session.complete_session.call_args[1]
        self.assertEqual(call_kwargs["failure_category"], FailureCategory.BUILD_VERIFICATION_FAILED)

    def test_no_build_config_pr_gate_skipped(self):
        """No build command configured → PR gate skipped (passes)."""
        agent = SmartFixAgent()
        session = Mock()
        context = Mock()
        context.build_config = None

        gate_result = agent._check_pr_gate(session, context)
        self.assertTrue(gate_result)

    def test_empty_build_command_pr_gate_skipped(self):
        """Build config exists but has_build_command is False → gate skipped."""
        agent = SmartFixAgent()
        session = Mock()
        context = Mock()
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = False

        gate_result = agent._check_pr_gate(session, context)
        self.assertTrue(gate_result)

    @patch('subprocess.run')
    def test_non_recordable_command_does_not_satisfy_gate(self, mock_subprocess):
        """Non-recordable commands (--version, echo) don't satisfy PR gate."""
        mock_subprocess.return_value = Mock(returncode=0, stdout="Maven 3.8.1", stderr="")

        tool = create_build_tool(
            repo_root=Path("/tmp/test"),
            remediation_id="int-002",
        )

        result = tool(build_command="mvn --version")

        self.assertTrue(result["success"])
        self.assertFalse(result["recorded"])
        self.assertIsNone(get_successful_build_command())

        # PR gate should fail since nothing was recorded
        agent = SmartFixAgent()
        session = Mock()
        session.complete_session = Mock()
        context = Mock()
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = True

        gate_result = agent._check_pr_gate(session, context)
        self.assertFalse(gate_result)


class TestBuildCommandEnforcement(unittest.TestCase):
    """Test that scoped/modified commands don't satisfy the PR gate when a configured command exists."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    @patch('subprocess.run')
    def test_scoped_command_not_recorded_when_configured_exists(self, mock_subprocess):
        """Agent runs scoped command (e.g. mvn test -Dtest=Foo) but configured is 'mvn test' → not recorded."""
        mock_subprocess.return_value = Mock(returncode=0, stdout="BUILD SUCCESS", stderr="")

        tool = create_build_tool(
            repo_root=Path("/tmp/test"),
            remediation_id="enf-001",
            user_build_command="mvn test",
        )

        # Agent runs a scoped variant instead of the exact configured command
        result = tool(build_command="mvn test -Dtest=SqlInjectionTest")

        self.assertTrue(result["success"])
        self.assertFalse(result["recorded"])
        self.assertIsNone(get_successful_build_command())

    @patch('subprocess.run')
    def test_exact_configured_command_is_recorded(self, mock_subprocess):
        """Agent runs exact configured command → recorded."""
        mock_subprocess.return_value = Mock(returncode=0, stdout="BUILD SUCCESS", stderr="")

        tool = create_build_tool(
            repo_root=Path("/tmp/test"),
            remediation_id="enf-002",
            user_build_command="mvn test",
        )

        result = tool(build_command="mvn test")

        self.assertTrue(result["success"])
        self.assertTrue(result["recorded"])
        self.assertEqual(get_successful_build_command(), "mvn test")

    @patch('subprocess.run')
    def test_pr_gate_rejects_mismatched_recorded_command(self, mock_subprocess):
        """PR gate fails if recorded command doesn't match configured command."""
        mock_subprocess.return_value = Mock(returncode=0, stdout="BUILD SUCCESS", stderr="")

        # Simulate: no user_build_command so any recordable command gets recorded
        tool = create_build_tool(
            repo_root=Path("/tmp/test"),
            remediation_id="enf-003",
        )
        tool(build_command="mvn test -Dtest=Foo")

        # Now check PR gate with a configured command that doesn't match
        agent = SmartFixAgent()
        session = Mock()
        session.complete_session = Mock()
        context = Mock()
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = True
        context.build_config.user_build_command = "mvn test"

        gate_result = agent._check_pr_gate(session, context)
        self.assertFalse(gate_result)
        session.complete_session.assert_called_once()
        call_kwargs = session.complete_session.call_args[1]
        self.assertEqual(call_kwargs["failure_category"], FailureCategory.BUILD_VERIFICATION_FAILED)


class TestBuildToolConfiguredVsDetermined(unittest.TestCase):
    """Test configured (user) vs determined (detected/agent-discovered) mode."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    @patch('subprocess.run')
    def test_configured_command_skips_allowlist(self, mock_subprocess):
        """User-configured command skips allowlist validation."""
        mock_subprocess.return_value = Mock(returncode=0, stdout="OK", stderr="")

        tool = create_build_tool(
            repo_root=Path("/tmp/test"),
            remediation_id="int-003",
            user_build_command="custom-internal-tool build",
        )

        # This command wouldn't pass allowlist, but user_build_command exact match skips it
        result = tool(build_command="custom-internal-tool build")

        self.assertTrue(result["success"])
        self.assertTrue(result["recorded"])
        self.assertEqual(get_successful_build_command(), "custom-internal-tool build")

    @patch('subprocess.run')
    def test_agent_discovered_command_must_pass_allowlist(self, mock_subprocess):
        """Agent-discovered command must pass allowlist validation."""
        mock_subprocess.return_value = Mock(returncode=0, stdout="OK", stderr="")

        tool = create_build_tool(
            repo_root=Path("/tmp/test"),
            remediation_id="int-004",
            # No user_build_command → agent-discovered mode
        )

        # rm -rf would fail allowlist
        result = tool(build_command="rm -rf /")

        self.assertFalse(result["success"])
        self.assertIn("not allowed", result["output"].lower())

    @patch('src.smartfix.domains.agents.build_tool.run_formatting_command')
    @patch('subprocess.run')
    def test_configured_format_command_skips_allowlist(self, mock_subprocess, mock_format):
        """User-configured format command skips allowlist validation."""
        mock_subprocess.return_value = Mock(returncode=0, stdout="Formatted", stderr="")

        tool = create_build_tool(
            repo_root=Path("/tmp/test"),
            remediation_id="int-005",
            user_build_command="mvn test",
            user_format_command="custom-formatter --fix",
        )

        result = tool(build_command="mvn test", format_command="custom-formatter --fix")

        self.assertTrue(result["success"])
        self.assertEqual(get_successful_format_command(), "custom-formatter --fix")


class TestCrossRunPersistence(unittest.TestCase):
    """Test that BuildConfiguration carries forward proven commands between runs."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    def test_build_config_from_config_user_configured(self):
        """User-configured commands populate user_build_command for exact-match."""
        config = Mock()
        config.BUILD_COMMAND = "mvn test"
        config.FORMATTING_COMMAND = "mvn spotless:apply"
        config._build_command_source = "config"
        config._format_command_source = "config"

        build_config = BuildConfiguration.from_config(config)

        self.assertEqual(build_config.build_command, "mvn test")
        self.assertEqual(build_config.build_command_source, "user_configured")
        self.assertEqual(build_config.user_build_command, "mvn test")
        self.assertEqual(build_config.user_format_command, "mvn spotless:apply")

    def test_build_config_from_config_phase1_detected(self):
        """Phase1-detected commands don't set user_build_command (use allowlist)."""
        config = Mock()
        config.BUILD_COMMAND = "npm test"
        config.FORMATTING_COMMAND = None
        config._build_command_source = "ai_detected"
        config._format_command_source = "config"

        build_config = BuildConfiguration.from_config(config)

        self.assertEqual(build_config.build_command, "npm test")
        self.assertEqual(build_config.build_command_source, "phase1_detected")
        self.assertIsNone(build_config.user_build_command)

    @patch('subprocess.run')
    def test_cross_run_build_config_passes_user_command_to_tool(self, mock_subprocess):
        """BuildConfiguration.user_build_command flows through to BuildTool for exact-match."""
        mock_subprocess.return_value = Mock(returncode=0, stdout="OK", stderr="")

        config = Mock()
        config.BUILD_COMMAND = "custom-tool verify"
        config.FORMATTING_COMMAND = None
        config._build_command_source = "config"
        config._format_command_source = "config"

        build_config = BuildConfiguration.from_config(config)

        # Create BuildTool with the user_build_command from config
        tool = create_build_tool(
            repo_root=Path("/tmp/test"),
            remediation_id="cross-001",
            user_build_command=build_config.user_build_command,
            user_format_command=build_config.user_format_command,
        )

        # Agent uses the same command (exact match → skips allowlist)
        result = tool(build_command="custom-tool verify")

        self.assertTrue(result["success"])
        self.assertTrue(result["recorded"])

    def test_storage_resets_between_remediations(self):
        """reset_storage clears state between vulnerability remediations."""
        # Simulate a previous run's success
        from src.smartfix.domains.agents import build_tool
        build_tool._successful_build_command = "mvn test"
        build_tool._successful_format_command = "mvn spotless:apply"

        self.assertEqual(get_successful_build_command(), "mvn test")

        # Reset for new remediation
        reset_storage()

        self.assertIsNone(get_successful_build_command())
        self.assertIsNone(get_successful_format_command())


class TestSmartFixAgentRemediation(unittest.TestCase):
    """Test full remediation flow through SmartFixAgent."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    @patch('src.smartfix.domains.agents.smartfix_agent.get_successful_build_command')
    def test_remediate_resets_storage_at_start(self, mock_get_cmd):
        """remediate() calls reset_storage at the beginning."""
        from src.smartfix.domains.agents import build_tool
        build_tool._successful_build_command = "leftover"

        mock_get_cmd.return_value = None

        agent = SmartFixAgent()
        context = Mock()
        context.build_config = None
        context.prompts = Mock()
        context.repo_config = Mock()

        with patch.object(agent, '_run_ai_fix_agent', return_value="<pr_body>Fixed</pr_body>"):
            agent.remediate(context)

        # After remediate starts, storage should have been reset
        # (mock_get_cmd returns None because we're checking the PR gate)
        self.assertIsNone(build_tool._successful_build_command)

    @patch('src.smartfix.domains.agents.smartfix_agent._run_agent_in_event_loop')
    def test_remediate_passes_build_tool_to_agent(self, mock_event_loop):
        """remediate() creates BuildTool and passes it as additional_tools."""
        mock_event_loop.return_value = "<pr_body>Fix applied</pr_body>"

        agent = SmartFixAgent()
        context = Mock()
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = False
        context.build_config.user_build_command = "mvn test"
        context.build_config.user_format_command = None
        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")
        context.prompts = Mock()
        context.prompts.fix_system_prompt = "Fix"
        context.prompts.fix_user_prompt = "Fix"
        context.remediation_id = "int-010"
        context.session_id = "sess-010"
        context.skip_writing_security_test = False

        with patch.object(agent, '_extract_analytics_data'):
            agent.remediate(context)

        # Verify additional_tools was passed
        mock_event_loop.assert_called_once()
        call_kwargs = mock_event_loop.call_args
        self.assertIn('additional_tools', call_kwargs.kwargs)
        additional_tools = call_kwargs.kwargs['additional_tools']
        self.assertEqual(len(additional_tools), 1)
        self.assertTrue(callable(additional_tools[0]))


if __name__ == '__main__':
    unittest.main()

import sys
import unittest
import os
import io
import contextlib
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure test directory is on path (conftest.py only runs under pytest)
sys.path.insert(0, str(Path(__file__).parent))
from setup_test_env import create_temp_repo_dir  # noqa: E402
from src.config import reset_config, get_config  # noqa: E402
from src.main import main  # noqa: E402
from src.smartfix.shared.failure_categories import FailureCategory  # noqa: E402


class TestMain(unittest.TestCase):
    """Test the main functionality of the application."""

    def setUp(self):
        """Set up test environment before each test."""
        # Use helper for temp directory creation
        self.temp_dir = str(create_temp_repo_dir())

        # Setup standard env vars, then override paths for this test
        # Override paths specific to this test
        import os
        self.env_vars = {
            'HOME': self.temp_dir,
            'GITHUB_WORKSPACE': self.temp_dir,
            'BUILD_COMMAND': 'echo "Mock build"',
            'FORMATTING_COMMAND': 'echo "Mock format"',
            'GITHUB_TOKEN': 'mock-token',
            'GITHUB_REPOSITORY': 'mock/repo',
            'GITHUB_SERVER_URL': 'https://mockhub.com',
            'CONTRAST_HOST': 'mock.contrastsecurity.com',  # No https:// prefix
            'CONTRAST_ORG_ID': 'mock-org',
            'CONTRAST_APP_ID': 'mock-app',
            'CONTRAST_AUTHORIZATION_KEY': 'mock-auth',
            'CONTRAST_API_KEY': 'mock-api',
            'BASE_BRANCH': 'main',
            'DEBUG_MODE': 'true',
            'RUN_TASK': 'generate_fix'
        }

        # Apply additional environment variables to what the mixin already set up
        os.environ.update(self.env_vars)

        # Reset config for clean test state
        reset_config()

        # Mock subprocess calls
        self.subproc_patcher = patch('subprocess.run')
        self.mock_subprocess = self.subproc_patcher.start()
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "Mock output"
        mock_process.communicate.return_value = (b"Mock stdout", b"Mock stderr")
        self.mock_subprocess.return_value = mock_process

        # Mock git configuration
        self.git_patcher = patch('src.smartfix.domains.scm.git_operations.GitOperations.configure_git_user')
        self.mock_git = self.git_patcher.start()

        # Mock API calls
        self.api_patcher = patch('src.contrast_api.get_org_prompt_details')
        self.mock_api = self.api_patcher.start()
        self.mock_api.return_value = None

        # Mock reconciliation to avoid real API calls
        self.reconcile_patcher = patch('src.main.reconcile_open_remediations')
        self.mock_reconcile = self.reconcile_patcher.start()

        # Mock requests for version checking
        self.requests_patcher = patch('src.version_check.requests.get')
        self.mock_requests_get = self.requests_patcher.start()
        mock_response = MagicMock()
        mock_response.json.return_value = [{'name': 'v1.0.0'}]
        mock_response.raise_for_status.return_value = None
        self.mock_requests_get.return_value = mock_response

        # Mock sys.exit to prevent test termination
        self.exit_patcher = patch('sys.exit')
        self.mock_exit = self.exit_patcher.start()

        # Mock count_open_prs_with_prefix to avoid JSON parse failure from mocked subprocess
        self.pr_count_patcher = patch(
            'src.github.github_operations.GitHubOperations.count_open_prs_with_prefix',
            return_value=0
        )
        self.mock_pr_count = self.pr_count_patcher.start()

        # Mock notify_remediation_failed_org to prevent real HTTP calls in error paths
        self.notify_patcher = patch('src.contrast_api.notify_remediation_failed_org', return_value=False)
        self.mock_notify = self.notify_patcher.start()

    def tearDown(self):
        """Clean up after each test."""
        # Stop all patches
        self.subproc_patcher.stop()
        self.git_patcher.stop()
        self.api_patcher.stop()
        self.reconcile_patcher.stop()
        self.requests_patcher.stop()
        self.exit_patcher.stop()
        self.pr_count_patcher.stop()
        self.notify_patcher.stop()
        reset_config()

        # Clean up temp directory
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_main_with_version_check(self):
        """Test main function with version check."""
        # Add version ref to environment
        updated_env = self.env_vars.copy()
        updated_env['GITHUB_ACTION_REF'] = 'refs/tags/v1.0.0'

        # Create a proper patch for the function as imported in main.py
        # Note: main.py imports from version_check directly, not src.version_check
        with patch('src.version_check.get_latest_repo_version') as mock_get_latest:
            # Setup version check mocks
            mock_get_latest.return_value = "v1.0.0"

            with patch.dict('os.environ', updated_env, clear=True):
                # Run main and capture output
                with io.StringIO() as buf, contextlib.redirect_stdout(buf):
                    main()
                    output = buf.getvalue()

                # Verify main function and version check ran
                self.assertIn("--- Starting Contrast AI SmartFix Script ---", output)
                self.assertIn("Current action version", output)
                mock_get_latest.assert_called_once()

    def test_main_without_action_ref(self):
        """Test main function without GITHUB_ACTION_REF."""
        # Ensure no GITHUB_ACTION_REF is set
        test_env = self.env_vars.copy()
        if 'GITHUB_ACTION_REF' in test_env:
            del test_env['GITHUB_ACTION_REF']
        if 'GITHUB_REF' in test_env:
            del test_env['GITHUB_REF']

        with patch.dict('os.environ', test_env, clear=True):
            # Run main and capture output
            with io.StringIO() as buf, contextlib.redirect_stdout(buf):
                main()
                output = buf.getvalue()

        # Verify warning about missing environment variables is present (updated for new message format)
        self.assertIn("Warning: Neither GITHUB_ACTION_REF nor GITHUB_REF environment variables are set", output)

    def test_duplicate_vuln_with_open_pr_skips_cleanly(self):
        """Test that duplicate vulnerability UUID with open PR skips cleanly without error_exit.

        Regression test for AIML-241: When the API returns the same vulnerability twice
        (common when a PR is already open), the code should skip it cleanly using the
        skipped_vulns logic rather than triggering the duplicate guard error.
        """
        # Setup: Mock API to return same vulnerability twice, then None
        vuln_data = {
            'vulnerabilityUuid': 'TEST-VULN-UUID-123',
            'vulnerabilityTitle': 'Test SQL Injection',
            'vulnerabilityRuleName': 'sql-injection',
            'remediationId': 'REM-TEST-123',
            'sessionId': 'session-123',
            'fixSystemPrompt': 'Fix the vulnerability',
            'fixUserPrompt': 'Please fix'
        }

        # Return same vuln twice, then None to stop loop
        self.mock_api.side_effect = [vuln_data, vuln_data, None]

        # Mock PR status check to return OPEN (simulating existing PR)
        with patch('src.github.github_operations.GitHubOperations.check_pr_status_for_label') as mock_pr_check:
            mock_pr_check.return_value = "OPEN"

            # Mock generate_label_details
            with patch('src.github.github_operations.GitHubOperations.generate_label_details') as mock_label:
                mock_label.return_value = ('contrast-vuln-id:TEST-VULN-UUID-123', 'color', 'desc')

                with patch.dict('os.environ', self.env_vars, clear=True):
                    # Run main and capture output
                    with io.StringIO() as buf, contextlib.redirect_stdout(buf):
                        main()
                        output = buf.getvalue()

                    # Verify the vulnerability was skipped both times
                    self.assertIn("Skipping vulnerability TEST-VULN-UUID-123", output)
                    self.assertIn("TEST-VULN-UUID-123 was re-suggested after being skipped", output)

                    # Verify the loop broke cleanly
                    self.assertIn("No vulnerabilities were processed in this run", output)

    def test_no_changes_detected_notifies_backend_as_no_code_changed(self):
        """Regression test: when agent makes no code changes, backend must be notified.

        Previously the action called continue without notifying the backend, causing
        the backend to re-serve the same vuln on the next iteration, which then
        triggered the duplicate-UUID guard and exited with GENERAL_FAILURE.
        """
        vuln_data = {
            'vulnerabilityUuid': 'TEST-VULN-UUID-456',
            'vulnerabilityTitle': 'Test Container Vulnerability',
            'vulnerabilityRuleName': 'weak-hash',
            'vulnerabilitySeverity': 'HIGH',
            'remediationId': 'REM-TEST-456',
            'sessionId': 'session-456',
            'fixSystemPrompt': 'Fix the vulnerability',
            'fixUserPrompt': 'Please fix',
        }
        # Return one vuln, then None to stop the loop
        self.mock_api.side_effect = [vuln_data, None]

        # Disable Contrast LLM to skip the credit tracking check (which would call
        # notify_remediation_failed before we reach the no-changes branch).
        # Set AGENT_MODEL to a non-Bedrock model so _validate_aws_bedrock_config skips its
        # AWS credentials check (which would fail with no AWS creds in test env).
        test_env = {**self.env_vars, 'USE_CONTRAST_LLM': 'false', 'AGENT_MODEL': 'mock-model'}

        from src.smartfix.domains.workflow.session_handler import SessionOutcome
        mock_session_result = SessionOutcome(
            should_continue=True,
            failure_category=None,
            ai_fix_summary="No code changes needed - container-level issue",
        )

        with patch('src.github.github_operations.GitHubOperations.count_open_prs_with_prefix', return_value=0), \
             patch('src.github.github_operations.GitHubOperations.check_pr_status_for_label', return_value="NOT_FOUND"), \
             patch('src.github.github_operations.GitHubOperations.generate_label_details',
                   return_value=('contrast-vuln-id:TEST-VULN-UUID-456', 'desc', 'color')), \
             patch('src.smartfix.domains.scm.git_operations.GitOperations.prepare_feature_branch'), \
             patch('src.smartfix.domains.scm.git_operations.GitOperations.stage_changes'), \
             patch('src.smartfix.domains.scm.git_operations.GitOperations.check_status', return_value=False), \
             patch('src.smartfix.domains.scm.git_operations.GitOperations.cleanup_branch') as mock_cleanup, \
             patch('src.main.SmartFixAgent') as mock_agent_class, \
             patch('src.main.handle_session_result', return_value=mock_session_result), \
             patch('src.main.generate_qa_section', return_value=""), \
             patch('src.contrast_api.notify_remediation_failed_org') as mock_notify_failed:

            mock_agent = MagicMock()
            mock_agent_class.return_value = mock_agent

            with patch.dict('os.environ', test_env, clear=True):
                reset_config()
                with patch('src.main.config', get_config()):
                    with io.StringIO() as buf, contextlib.redirect_stdout(buf):
                        main()
                        output = buf.getvalue()

        mock_notify_failed.assert_called_once()
        call_kwargs = mock_notify_failed.call_args[1]
        self.assertEqual(call_kwargs['failure_category'], FailureCategory.NO_CODE_CHANGED.value)
        self.assertEqual(call_kwargs['remediation_id'], 'REM-TEST-456')
        mock_cleanup.assert_called_once_with("smartfix/remediation-REM-TEST-456")
        self.assertIn("No changes detected from agent execution", output)

    def test_fix_vulnerability_span_created_with_request_attributes(self):
        """fix-vulnerability span is opened for each processed vulnerability with correct request attributes."""
        vuln_data = {
            'vulnerabilityUuid': 'SPAN-UUID-001',
            'vulnerabilityTitle': 'Test SQL Injection',
            'vulnerabilityRuleName': 'sql-injection',
            'vulnerabilitySeverity': 'HIGH',
            'remediationId': 'REM-SPAN-001',
            'sessionId': 'session-span-001',
            'fixSystemPrompt': 'Fix the vulnerability',
            'fixUserPrompt': 'Please fix',
        }
        self.mock_api.side_effect = [vuln_data, None]

        # Disable Contrast LLM; use non-Bedrock model to skip AWS validation.
        test_env = {**self.env_vars, 'USE_CONTRAST_LLM': 'false', 'AGENT_MODEL': 'mock-model'}

        from src.smartfix.domains.workflow.session_handler import SessionOutcome
        mock_session_result = SessionOutcome(
            should_continue=False,
            failure_category=FailureCategory.AGENT_FAILURE.value,
            ai_fix_summary="Agent failed",
        )

        # Track span calls keyed by span name
        span_registry = {}

        def mock_start_span(name):
            mock_span = MagicMock()
            mock_span_cm = MagicMock()
            mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
            mock_span_cm.__exit__ = MagicMock(return_value=False)
            span_registry[name] = mock_span
            return mock_span_cm

        with patch('src.github.github_operations.GitHubOperations.count_open_prs_with_prefix', return_value=0), \
             patch('src.github.github_operations.GitHubOperations.check_pr_status_for_label', return_value="NOT_FOUND"), \
             patch('src.github.github_operations.GitHubOperations.generate_label_details',
                   return_value=('contrast-vuln-id:SPAN-UUID-001', 'desc', 'color')), \
             patch('src.smartfix.domains.scm.git_operations.GitOperations.prepare_feature_branch'), \
             patch('src.smartfix.domains.scm.git_operations.GitOperations.cleanup_branch'), \
             patch('src.main.SmartFixAgent') as mock_agent_class, \
             patch('src.main.handle_session_result', return_value=mock_session_result), \
             patch('src.smartfix.domains.telemetry.otel_provider.start_span', side_effect=mock_start_span), \
             patch('src.smartfix.domains.telemetry.otel_provider.initialize_otel'), \
             patch('src.smartfix.domains.telemetry.otel_provider.shutdown_otel'):

            mock_agent_class.return_value = MagicMock()

            with patch.dict('os.environ', test_env, clear=True):
                reset_config()
                with patch('src.main.config', get_config(testing=True)):
                    main()

        # Verify the operation span was started
        self.assertIn("fix-vulnerability", span_registry,
                      "Expected start_span('fix-vulnerability') to be called")

        op_span = span_registry["fix-vulnerability"]
        attrs = {call[0][0]: call[0][1] for call in op_span.set_attribute.call_args_list}

        self.assertEqual(attrs.get("contrast.finding.fingerprint"), "SPAN-UUID-001")
        self.assertEqual(attrs.get("contrast.finding.source"), "runtime")
        self.assertEqual(attrs.get("contrast.finding.rule_id"), "sql-injection")
        self.assertEqual(attrs.get("contrast.smartfix.coding_agent"), "smartfix")

    def test_fix_vulnerability_span_response_attributes_no_changes(self):
        """fix-vulnerability span has fix_applied=False and pr_created=False when no code changes."""
        vuln_data = {
            'vulnerabilityUuid': 'SPAN-UUID-002',
            'vulnerabilityTitle': 'Test Weak Hash',
            'vulnerabilityRuleName': 'weak-hash',
            'vulnerabilitySeverity': 'HIGH',
            'remediationId': 'REM-SPAN-002',
            'sessionId': 'session-span-002',
            'fixSystemPrompt': 'Fix the vulnerability',
            'fixUserPrompt': 'Please fix',
        }
        self.mock_api.side_effect = [vuln_data, None]

        test_env = {**self.env_vars, 'USE_CONTRAST_LLM': 'false', 'AGENT_MODEL': 'mock-model'}

        from src.smartfix.domains.workflow.session_handler import SessionOutcome
        mock_session_result = SessionOutcome(
            should_continue=True,
            failure_category=None,
            ai_fix_summary="No code changes needed",
        )

        span_registry = {}

        def mock_start_span(name):
            mock_span = MagicMock()
            mock_span_cm = MagicMock()
            mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
            mock_span_cm.__exit__ = MagicMock(return_value=False)
            span_registry[name] = mock_span
            return mock_span_cm

        with patch('src.github.github_operations.GitHubOperations.count_open_prs_with_prefix', return_value=0), \
             patch('src.github.github_operations.GitHubOperations.check_pr_status_for_label', return_value="NOT_FOUND"), \
             patch('src.github.github_operations.GitHubOperations.generate_label_details',
                   return_value=('contrast-vuln-id:SPAN-UUID-002', 'desc', 'color')), \
             patch('src.smartfix.domains.scm.git_operations.GitOperations.prepare_feature_branch'), \
             patch('src.smartfix.domains.scm.git_operations.GitOperations.stage_changes'), \
             patch('src.smartfix.domains.scm.git_operations.GitOperations.check_status', return_value=False), \
             patch('src.smartfix.domains.scm.git_operations.GitOperations.cleanup_branch'), \
             patch('src.main.SmartFixAgent') as mock_agent_class, \
             patch('src.main.handle_session_result', return_value=mock_session_result), \
             patch('src.main.generate_qa_section', return_value=""), \
             patch('src.smartfix.domains.telemetry.otel_provider.start_span', side_effect=mock_start_span), \
             patch('src.smartfix.domains.telemetry.otel_provider.initialize_otel'), \
             patch('src.smartfix.domains.telemetry.otel_provider.shutdown_otel'):

            mock_agent_class.return_value = MagicMock()

            with patch.dict('os.environ', test_env, clear=True):
                reset_config()
                with patch('src.main.config', get_config(testing=True)):
                    main()

        self.assertIn("fix-vulnerability", span_registry)
        op_span = span_registry["fix-vulnerability"]
        attrs = {call[0][0]: call[0][1] for call in op_span.set_attribute.call_args_list}

        self.assertEqual(attrs.get("contrast.smartfix.fix_applied"), False)
        self.assertEqual(attrs.get("contrast.smartfix.pr_created"), False)

    def test_main_initializes_and_shuts_down_otel(self):
        """main() calls initialize_otel, starts smartfix-run span, and calls shutdown_otel."""
        mock_span = MagicMock()
        mock_span_cm = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=False)

        with patch('src.smartfix.domains.telemetry.otel_provider.initialize_otel') as mock_init, \
             patch('src.smartfix.domains.telemetry.otel_provider.start_span', return_value=mock_span_cm) as mock_start, \
             patch('src.smartfix.domains.telemetry.otel_provider.shutdown_otel') as mock_shutdown, \
             patch.dict('os.environ', self.env_vars, clear=True):
            reset_config()
            with patch('src.main.config', get_config(testing=True)):
                main()

        mock_init.assert_called_once()
        mock_start.assert_called_once_with("smartfix-run")
        # session.id must be set
        session_calls = [c for c in mock_span.set_attribute.call_args_list
                         if c[0][0] == "session.id"]
        self.assertTrue(len(session_calls) >= 1, "Expected session.id to be set on run span")
        # vulnerabilities_total must be set; with no vulns processed it should be 0
        total_calls = [c for c in mock_span.set_attribute.call_args_list
                       if c[0][0] == "contrast.smartfix.vulnerabilities_total"]
        self.assertTrue(len(total_calls) >= 1, "Expected contrast.smartfix.vulnerabilities_total to be set")
        self.assertEqual(total_calls[-1][0][1], 0)
        mock_shutdown.assert_called()

    def test_skipped_app_ids_warning_is_logged(self):
        """When skippedAppIds is non-empty, a warning including the count and IDs is logged."""
        vuln_data = {
            'vulnerabilityUuid': 'TEST-VULN-UUID-SKIP',
            'vulnerabilityTitle': 'Test Injection',
            'vulnerabilityRuleName': 'sql-injection',
            'vulnerabilitySeverity': 'HIGH',
            'remediationId': 'REM-SKIP-001',
            'sessionId': 'session-skip',
            'fixSystemPrompt': 'Fix it',
            'fixUserPrompt': 'Please fix',
            'skippedAppIds': ['app-id-2', 'app-id-3'],
        }

        # Return vuln_data once then None to stop the loop
        self.mock_api.side_effect = [vuln_data, None]

        with patch('src.github.github_operations.GitHubOperations.check_pr_status_for_label') as mock_pr_check, \
             patch('src.github.github_operations.GitHubOperations.generate_label_details') as mock_label:
            mock_pr_check.return_value = "OPEN"
            mock_label.return_value = ('contrast-vuln-id:TEST-VULN-UUID-SKIP', 'color', 'desc')

            with patch.dict('os.environ', self.env_vars, clear=True):
                with io.StringIO() as buf, contextlib.redirect_stdout(buf):
                    main()
                    output = buf.getvalue()

        self.assertIn("2 app(s) were inaccessible and skipped", output)
        self.assertIn("app-id-2", output)
        self.assertIn("app-id-3", output)


if __name__ == '__main__':
    unittest.main()

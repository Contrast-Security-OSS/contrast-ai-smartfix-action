# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# #L%
#

"""
Tests for Command Detection Orchestrator.
"""

import unittest
from unittest.mock import patch
from pathlib import Path
from src.smartfix.config.command_detection_orchestrator import (
    detect_build_command_with_fallback,
    NO_OP_BUILD_COMMAND
)


class TestCommandDetectionOrchestrator(unittest.TestCase):
    """Test command detection orchestrator."""

    def setUp(self):
        """Set up test fixtures."""
        self.repo_root = Path("/tmp/test_repo")
        self.remediation_id = "test-remediation-123"

    @patch('src.smartfix.config.command_detection_orchestrator.logger')
    @patch('src.smartfix.config.command_detection_orchestrator.detect_build_command')
    def test_phase1_success_returns_immediately(self, mock_phase1, mock_logger):
        """Phase 1 success returns command immediately without calling Phase 2."""
        # Phase 1 returns successful command
        mock_phase1.return_value = ('mvn test', [])

        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Should return Phase 1 command
        self.assertEqual(result, 'mvn test')
        # Should have called Phase 1
        mock_phase1.assert_called_once_with(
            self.repo_root,
            None,
            self.remediation_id
        )
        # Should log Phase 1 start and success
        self.assertEqual(mock_logger.info.call_count, 2)
        mock_logger.info.assert_any_call(
            "Starting Phase 1: Deterministic build command detection"
        )
        mock_logger.info.assert_any_call(
            "Phase 1 succeeded: Detected BUILD_COMMAND: mvn test"
        )

    @patch('src.smartfix.config.command_detection_orchestrator.logger')
    @patch('src.smartfix.config.command_detection_orchestrator.detect_build_command')
    def test_phase1_failure_triggers_phase2(self, mock_phase1, mock_logger):
        """Phase 1 failure triggers Phase 2 with failure history."""
        # Phase 1 fails with failure history
        phase1_failures = [
            {"command": "mvn test", "error": "mvn: command not found"},
            {"command": "gradle test", "error": "gradle: command not found"}
        ]
        mock_phase1.return_value = (None, phase1_failures)

        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Should return no-op fallback (Phase 2 not implemented yet)
        self.assertEqual(result, NO_OP_BUILD_COMMAND)
        # Should log Phase 1 failure with failure count
        mock_logger.warning.assert_any_call(
            "Phase 1 failed: Tested 2 candidate(s), all failed. "
            "Proceeding to Phase 2 with failure history."
        )
        # Should log Phase 2 start
        mock_logger.info.assert_any_call(
            "Starting Phase 2: LLM-based build command detection"
        )

    @patch('src.smartfix.config.command_detection_orchestrator.logger')
    @patch('src.smartfix.config.command_detection_orchestrator.detect_build_command')
    def test_phase1_no_candidates_triggers_phase2(self, mock_phase1, mock_logger):
        """Phase 1 with no candidates triggers Phase 2."""
        # Phase 1 fails with no candidates
        mock_phase1.return_value = (None, [])

        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Should return no-op fallback
        self.assertEqual(result, NO_OP_BUILD_COMMAND)
        # Should log Phase 1 failure without candidates
        mock_logger.warning.assert_any_call(
            "Phase 1 failed: No suitable build commands found in project structure"
        )
        # Should proceed to Phase 2
        mock_logger.info.assert_any_call(
            "Starting Phase 2: LLM-based build command detection"
        )

    @patch('src.smartfix.config.command_detection_orchestrator.logger')
    @patch('src.smartfix.config.command_detection_orchestrator.detect_build_command')
    def test_both_phases_fail_returns_noop(self, mock_phase1, mock_logger):
        """Both phases failing returns NO_OP_BUILD_COMMAND fallback."""
        # Phase 1 fails
        mock_phase1.return_value = (None, [{"command": "mvn test", "error": "failed"}])

        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Should return no-op fallback
        self.assertEqual(result, NO_OP_BUILD_COMMAND)
        # Should log fallback usage
        mock_logger.warning.assert_any_call(
            f"Both detection phases failed. Using no-op fallback: {NO_OP_BUILD_COMMAND}"
        )

    @patch('src.smartfix.config.command_detection_orchestrator.logger')
    @patch('src.smartfix.config.command_detection_orchestrator.detect_build_command')
    def test_phase1_exception_handled_gracefully(self, mock_phase1, mock_logger):
        """Phase 1 exception is caught and logged, proceeds to Phase 2."""
        # Phase 1 raises exception
        mock_phase1.side_effect = RuntimeError("Unexpected error")

        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Should return no-op fallback
        self.assertEqual(result, NO_OP_BUILD_COMMAND)
        # Should log exception
        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        self.assertIn("Phase 1 detection failed with exception", error_msg)
        self.assertIn("Unexpected error", error_msg)
        # Should proceed to Phase 2
        mock_logger.info.assert_any_call(
            "Starting Phase 2: LLM-based build command detection"
        )

    @patch('src.smartfix.config.command_detection_orchestrator.logger')
    @patch('src.smartfix.config.command_detection_orchestrator.detect_build_command')
    def test_passes_parameters_to_phase1(self, mock_phase1, mock_logger):
        """Orchestrator passes all parameters to Phase 1."""
        mock_phase1.return_value = ('npm test', [])
        project_dir = Path("/tmp/test_repo/backend")

        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            project_dir=project_dir,
            max_llm_attempts=10,
            remediation_id=self.remediation_id
        )

        # Should pass parameters to Phase 1
        mock_phase1.assert_called_once_with(
            self.repo_root,
            project_dir,
            self.remediation_id
        )
        self.assertEqual(result, 'npm test')

    @patch('src.smartfix.config.command_detection_orchestrator.logger')
    @patch('src.smartfix.config.command_detection_orchestrator.detect_build_command')
    def test_logging_at_all_transitions(self, mock_phase1, mock_logger):
        """Verify logging at all phase transitions."""
        # Phase 1 fails, triggers Phase 2, Phase 2 fails
        mock_phase1.return_value = (None, [{"command": "test", "error": "failed"}])

        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Verify all expected log calls
        # 1. Phase 1 start
        mock_logger.info.assert_any_call(
            "Starting Phase 1: Deterministic build command detection"
        )
        # 2. Phase 1 failure
        self.assertTrue(
            any("Phase 1 failed" in str(call) for call in mock_logger.warning.call_args_list)
        )
        # 3. Phase 2 start
        mock_logger.info.assert_any_call(
            "Starting Phase 2: LLM-based build command detection"
        )
        # 4. Fallback warning
        mock_logger.warning.assert_any_call(
            f"Both detection phases failed. Using no-op fallback: {NO_OP_BUILD_COMMAND}"
        )
        self.assertEqual(result, NO_OP_BUILD_COMMAND)


if __name__ == '__main__':
    unittest.main()

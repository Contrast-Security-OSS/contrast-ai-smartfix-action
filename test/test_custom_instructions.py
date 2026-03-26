#!/usr/bin/env python3
# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2026 Contrast Security, Inc.
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

import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from src.smartfix.domains.agents.custom_instructions import load_custom_instructions, HEADER, SOURCE_B_FRAMING


def _config(use_smartfix=True, use_repo=True, base_branch="main"):
    return SimpleNamespace(
        USE_SMARTFIX_INSTRUCTIONS=use_smartfix,
        USE_REPO_AGENT_INSTRUCTIONS=use_repo,
        BASE_BRANCH=base_branch,
    )


def _git_show_result(content=None, returncode=0):
    """Return a mock subprocess.CompletedProcess for git show."""
    result = MagicMock()
    result.returncode = returncode
    if content is not None:
        result.stdout = content if isinstance(content, bytes) else content.encode("utf-8")
    else:
        result.stdout = b""
    return result


class TestLoadCustomInstructions(unittest.TestCase):

    def setUp(self):
        self.repo_path = Path("/fake/repo")
        self.config = _config()

    # --- Source A scenarios ---

    @patch("subprocess.run")
    def test_source_a_present_both_enabled_returns_verbatim(self, mock_run):
        """Source A content returned verbatim under header when both configs true."""
        mock_run.return_value = _git_show_result("Use OWASP Java Encoder for XSS fixes.")
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIsNotNone(result)
        self.assertIn(HEADER, result)
        self.assertIn("Use OWASP Java Encoder for XSS fixes.", result)
        # Verify called with Source A path
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn("SMARTFIX_INSTRUCTIONS.md", call_args[-1])

    @patch("subprocess.run")
    def test_source_a_disabled_falls_through_to_source_b(self, mock_run):
        """When USE_SMARTFIX_INSTRUCTIONS=false, Source A is skipped even if present."""
        source_b_content = "Use factory pattern for all new classes."
        # First call (Source A) — should be skipped entirely
        # Only Source B files should be checked
        mock_run.return_value = _git_show_result(source_b_content)
        config = _config(use_smartfix=False, use_repo=True)
        result = load_custom_instructions(self.repo_path, config)
        self.assertIsNotNone(result)
        # Ensure Source A was never checked
        for call in mock_run.call_args_list:
            args = call[0][0]
            self.assertNotIn("SMARTFIX_INSTRUCTIONS.md", args[-1])

    @patch("subprocess.run")
    def test_source_a_empty_falls_through_to_source_b(self, mock_run):
        """Empty Source A is treated as absent and Source B is checked."""
        source_b_content = "Use interfaces over abstract classes."
        # Source A returns empty; Source B returns content
        mock_run.side_effect = [
            _git_show_result(""),           # Source A: empty
            _git_show_result(source_b_content),  # Source B first file
        ]
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIsNotNone(result)
        self.assertIn(source_b_content, result)

    # --- Source B scenarios ---

    @patch("subprocess.run")
    def test_source_b_copilot_instructions_used_as_first_match(self, mock_run):
        """With no Source A, copilot-instructions.md is used as first Source B match."""
        content = "Follow SOLID principles."
        mock_run.side_effect = [
            _git_show_result(returncode=128),  # Source A: not found
            _git_show_result(content),         # Source B: copilot-instructions.md
        ]
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIsNotNone(result)
        self.assertIn(SOURCE_B_FRAMING, result)
        self.assertIn(content, result)

    @patch("subprocess.run")
    def test_source_b_priority_order_uses_first_match(self, mock_run):
        """Source B checks files in priority order and uses first match."""
        # copilot-instructions.md not found, AGENTS.md found
        mock_run.side_effect = [
            _git_show_result(returncode=128),     # Source A: not found
            _git_show_result(returncode=128),     # copilot-instructions.md: not found
            _git_show_result("AGENTS.md content"),  # AGENTS.md: found
        ]
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIsNotNone(result)
        self.assertIn("AGENTS.md content", result)

    @patch("subprocess.run")
    def test_source_b_disabled_returns_none(self, mock_run):
        """When USE_REPO_AGENT_INSTRUCTIONS=false, Source B is skipped."""
        config = _config(use_smartfix=False, use_repo=False)
        result = load_custom_instructions(self.repo_path, config)
        self.assertIsNone(result)
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_source_b_no_files_found_returns_none(self, mock_run):
        """When no Source B files are found, None is returned."""
        mock_run.return_value = _git_show_result(returncode=128)
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIsNone(result)

    @patch("subprocess.run")
    def test_both_sources_present_only_source_a_used(self, mock_run):
        """When both Source A and B are present, only Source A is used."""
        source_a_content = "SmartFix-specific instructions."
        mock_run.return_value = _git_show_result(source_a_content)
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIn(source_a_content, result)
        # Source B framing must NOT appear (Source A is verbatim)
        self.assertNotIn(SOURCE_B_FRAMING, result)
        # Only one git show call (Source A only)
        self.assertEqual(mock_run.call_count, 1)

    @patch("subprocess.run")
    def test_both_configs_false_returns_none(self, mock_run):
        """When both configs are false, None is returned without any git calls."""
        config = _config(use_smartfix=False, use_repo=False)
        result = load_custom_instructions(self.repo_path, config)
        self.assertIsNone(result)
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_source_a_false_source_b_true_agent_file_present(self, mock_run):
        """USE_SMARTFIX_INSTRUCTIONS=false + USE_REPO_AGENT_INSTRUCTIONS=true uses Source B."""
        content = "Follow CLAUDE.md conventions."
        mock_run.side_effect = [
            _git_show_result(returncode=128),  # copilot-instructions.md: not found
            _git_show_result(returncode=128),  # AGENTS.md: not found
            _git_show_result(content),         # CLAUDE.md: found
        ]
        config = _config(use_smartfix=False, use_repo=True)
        result = load_custom_instructions(self.repo_path, config)
        self.assertIsNotNone(result)
        self.assertIn(SOURCE_B_FRAMING, result)
        self.assertIn(content, result)

    # --- Error handling ---

    @patch("subprocess.run")
    def test_git_show_nonzero_returncode_returns_none(self, mock_run):
        """git show returning non-zero (file not on branch) is treated as absent."""
        mock_run.return_value = _git_show_result(returncode=128)
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIsNone(result)

    @patch("subprocess.run")
    def test_non_utf8_content_decoded_with_replacement(self, mock_run):
        """Non-UTF-8 bytes are decoded with replacement chars, not a crash."""
        bad_bytes = b"Good prefix \xff\xfe bad bytes then more text."
        result_mock = MagicMock()
        result_mock.returncode = 0
        result_mock.stdout = bad_bytes
        mock_run.return_value = result_mock
        # Should not raise; result should contain something
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIsNotNone(result)
        self.assertIn("Good prefix", result)

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10))
    def test_git_show_timeout_returns_none(self, mock_run):
        """subprocess.TimeoutExpired is caught and returns None gracefully."""
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIsNone(result)

    @patch("subprocess.run", side_effect=OSError("git not found"))
    def test_oserror_returns_none(self, mock_run):
        """OSError (e.g. git not in PATH) is caught and returns None gracefully."""
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIsNone(result)

    @patch("subprocess.run")
    def test_large_file_included_without_truncation(self, mock_run):
        """Very large instruction files are included in full."""
        large_content = "A" * 100_000
        mock_run.return_value = _git_show_result(large_content)
        result = load_custom_instructions(self.repo_path, self.config)
        self.assertIsNotNone(result)
        self.assertIn(large_content, result)

    # --- Base branch used ---

    @patch("subprocess.run")
    def test_custom_base_branch_passed_to_git_show(self, mock_run):
        """The configured BASE_BRANCH is passed to git show."""
        mock_run.return_value = _git_show_result("some content")
        config = _config(base_branch="develop")
        load_custom_instructions(self.repo_path, config)
        call_args = mock_run.call_args[0][0]
        # The ref argument to git show should contain the base branch
        self.assertTrue(
            any("develop:" in arg for arg in call_args),
            f"Expected 'develop:' in git show args, got: {call_args}"
        )

    # --- Logging ---

    @patch("subprocess.run")
    def test_source_a_loaded_is_logged(self, mock_run):
        """Loading Source A emits a log message naming the file and branch."""
        mock_run.return_value = _git_show_result("instructions content")
        with patch("src.smartfix.domains.agents.custom_instructions.log") as mock_log:
            load_custom_instructions(self.repo_path, self.config)
            log_messages = " ".join(str(call) for call in mock_log.call_args_list)
            self.assertIn("SMARTFIX_INSTRUCTIONS.md", log_messages)

    @patch("subprocess.run")
    def test_source_b_loaded_is_logged(self, mock_run):
        """Loading Source B emits a log message naming the file and branch."""
        mock_run.side_effect = [
            _git_show_result(returncode=128),         # Source A: not found
            _git_show_result("copilot instructions"), # Source B
        ]
        with patch("src.smartfix.domains.agents.custom_instructions.log") as mock_log:
            load_custom_instructions(self.repo_path, self.config)
            log_messages = " ".join(str(call) for call in mock_log.call_args_list)
            self.assertIn("Source B", log_messages)


if __name__ == "__main__":
    unittest.main()

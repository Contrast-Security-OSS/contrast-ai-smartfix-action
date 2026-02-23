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

"""
Tests for directory_tree_utils.py module.

Tests cover:
- get_directory_tree(): tree CLI success, CLI not found (fallback), timeout (fallback), truncation
- generate_simple_tree(): empty dir, nested dirs, skipped entries
- get_directory_tree_for_agent_prompt(): markdown formatting
- smartfix_agent.py call sites: directory tree appended to fix/QA prompts
"""

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from src.smartfix.domains.agents.directory_tree_utils import (
    get_directory_tree,
    generate_simple_tree,
    get_directory_tree_for_agent_prompt,
)


class TestGetDirectoryTree(unittest.TestCase):
    """Tests for get_directory_tree() — CLI success, fallback, truncation"""

    def test_uses_tree_cli_when_available(self):
        """When tree CLI succeeds (returncode=0), returns its stdout."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ".\n├── src\n└── test\n\n2 directories"

        with patch('subprocess.run', return_value=mock_result) as mock_run:
            result = get_directory_tree(Path('/some/repo'), max_depth=3)

        self.assertEqual(result, mock_result.stdout)
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        self.assertIn('tree', call_args[0][0])

    def test_tree_cli_nonzero_returncode_falls_back_to_python(self):
        """When tree CLI returns non-zero, falls back to generate_simple_tree."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "src").mkdir()
            with patch('subprocess.run', return_value=mock_result):
                result = get_directory_tree(Path(tmpdir), max_depth=2)

        self.assertIn("src", result)

    def test_tree_cli_not_found_falls_back_to_python(self):
        """When tree CLI raises FileNotFoundError, falls back to generate_simple_tree."""
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "src").mkdir()
            with patch('subprocess.run', side_effect=FileNotFoundError("tree not found")):
                result = get_directory_tree(Path(tmpdir), max_depth=2)

        self.assertIn("src", result)

    def test_tree_cli_timeout_falls_back_to_python(self):
        """When tree CLI times out, falls back to generate_simple_tree."""
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "mymodule").mkdir()
            with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(['tree'], 5)):
                result = get_directory_tree(Path(tmpdir), max_depth=2)

        self.assertIn("mymodule", result)

    def test_truncates_when_output_exceeds_max_chars(self):
        """Output longer than max_chars is truncated with a suffix message."""
        long_output = "x" * 200
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = long_output

        with patch('subprocess.run', return_value=mock_result):
            result = get_directory_tree(Path('/repo'), max_depth=3, max_chars=100)

        self.assertEqual(len(result), 100 + len("\n... [truncated, 100 chars omitted]"))
        self.assertIn("[truncated, 100 chars omitted]", result)
        self.assertTrue(result.startswith("x" * 100))

    def test_no_truncation_when_output_within_max_chars(self):
        """Output shorter than max_chars is returned unchanged."""
        short_output = ".\n└── src\n"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = short_output

        with patch('subprocess.run', return_value=mock_result):
            result = get_directory_tree(Path('/repo'), max_depth=3, max_chars=8000)

        self.assertEqual(result, short_output)
        self.assertNotIn("[truncated", result)

    def test_python_fallback_truncates_when_output_exceeds_max_chars(self):
        """Python fallback also truncates output that exceeds max_chars."""
        big_tree = "a" * 200
        with TemporaryDirectory() as tmpdir:
            with patch('subprocess.run', side_effect=FileNotFoundError()):
                with patch('src.smartfix.domains.agents.directory_tree_utils.generate_simple_tree', return_value=big_tree):
                    result = get_directory_tree(Path(tmpdir), max_depth=3, max_chars=50)

        self.assertIn("[truncated", result)
        self.assertTrue(result.startswith("a" * 50))

    def test_returns_unavailable_message_when_python_fallback_fails(self):
        """When both CLI and Python fallback fail, returns '[Directory tree unavailable]'."""
        with TemporaryDirectory() as tmpdir:
            with patch('subprocess.run', side_effect=FileNotFoundError()):
                with patch('src.smartfix.domains.agents.directory_tree_utils.generate_simple_tree',
                           side_effect=RuntimeError("permission denied")):
                    result = get_directory_tree(Path(tmpdir))

        self.assertEqual(result, "[Directory tree unavailable]")


class TestGenerateSimpleTree(unittest.TestCase):
    """Tests for generate_simple_tree() — pure Python fallback"""

    def test_empty_directory_returns_empty_string(self):
        """Empty directory produces empty string (no entries to list)."""
        with TemporaryDirectory() as tmpdir:
            result = generate_simple_tree(Path(tmpdir), max_depth=3)
        self.assertEqual(result, "")

    def test_single_file_uses_corner_branch(self):
        """Single entry (last) uses └── connector."""
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "file.py").touch()
            result = generate_simple_tree(Path(tmpdir), max_depth=2)
        self.assertIn("└── file.py", result)

    def test_multiple_entries_last_uses_corner_others_use_tee(self):
        """Non-last entries use ├── and last uses └──."""
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "aaa.py").touch()
            (Path(tmpdir) / "bbb.py").touch()
            result = generate_simple_tree(Path(tmpdir), max_depth=2)
        self.assertIn("├── aaa.py", result)
        self.assertIn("└── bbb.py", result)

    def test_recurses_into_subdirectories(self):
        """Directories at depth < max_depth are recursed into."""
        with TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "nested.py").touch()
            result = generate_simple_tree(Path(tmpdir), max_depth=3)
        self.assertIn("subdir", result)
        self.assertIn("nested.py", result)

    def test_stops_at_max_depth(self):
        """Does not recurse beyond max_depth."""
        with TemporaryDirectory() as tmpdir:
            deep = Path(tmpdir) / "a" / "b" / "c"
            deep.mkdir(parents=True)
            (deep / "deep_file.py").touch()
            result = generate_simple_tree(Path(tmpdir), max_depth=2)
        # "a" and "b" visible, but "c" and "deep_file.py" should not appear
        self.assertIn("a", result)
        self.assertNotIn("deep_file.py", result)

    def test_skips_hidden_directories(self):
        """Directories starting with '.' are excluded."""
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".git").mkdir()
            (Path(tmpdir) / ".venv").mkdir()
            (Path(tmpdir) / "src").mkdir()
            result = generate_simple_tree(Path(tmpdir), max_depth=2)
        self.assertNotIn(".git", result)
        self.assertNotIn(".venv", result)
        self.assertIn("src", result)

    def test_skips_common_build_directories(self):
        """node_modules, __pycache__, target, build, dist, venv are skipped."""
        skipped = ['node_modules', '__pycache__', 'target', 'build', 'dist', 'venv']
        with TemporaryDirectory() as tmpdir:
            for d in skipped:
                (Path(tmpdir) / d).mkdir()
            (Path(tmpdir) / "src").mkdir()
            result = generate_simple_tree(Path(tmpdir), max_depth=2)
        for d in skipped:
            self.assertNotIn(d, result)
        self.assertIn("src", result)

    def test_entries_are_sorted_alphabetically(self):
        """Entries appear in alphabetical order."""
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "zebra.py").touch()
            (Path(tmpdir) / "alpha.py").touch()
            (Path(tmpdir) / "mango.py").touch()
            result = generate_simple_tree(Path(tmpdir), max_depth=2)
        alpha_pos = result.index("alpha.py")
        mango_pos = result.index("mango.py")
        zebra_pos = result.index("zebra.py")
        self.assertLess(alpha_pos, mango_pos)
        self.assertLess(mango_pos, zebra_pos)


class TestGetDirectoryTreeForAgentPrompt(unittest.TestCase):
    """Tests for get_directory_tree_for_agent_prompt() — markdown formatting"""

    def test_returns_markdown_section_header(self):
        """Result starts with the expected markdown section header."""
        with patch('src.smartfix.domains.agents.directory_tree_utils.get_directory_tree', return_value=".\n└── src"):
            result = get_directory_tree_for_agent_prompt(Path('/repo'))
        self.assertIn("## Repository Directory Tree", result)

    def test_tree_wrapped_in_code_fence(self):
        """Tree content is wrapped in triple-backtick code fence."""
        tree_content = ".\n└── src"
        with patch('src.smartfix.domains.agents.directory_tree_utils.get_directory_tree', return_value=tree_content):
            result = get_directory_tree_for_agent_prompt(Path('/repo'))
        self.assertIn(f"```\n{tree_content}\n```", result)

    def test_section_starts_with_double_newline(self):
        """Section is separated from preceding content with double newline."""
        with patch('src.smartfix.domains.agents.directory_tree_utils.get_directory_tree', return_value="tree"):
            result = get_directory_tree_for_agent_prompt(Path('/repo'))
        self.assertTrue(result.startswith("\n\n"))

    def test_passes_max_depth_and_max_chars_to_get_directory_tree(self):
        """Custom max_depth and max_chars are forwarded to get_directory_tree."""
        with patch('src.smartfix.domains.agents.directory_tree_utils.get_directory_tree', return_value="tree") as mock_tree:
            get_directory_tree_for_agent_prompt(Path('/repo'), max_depth=5, max_chars=1000)
        mock_tree.assert_called_once_with(Path('/repo'), 5, 1000)


class TestSmartfixAgentDirectoryTreeIntegration(unittest.TestCase):
    """
    Tests that SmartFixAgent appends the directory tree to Fix and QA user prompts.
    These tests verify the call sites added in contrast-29q.
    """

    def _make_context(self, repo_path=None):
        """Build a minimal RemediationContext mock for testing."""
        context = MagicMock()
        context.repo_config.repo_path = repo_path or Path('/tmp/test-repo')
        context.remediation_id = "rem-123"
        context.session_id = "sess-456"
        context.prompts.fix_user_prompt = "Fix this vulnerability."
        context.prompts.fix_system_prompt = "You are a security expert."
        context.prompts.qa_system_prompt = "You are a QA reviewer."
        context.prompts.get_processed_qa_user_prompt.return_value = "Review this fix."
        context.build_config.has_build_command.return_value = False
        return context

    def test_fix_agent_appends_directory_tree_to_user_prompt(self):
        """
        _run_fix_agent_execution should append the directory tree to
        fix_user_prompt before passing it to _run_agent_in_event_loop.
        """
        from src.smartfix.domains.agents.smartfix_agent import SmartFixAgent

        agent = SmartFixAgent()
        context = self._make_context()
        tree_section = "\n\n## Repository Directory Tree\n\n```\n.\n└── src\n```"

        with patch('src.smartfix.domains.agents.smartfix_agent.get_directory_tree_for_agent_prompt',
                   return_value=tree_section) as mock_tree:
            with patch('src.smartfix.domains.agents.smartfix_agent._run_agent_in_event_loop',
                       return_value="fix completed") as mock_run:
                agent._run_fix_agent_execution(context)

        mock_tree.assert_called_once_with(context.repo_config.repo_path)
        actual_prompt = mock_run.call_args[0][3]
        self.assertEqual(actual_prompt, "Fix this vulnerability." + tree_section)

    def test_qa_agent_appends_directory_tree_to_query(self):
        """
        _run_qa_agent should append the directory tree to qa_query
        before passing it to _run_agent_in_event_loop.
        """
        from src.smartfix.domains.agents.smartfix_agent import SmartFixAgent

        agent = SmartFixAgent()
        context = self._make_context()
        tree_section = "\n\n## Repository Directory Tree\n\n```\n.\n└── src\n```"

        with patch('src.smartfix.domains.agents.smartfix_agent.get_directory_tree_for_agent_prompt',
                   return_value=tree_section) as mock_tree:
            with patch('src.smartfix.domains.agents.smartfix_agent._run_agent_in_event_loop',
                       return_value="qa completed") as mock_run:
                agent._run_qa_agent(context, "build output", ["src/Foo.java"])

        mock_tree.assert_called_once_with(context.repo_config.repo_path)
        actual_prompt = mock_run.call_args[0][3]
        self.assertIn("Review this fix.", actual_prompt)
        self.assertIn(tree_section, actual_prompt)

    def test_fix_agent_tree_called_with_correct_repo_path(self):
        """get_directory_tree_for_agent_prompt receives the repo_path from context."""
        from src.smartfix.domains.agents.smartfix_agent import SmartFixAgent

        repo_path = Path('/specific/repo/path')
        agent = SmartFixAgent()
        context = self._make_context(repo_path=repo_path)

        with patch('src.smartfix.domains.agents.smartfix_agent.get_directory_tree_for_agent_prompt',
                   return_value="\n\n## Repository Directory Tree\n\n```\ntree\n```") as mock_tree:
            with patch('src.smartfix.domains.agents.smartfix_agent._run_agent_in_event_loop',
                       return_value="done"):
                agent._run_fix_agent_execution(context)

        mock_tree.assert_called_once_with(repo_path)


if __name__ == '__main__':
    unittest.main()

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

"""Tests for CODEOWNERS file parsing and reviewer resolution (TS-38988)."""

import unittest
from pathlib import Path
import tempfile

from src.smartfix.domains.scm.codeowners import find_codeowners_file, get_reviewers_for_files


class TestFindCodeownersFile(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo_root = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_finds_github_codeowners(self):
        """Finds CODEOWNERS in .github/ directory first."""
        github_dir = self.repo_root / ".github"
        github_dir.mkdir()
        codeowners = github_dir / "CODEOWNERS"
        codeowners.write_text("* @owner\n")

        result = find_codeowners_file(self.repo_root)

        self.assertEqual(result, codeowners)

    def test_finds_root_codeowners_when_no_github_dir(self):
        """Falls back to CODEOWNERS in repo root."""
        codeowners = self.repo_root / "CODEOWNERS"
        codeowners.write_text("* @owner\n")

        result = find_codeowners_file(self.repo_root)

        self.assertEqual(result, codeowners)

    def test_finds_docs_codeowners_as_last_fallback(self):
        """Falls back to docs/CODEOWNERS when others are absent."""
        docs_dir = self.repo_root / "docs"
        docs_dir.mkdir()
        codeowners = docs_dir / "CODEOWNERS"
        codeowners.write_text("* @owner\n")

        result = find_codeowners_file(self.repo_root)

        self.assertEqual(result, codeowners)

    def test_prefers_github_over_root(self):
        """Prefers .github/CODEOWNERS over root CODEOWNERS."""
        github_dir = self.repo_root / ".github"
        github_dir.mkdir()
        (github_dir / "CODEOWNERS").write_text("* @github-owner\n")
        (self.repo_root / "CODEOWNERS").write_text("* @root-owner\n")

        result = find_codeowners_file(self.repo_root)

        self.assertEqual(result, github_dir / "CODEOWNERS")

    def test_returns_none_when_no_codeowners(self):
        """Returns None when no CODEOWNERS file exists anywhere."""
        result = find_codeowners_file(self.repo_root)

        self.assertIsNone(result)


class TestGetReviewersForFiles(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.repo_root = Path(self.tmpdir)
        self.github_dir = self.repo_root / ".github"
        self.github_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def _write_codeowners(self, content: str):
        (self.github_dir / "CODEOWNERS").write_text(content)

    def test_returns_empty_set_when_no_codeowners_file(self):
        """Returns empty set when no CODEOWNERS file exists."""
        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, set())

    def test_returns_empty_set_when_no_files_match(self):
        """Returns empty set when changed files don't match any pattern."""
        self._write_codeowners("*.rb @ruby-owner\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, set())

    def test_ignores_comment_lines(self):
        """Lines starting with # are ignored."""
        self._write_codeowners("# This is a comment\n*.py @python-owner\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, {"python-owner"})

    def test_ignores_inline_comments(self):
        """Inline comments (# ...) are stripped; only owners before the # are returned."""
        self._write_codeowners("*.py @alice @bob # backend team\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, {"alice", "bob"})

    def test_inline_comment_words_not_treated_as_owners(self):
        """Words after an inline # are not returned as reviewer handles."""
        self._write_codeowners("*.py @alice # backend team\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertNotIn("backend", result)
        self.assertNotIn("team", result)
        self.assertNotIn("#", result)

    def test_ignores_empty_lines(self):
        """Empty lines are ignored."""
        self._write_codeowners("\n*.py @python-owner\n\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, {"python-owner"})

    def test_strips_at_prefix_from_usernames(self):
        """@ prefix is stripped from reviewer handles."""
        self._write_codeowners("*.py @alice @bob\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, {"alice", "bob"})

    def test_wildcard_matches_any_file_with_extension(self):
        """*.py matches any Python file regardless of directory."""
        self._write_codeowners("*.py @python-owner\n")

        result = get_reviewers_for_files(["src/deep/nested/module.py"], self.repo_root)

        self.assertEqual(result, {"python-owner"})

    def test_directory_pattern_matches_files_in_directory(self):
        """src/ pattern matches files inside that directory."""
        self._write_codeowners("src/ @src-owner\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, {"src-owner"})

    def test_exact_file_pattern_matches(self):
        """Exact file path pattern matches that specific file."""
        self._write_codeowners("src/config.py @config-owner\n")

        result = get_reviewers_for_files(["src/config.py"], self.repo_root)

        self.assertEqual(result, {"config-owner"})

    def test_exact_file_pattern_does_not_match_other_files(self):
        """Exact file pattern does not match other files."""
        self._write_codeowners("src/config.py @config-owner\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, set())

    def test_team_ref_included_without_stripping_org(self):
        """Team refs like org/team are included as-is (only leading @ stripped)."""
        self._write_codeowners("*.py @myorg/backend-team\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, {"myorg/backend-team"})

    def test_multiple_owners_per_pattern(self):
        """Multiple owners on one line are all returned."""
        self._write_codeowners("*.py @alice @bob @myorg/team\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, {"alice", "bob", "myorg/team"})

    def test_multiple_changed_files_union_of_owners(self):
        """Owners from all matching files are combined."""
        self._write_codeowners("*.py @python-owner\n*.js @js-owner\n")

        result = get_reviewers_for_files(["src/main.py", "src/app.js"], self.repo_root)

        self.assertEqual(result, {"python-owner", "js-owner"})

    def test_catch_all_pattern_matches_any_file(self):
        """* pattern matches any file."""
        self._write_codeowners("* @default-owner\n")

        result = get_reviewers_for_files(["src/main.py", "README.md"], self.repo_root)

        self.assertEqual(result, {"default-owner"})

    def test_later_pattern_adds_owners_for_matching_files(self):
        """All matching patterns contribute owners (union semantics)."""
        self._write_codeowners("* @default-owner\n*.py @python-owner\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertIn("python-owner", result)
        self.assertIn("default-owner", result)

    def test_no_duplicate_owners(self):
        """Same owner listed in multiple matching patterns appears only once."""
        self._write_codeowners("* @alice\n*.py @alice\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, {"alice"})

    def test_root_anchored_directory_pattern_matches(self):
        """/docs/ matches files inside docs/ at the repo root."""
        self._write_codeowners("/docs/ @docs-owner\n")

        result = get_reviewers_for_files(["docs/guide.md"], self.repo_root)

        self.assertEqual(result, {"docs-owner"})

    def test_root_anchored_glob_pattern_matches(self):
        """/src/*.py matches Python files directly inside src/."""
        self._write_codeowners("/src/*.py @src-owner\n")

        result = get_reviewers_for_files(["src/main.py"], self.repo_root)

        self.assertEqual(result, {"src-owner"})

    def test_root_anchored_pattern_does_not_produce_double_slash(self):
        """/docs/ does not require the file path to start with //docs/."""
        self._write_codeowners("/docs/ @docs-owner\n")

        result = get_reviewers_for_files(["other/file.md"], self.repo_root)

        self.assertEqual(result, set())


if __name__ == "__main__":
    unittest.main()

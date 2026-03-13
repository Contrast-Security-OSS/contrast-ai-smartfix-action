# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2026 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# #L%
#

"""
Integration Tests for Build Command Detection (Store-Only)

Tests the deterministic detection flow with real file systems:
- File marker-based candidate generation
- Tool availability checking (--version)
- Security allowlist validation

Detection is store-only: it does NOT run actual builds.
The Fix agent's BuildTool handles build execution and verification.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.smartfix.config.command_detector import detect_build_command


class TestBuildCommandDetectionIntegration(unittest.TestCase):
    """Integration tests for store-only build command detection."""

    def setUp(self):
        """Set up temporary directory for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_file(self, relative_path: str, content: str = ""):
        """Helper to create a file with content in test directory."""
        file_path = self.repo_root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return file_path

    @patch('subprocess.run')
    def test_real_maven_project_detected(self, mock_subprocess):
        """Real Maven project: detects mvn command from pom.xml marker."""
        self._create_file('pom.xml', '<project><artifactId>test</artifactId></project>')
        self._create_file('src/main/java/App.java', 'public class App {}')

        # Mock mvn --version check (tool exists)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='Maven 3.8.1')

        result = detect_build_command(repo_root=self.repo_root)

        # Should detect Maven command without running a build
        self.assertIsNotNone(result)
        self.assertIn('mvn', result.lower())

    @patch('src.smartfix.config.command_detector._validate_command_exists')
    def test_missing_tools_returns_none(self, mock_validate):
        """Missing tools: returns None when no tools are available."""
        self._create_file('pom.xml', '<project><artifactId>test</artifactId></project>')

        # Mock: all tools missing
        mock_validate.return_value = False

        result = detect_build_command(repo_root=self.repo_root)

        self.assertIsNone(result)
        self.assertGreater(mock_validate.call_count, 0)

    def test_no_markers_returns_none(self):
        """No build markers: returns None for empty project."""
        self._create_file('README.md', '# Test Project')
        self._create_file('src/code.py', 'print("hello")')

        result = detect_build_command(repo_root=self.repo_root)

        self.assertIsNone(result)

    @patch('subprocess.run')
    def test_gradle_project_detected(self, mock_subprocess):
        """Gradle project: detects gradle command from build.gradle marker."""
        self._create_file('build.gradle', 'plugins { id "java" }')
        self._create_file('settings.gradle', 'rootProject.name = "test"')

        mock_subprocess.return_value = MagicMock(returncode=0, stdout='Gradle 7.4')

        result = detect_build_command(repo_root=self.repo_root)

        self.assertIsNotNone(result)
        self.assertTrue(
            'gradle' in result.lower() or 'gradlew' in result.lower(),
            f"Expected Gradle command, got: {result}"
        )

    @patch('subprocess.run')
    def test_npm_project_detected(self, mock_subprocess):
        """npm project: detects npm command from package.json marker."""
        self._create_file('package.json', '{"name": "test", "scripts": {"test": "jest"}}')

        mock_subprocess.return_value = MagicMock(returncode=0, stdout='8.19.2')

        result = detect_build_command(repo_root=self.repo_root)

        self.assertIsNotNone(result)
        self.assertIn('npm', result.lower())

    @patch('subprocess.run')
    def test_makefile_project_detected(self, mock_subprocess):
        """Makefile project: detects make command from Makefile marker."""
        self._create_file('Makefile', 'test:\n\t@python -m pytest\n\n.PHONY: test\n')

        mock_subprocess.return_value = MagicMock(returncode=0, stdout='GNU Make 4.3')

        result = detect_build_command(repo_root=self.repo_root)

        self.assertIsNotNone(result)
        self.assertIn('make', result.lower())

    @patch('subprocess.run')
    def test_detection_never_raises_exceptions(self, mock_subprocess):
        """Detection returns None on errors, never raises."""
        self._create_file('pom.xml', '<project></project>')

        mock_subprocess.side_effect = RuntimeError("Subprocess explosion")

        result = detect_build_command(repo_root=self.repo_root)

        self.assertIsNone(result)

    @patch('subprocess.run')
    def test_project_dir_parameter_for_monorepos(self, mock_subprocess):
        """project_dir parameter scopes detection to subdirectory."""
        backend_dir = self.repo_root / 'backend'
        backend_dir.mkdir(parents=True)
        (backend_dir / 'pom.xml').write_text('<project></project>')

        mock_subprocess.return_value = MagicMock(returncode=0, stdout='Maven 3.8.1')

        result = detect_build_command(
            repo_root=self.repo_root,
            project_dir=backend_dir,
        )

        self.assertIsNotNone(result)
        self.assertIn('mvn', result.lower())

    @patch('subprocess.run')
    def test_no_build_execution_during_detection(self, mock_subprocess):
        """Detection must NOT run actual builds (store-only)."""
        self._create_file('pom.xml', '<project></project>')

        mock_subprocess.return_value = MagicMock(returncode=0, stdout='Maven 3.8.1')

        detect_build_command(repo_root=self.repo_root)

        # Verify subprocess was only called for --version checks, not builds
        for call in mock_subprocess.call_args_list:
            args = call[0][0] if call[0] else call[1].get('args', [])
            if isinstance(args, list):
                # Should only have version/help flags, never actual build commands
                self.assertTrue(
                    any(flag in args for flag in ['--version', '--help', '-v', '-h']),
                    f"Unexpected subprocess call (possible build execution): {args}"
                )


if __name__ == '__main__':
    unittest.main()

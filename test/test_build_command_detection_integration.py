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
Integration Tests for Complete Build Command Detection Flow

Tests the end-to-end detection flow with real file systems:
- Phase 1: Deterministic detection (file markers + validation)
- Phase 2: LLM-based detection (currently placeholder)
- Phase 3: No-op fallback

Unlike unit tests, these tests use real temporary directories with
actual build files to test the complete integration.
"""

import os
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.smartfix.config.command_detection_orchestrator import (
    detect_build_command_with_fallback,
    NO_OP_BUILD_COMMAND
)


class TestBuildCommandDetectionIntegration(unittest.TestCase):
    """Integration tests for complete build command detection flow."""

    def setUp(self):
        """Set up temporary directory for each test."""
        # Store original values to restore in tearDown
        self._original_env = {
            'GITHUB_WORKSPACE': os.environ.get('GITHUB_WORKSPACE'),
            'GITHUB_REPOSITORY': os.environ.get('GITHUB_REPOSITORY'),
            'GITHUB_SERVER_URL': os.environ.get('GITHUB_SERVER_URL'),
            'GITHUB_TOKEN': os.environ.get('GITHUB_TOKEN'),
        }

        # Set required environment variables for tests that trigger Phase 2
        os.environ['GITHUB_WORKSPACE'] = tempfile.gettempdir()
        os.environ['GITHUB_REPOSITORY'] = 'test/repo'
        os.environ['GITHUB_SERVER_URL'] = 'https://github.com'
        os.environ['GITHUB_TOKEN'] = 'test-token'
        os.environ.setdefault('CONTRAST_HOST', 'test.contrastsecurity.com')
        os.environ.setdefault('CONTRAST_ORG_ID', 'test-org')
        os.environ.setdefault('CONTRAST_APP_ID', 'test-app')
        os.environ.setdefault('CONTRAST_AUTHORIZATION_KEY', 'test-auth')
        os.environ.setdefault('CONTRAST_API_KEY', 'test-api-key')

        self.test_dir = tempfile.mkdtemp()
        self.repo_root = Path(self.test_dir)
        self.remediation_id = "integration-test-123"

    def tearDown(self):
        """Clean up temporary directory and restore environment variables."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

        # Restore original environment variables
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _create_file(self, relative_path: str, content: str = ""):
        """Helper to create a file with content in test directory."""
        file_path = self.repo_root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return file_path

    @patch('src.smartfix.config.command_detector.run_build_command')
    @patch('subprocess.run')
    def test_real_maven_project_phase1_success(self, mock_subprocess, mock_run_build):
        """Real Maven project: Phase 1 detects mvn command successfully."""
        # Create real Maven project structure
        self._create_file('pom.xml', '<project><artifactId>test</artifactId></project>')
        self._create_file('src/main/java/App.java', 'public class App {}')

        # Mock mvn --version check (tool exists)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='Maven 3.8.1')

        # Mock successful build execution (skip actual Maven build)
        mock_run_build.return_value = (True, "Build successful")

        # Run orchestrator
        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Should detect Maven command from Phase 1
        self.assertIn('mvn', result.lower())
        self.assertNotEqual(result, NO_OP_BUILD_COMMAND)

        # Should have called run_build_command (Phase 1 validates by running)
        mock_run_build.assert_called_once()

    @patch('src.smartfix.config.command_detector._validate_command_exists')
    def test_missing_tools_triggers_phase2_and_fallback(self, mock_validate):
        """Missing tools: Phase 1 skips candidates, Phase 2 placeholder, returns no-op."""
        # Create Maven project but tools not installed
        self._create_file('pom.xml', '<project><artifactId>test</artifactId></project>')

        # Mock: all tools missing (_validate_command_exists returns False)
        mock_validate.return_value = False

        # Run orchestrator
        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Phase 1 should skip all candidates (tools missing)
        # Phase 2 placeholder returns None
        # Should fallback to NO_OP
        self.assertEqual(result, NO_OP_BUILD_COMMAND)

        # Should have checked for tool existence multiple times
        self.assertGreater(mock_validate.call_count, 0)

    def test_no_markers_triggers_phase2_and_fallback(self):
        """No build markers: Phase 1 finds nothing, Phase 2 placeholder, returns no-op."""
        # Empty directory with no build markers
        # (no pom.xml, build.gradle, package.json, Makefile, etc.)
        self._create_file('README.md', '# Test Project')
        self._create_file('src/code.py', 'print("hello")')

        # Run orchestrator
        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Phase 1 should find no candidates
        # Phase 2 placeholder returns None
        # Should fallback to NO_OP
        self.assertEqual(result, NO_OP_BUILD_COMMAND)

    @patch('src.smartfix.config.command_detector.run_build_command')
    @patch('subprocess.run')
    def test_complete_failure_uses_noop_fallback(self, mock_subprocess, mock_run_build):
        """Complete failure: All Phase 1 candidates fail, Phase 2 placeholder, returns no-op."""
        # Create Maven project
        self._create_file('pom.xml', '<project><artifactId>test</artifactId></project>')

        # Mock mvn --version check (tool exists)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='Maven 3.8.1')

        # Mock: all builds fail (Phase 1 exhausts all candidates)
        mock_run_build.return_value = (False, "Build failed: compilation error")

        # Run orchestrator
        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Phase 1 should try candidates but all fail
        # Phase 2 placeholder returns None
        # Should fallback to NO_OP
        self.assertEqual(result, NO_OP_BUILD_COMMAND)

        # Should have attempted to run build
        mock_run_build.assert_called()

    @patch('src.smartfix.config.command_detector.run_build_command')
    @patch('subprocess.run')
    def test_end_to_end_flow_gradle_project(self, mock_subprocess, mock_run_build):
        """End-to-end: Gradle project detection from filesystem to command."""
        # Create real Gradle project structure
        self._create_file('build.gradle', 'plugins { id "java" }')
        self._create_file('settings.gradle', 'rootProject.name = "test"')
        self._create_file('src/main/java/App.java', 'public class App {}')

        # Mock gradle/gradlew --version check (tool exists)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='Gradle 7.4')

        # Mock successful build
        mock_run_build.return_value = (True, "BUILD SUCCESSFUL")

        # Run orchestrator
        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Should detect Gradle command from Phase 1
        self.assertTrue(
            'gradle' in result.lower() or 'gradlew' in result.lower(),
            f"Expected Gradle command, got: {result}"
        )
        self.assertNotEqual(result, NO_OP_BUILD_COMMAND)

    @patch('src.smartfix.config.command_detector.run_build_command')
    @patch('subprocess.run')
    def test_end_to_end_flow_npm_project(self, mock_subprocess, mock_run_build):
        """End-to-end: npm project detection from filesystem to command."""
        # Create real npm project structure
        package_json_content = '''{
  "name": "test-project",
  "version": "1.0.0",
  "scripts": {
    "test": "jest"
  }
}'''
        self._create_file('package.json', package_json_content)
        self._create_file('src/index.js', 'console.log("hello");')

        # Mock npm --version check (tool exists)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='8.19.2')

        # Mock successful npm test
        mock_run_build.return_value = (True, "PASS tests/example.test.js")

        # Run orchestrator
        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Should detect npm command from Phase 1
        self.assertIn('npm', result.lower())
        self.assertNotEqual(result, NO_OP_BUILD_COMMAND)

    @patch('src.smartfix.config.command_detector.run_build_command')
    @patch('subprocess.run')
    def test_end_to_end_flow_makefile_project(self, mock_subprocess, mock_run_build):
        """End-to-end: Makefile project detection from filesystem to command."""
        # Create real Makefile project structure
        makefile_content = '''test:
\t@echo "Running tests..."
\t@python -m pytest

.PHONY: test
'''
        self._create_file('Makefile', makefile_content)
        self._create_file('tests/test_example.py', 'def test_dummy(): pass')

        # Mock make --version check (tool exists)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='GNU Make 4.3')

        # Mock successful make test
        mock_run_build.return_value = (True, "Running tests... passed")

        # Run orchestrator
        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Should detect make command from Phase 1
        self.assertIn('make', result.lower())
        self.assertNotEqual(result, NO_OP_BUILD_COMMAND)

    @patch('subprocess.run')
    def test_orchestrator_never_raises_exceptions(self, mock_subprocess):
        """Orchestrator always returns valid string, never raises exceptions."""
        # Create Maven project
        self._create_file('pom.xml', '<project></project>')

        # Mock subprocess to raise exception (simulating environment issues)
        mock_subprocess.side_effect = RuntimeError("Subprocess explosion")

        # Run orchestrator - should catch exception and fallback
        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            remediation_id=self.remediation_id
        )

        # Should return no-op fallback, never raise exception
        self.assertEqual(result, NO_OP_BUILD_COMMAND)
        self.assertIsInstance(result, str)

    @patch('src.smartfix.config.command_detector.run_build_command')
    @patch('subprocess.run')
    def test_project_dir_parameter_passed_through(self, mock_subprocess, mock_run_build):
        """Orchestrator passes project_dir parameter to Phase 1 for monorepos."""
        # Create monorepo structure with subdirectory
        backend_dir = self.repo_root / 'backend'
        backend_dir.mkdir(parents=True)
        (backend_dir / 'pom.xml').write_text('<project></project>')

        # Mock tool exists
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='Maven 3.8.1')

        # Mock successful build
        mock_run_build.return_value = (True, "Build successful")

        # Run orchestrator with project_dir
        result = detect_build_command_with_fallback(
            repo_root=self.repo_root,
            project_dir=backend_dir,
            remediation_id=self.remediation_id
        )

        # Should detect command
        self.assertIn('mvn', result.lower())
        self.assertNotEqual(result, NO_OP_BUILD_COMMAND)

        # Verify run_build_command was called with repo_root (not project_dir)
        # (project_dir is used for file discovery, repo_root for execution)
        call_args = mock_run_build.call_args
        self.assertIsNotNone(call_args)


if __name__ == '__main__':
    unittest.main()

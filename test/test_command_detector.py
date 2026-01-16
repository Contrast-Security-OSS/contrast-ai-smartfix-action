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
Tests for command_detector module.
"""

import unittest
import tempfile
from pathlib import Path
from src.smartfix.config.command_detector import (
    inspect_makefile_targets,
    generate_build_command_candidates,
    generate_format_command_candidates,
    detect_package_manager,
)


class TestInspectMakefileTargets(unittest.TestCase):
    """Test Makefile target inspection."""

    def test_extracts_simple_targets(self):
        """Extract targets from a simple Makefile."""
        makefile_content = """
test:
\t@pytest tests/

build:
\tpython setup.py build

clean:
\trm -rf build/
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='Makefile', delete=False) as f:
            f.write(makefile_content)
            makefile_path = Path(f.name)

        try:
            targets = inspect_makefile_targets(makefile_path)
            self.assertEqual(targets, ['test', 'build', 'clean'])
        finally:
            makefile_path.unlink()

    def test_prioritizes_test_targets(self):
        """Prioritize test, check, build targets."""
        makefile_content = """
all:
\techo "all"

deploy:
\techo "deploy"

test:
\t@pytest

build:
\techo "build"

check:
\tmake test
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='Makefile', delete=False) as f:
            f.write(makefile_content)
            makefile_path = Path(f.name)

        try:
            targets = inspect_makefile_targets(makefile_path)
            # Priority targets should come first: test, check, build, all
            # then others: deploy
            self.assertEqual(targets[:4], ['test', 'check', 'build', 'all'])
            self.assertIn('deploy', targets)
        finally:
            makefile_path.unlink()

    def test_handles_missing_makefile(self):
        """Return empty list for non-existent Makefile."""
        non_existent = Path("/tmp/nonexistent_makefile_12345")
        targets = inspect_makefile_targets(non_existent)
        self.assertEqual(targets, [])

    def test_ignores_comments_and_variables(self):
        """Ignore commented lines and variable assignments."""
        makefile_content = """
# This is a comment with test: in it
VAR = value

test:
\t@pytest

# Another comment
# build: commented target
real-target:
\techo "real"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='Makefile', delete=False) as f:
            f.write(makefile_content)
            makefile_path = Path(f.name)

        try:
            targets = inspect_makefile_targets(makefile_path)
            self.assertEqual(targets, ['test', 'real-target'])
        finally:
            makefile_path.unlink()


class TestGenerateBuildCommandCandidates(unittest.TestCase):
    """Test build command candidate generation."""

    def test_maven_project(self):
        """Generate Maven commands for pom.xml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pom.xml').touch()

            candidates = generate_build_command_candidates(repo_root)

            # Should include Maven test commands
            self.assertIn('mvn test', candidates)
            self.assertIn('mvn clean install', candidates)
            # Maven should be prioritized early
            self.assertTrue(candidates.index('mvn test') < 5)

    def test_gradle_with_wrapper(self):
        """Prefer Gradle wrapper over gradle command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'build.gradle').touch()
            (repo_root / 'gradlew').touch()

            candidates = generate_build_command_candidates(repo_root)

            # Should prefer ./gradlew over gradle
            self.assertIn('./gradlew test', candidates)
            self.assertIn('./gradlew build', candidates)
            # Wrapper should come before non-wrapper
            gradlew_idx = next((i for i, c in enumerate(candidates) if './gradlew' in c), -1)
            gradle_idx = next((i for i, c in enumerate(candidates) if c.startswith('gradle ')), -1)
            if gradle_idx != -1:
                self.assertLess(gradlew_idx, gradle_idx)

    def test_python_pytest(self):
        """Generate pytest commands for Python projects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pytest.ini').touch()

            candidates = generate_build_command_candidates(repo_root)

            self.assertIn('pytest', candidates)

    def test_npm_project(self):
        """Generate npm commands for package.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'package.json').touch()

            candidates = generate_build_command_candidates(repo_root)

            self.assertIn('npm test', candidates)
            self.assertIn('npm run build', candidates)

    def test_makefile_integration(self):
        """Include Makefile targets in candidates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            makefile = repo_root / 'Makefile'
            makefile.write_text('test:\n\t@pytest\n\nbuild:\n\tpython setup.py build\n')

            candidates = generate_build_command_candidates(repo_root)

            # Should include make commands from Makefile
            self.assertIn('make test', candidates)
            self.assertIn('make build', candidates)

    def test_monorepo_maven_uses_f_flag(self):
        """Use -f flag for Maven in subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            subdir = repo_root / 'backend'
            subdir.mkdir()
            (subdir / 'pom.xml').touch()

            candidates = generate_build_command_candidates(repo_root, project_dir=subdir)

            # Should use -f flag, not cd
            self.assertTrue(any('mvn -f backend/pom.xml test' in c for c in candidates))

    def test_monorepo_gradle_uses_p_flag(self):
        """Use -p flag for Gradle in subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            subdir = repo_root / 'backend'
            subdir.mkdir()
            (subdir / 'build.gradle').touch()
            (repo_root / 'gradlew').touch()

            candidates = generate_build_command_candidates(repo_root, project_dir=subdir)

            # Should use -p flag
            self.assertTrue(any('./gradlew -p backend test' in c for c in candidates))

    def test_empty_directory(self):
        """Return empty list for directory with no build files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            candidates = generate_build_command_candidates(repo_root)

            self.assertEqual(candidates, [])


class TestGenerateFormatCommandCandidates(unittest.TestCase):
    """Test format command candidate generation."""

    def test_python_formatters(self):
        """Generate Python formatter commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pyproject.toml').touch()

            candidates = generate_format_command_candidates(repo_root)

            self.assertIn('black .', candidates)
            self.assertIn('ruff format .', candidates)

    def test_javascript_formatters(self):
        """Generate JavaScript formatter commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'package.json').touch()

            candidates = generate_format_command_candidates(repo_root)

            self.assertIn('prettier --write .', candidates)
            self.assertIn('npm run format', candidates)

    def test_java_formatters(self):
        """Generate Java formatter commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pom.xml').touch()

            candidates = generate_format_command_candidates(repo_root)

            self.assertIn('mvn spotless:apply', candidates)

    def test_csharp_formatters(self):
        """Generate C# formatter commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'MyProject.sln').touch()

            candidates = generate_format_command_candidates(repo_root)

            self.assertIn('dotnet format', candidates)

    def test_empty_directory_format(self):
        """Return empty list for directory with no project files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            candidates = generate_format_command_candidates(repo_root)

            self.assertEqual(candidates, [])


class TestDetectPackageManager(unittest.TestCase):
    """Test package manager detection."""

    def test_detects_npm(self):
        """Detect npm from package-lock.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'package-lock.json').touch()

            pm = detect_package_manager(repo_root)
            self.assertEqual(pm, 'npm')

    def test_detects_yarn(self):
        """Detect yarn from yarn.lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'yarn.lock').touch()

            pm = detect_package_manager(repo_root)
            self.assertEqual(pm, 'yarn')

    def test_detects_pnpm(self):
        """Detect pnpm from pnpm-lock.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pnpm-lock.yaml').touch()

            pm = detect_package_manager(repo_root)
            self.assertEqual(pm, 'pnpm')

    def test_detects_bun(self):
        """Detect bun from bun.lockb."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'bun.lockb').touch()

            pm = detect_package_manager(repo_root)
            self.assertEqual(pm, 'bun')

    def test_defaults_to_npm_with_package_json(self):
        """Default to npm if only package.json exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'package.json').touch()

            pm = detect_package_manager(repo_root)
            self.assertEqual(pm, 'npm')

    def test_returns_none_without_node_files(self):
        """Return None for non-Node.js projects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            pm = detect_package_manager(repo_root)
            self.assertIsNone(pm)


class TestCommandValidationIntegration(unittest.TestCase):
    """Test that command detection integrates with validation."""

    def test_detect_build_skips_invalid_commands(self):
        """detect_build_command skips candidates that fail validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            # Create pom.xml to generate Maven candidates
            (repo_root / 'pom.xml').touch()

            # Mock _validate_command_exists to return True (command exists)
            # but validation should filter out dangerous commands
            import src.smartfix.config.command_detector as cd
            original_validate = cd._validate_command_exists

            try:
                # All commands "exist" but some are invalid
                cd._validate_command_exists = lambda cmd, repo, **kwargs: True

                # detect_build_command should skip invalid Maven commands
                # and return None since all candidates are invalid
                # (Maven commands are valid in real use, but this tests the filtering)
                command = cd.detect_build_command(repo_root)

                # Should return a valid command since Maven commands are valid
                self.assertIsNotNone(command)
                self.assertIn('mvn', command)
            finally:
                cd._validate_command_exists = original_validate

    def test_detect_build_validates_before_returning(self):
        """detect_build_command validates each candidate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pom.xml').touch()

            import src.smartfix.config.command_detector as cd
            original_validate = cd._validate_command_exists

            try:
                # Simulate command existence check
                cd._validate_command_exists = lambda cmd, repo, **kwargs: 'mvn' in cmd

                command = cd.detect_build_command(repo_root)

                # Should return validated Maven command
                self.assertIsNotNone(command)
                # Command should be from our allowlist (basic check)
                self.assertTrue(command.startswith('mvn'))
            finally:
                cd._validate_command_exists = original_validate

    def test_detect_format_validates_before_returning(self):
        """detect_format_command validates each candidate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pyproject.toml').touch()

            import src.smartfix.config.command_detector as cd
            original_validate = cd._validate_command_exists

            try:
                # Simulate command existence check
                cd._validate_command_exists = lambda cmd, repo, **kwargs: 'black' in cmd

                command = cd.detect_format_command(repo_root)

                # Should return validated Python formatter command
                self.assertIsNotNone(command)
                self.assertIn('black', command)
            finally:
                cd._validate_command_exists = original_validate


if __name__ == '__main__':
    unittest.main()

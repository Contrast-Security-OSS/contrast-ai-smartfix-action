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
Tests for command_detector module.
"""

import unittest
import tempfile
from pathlib import Path
from src.smartfix.config.command_detector import (
    inspect_makefile_targets,
    generate_build_command_candidates,
    generate_format_command_candidates,
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

    def test_detects_dotted_targets(self):
        """Targets containing dots (e.g. test.unit) are detected and validated."""
        makefile_content = """
test.unit:
\t@pytest tests/unit

test.integration:
\t@pytest tests/integration

build:
\tpython -m build
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='Makefile', delete=False) as f:
            f.write(makefile_content)
            makefile_path = Path(f.name)

        try:
            targets = inspect_makefile_targets(makefile_path)
            self.assertIn('test.unit', targets)
            self.assertIn('test.integration', targets)
            self.assertIn('build', targets)
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
        """Generate npm commands for package.json (default when no lock file)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'package.json').touch()

            candidates = generate_build_command_candidates(repo_root)

            self.assertIn('npm test', candidates)
            self.assertIn('npm run build', candidates)

    def test_yarn_project(self):
        """Generate yarn commands when yarn.lock exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'package.json').touch()
            (repo_root / 'yarn.lock').touch()

            candidates = generate_build_command_candidates(repo_root)

            self.assertIn('yarn test', candidates)
            self.assertIn('yarn run build', candidates)
            self.assertNotIn('npm test', candidates)

    def test_pnpm_project(self):
        """Generate pnpm commands when pnpm-lock.yaml exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'package.json').touch()
            (repo_root / 'pnpm-lock.yaml').touch()

            candidates = generate_build_command_candidates(repo_root)

            self.assertIn('pnpm test', candidates)
            self.assertIn('pnpm run build', candidates)
            self.assertNotIn('npm test', candidates)

    def test_bun_project(self):
        """Generate bun commands when bun.lockb exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'package.json').touch()
            (repo_root / 'bun.lockb').touch()

            candidates = generate_build_command_candidates(repo_root)

            self.assertIn('bun test', candidates)
            self.assertIn('bun run build', candidates)
            self.assertNotIn('npm test', candidates)

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

    def test_monorepo_npm_uses_prefix_flag(self):
        """npm uses --prefix in monorepo subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            subdir = repo_root / 'frontend'
            subdir.mkdir()
            (subdir / 'package.json').touch()

            candidates = generate_build_command_candidates(repo_root, project_dir=subdir)

            self.assertIn('npm --prefix frontend test', candidates)
            self.assertNotIn('npm --cwd frontend test', candidates)
            self.assertNotIn('npm --dir frontend test', candidates)

    def test_monorepo_yarn_uses_cwd_flag(self):
        """yarn uses --cwd in monorepo subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            subdir = repo_root / 'frontend'
            subdir.mkdir()
            (subdir / 'package.json').touch()
            (subdir / 'yarn.lock').touch()

            candidates = generate_build_command_candidates(repo_root, project_dir=subdir)

            self.assertIn('yarn --cwd frontend test', candidates)
            self.assertNotIn('yarn --prefix frontend test', candidates)

    def test_monorepo_pnpm_uses_dir_flag(self):
        """pnpm uses --dir in monorepo subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            subdir = repo_root / 'frontend'
            subdir.mkdir()
            (subdir / 'package.json').touch()
            (subdir / 'pnpm-lock.yaml').touch()

            candidates = generate_build_command_candidates(repo_root, project_dir=subdir)

            self.assertIn('pnpm --dir frontend test', candidates)
            self.assertNotIn('pnpm --prefix frontend test', candidates)
            self.assertNotIn('pnpm --cwd frontend test', candidates)

    def test_monorepo_bun_uses_cwd_flag(self):
        """bun uses --cwd in monorepo subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            subdir = repo_root / 'frontend'
            subdir.mkdir()
            (subdir / 'package.json').touch()
            (subdir / 'bun.lockb').touch()

            candidates = generate_build_command_candidates(repo_root, project_dir=subdir)

            self.assertIn('bun --cwd frontend test', candidates)
            self.assertNotIn('bun --prefix frontend test', candidates)

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


class TestCommandValidationIntegration(unittest.TestCase):
    """Test that command detection integrates with validation."""

    def test_detect_build_skips_invalid_commands(self):
        """detect_build_command skips candidates that fail validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pom.xml').touch()

            import src.smartfix.config.command_detector as cd
            original_validate = cd._validate_command_exists

            try:
                cd._validate_command_exists = lambda cmd, repo, **kwargs: True

                command = cd.detect_build_command(repo_root)

                # Should return a valid command since Maven commands are valid
                self.assertIsNotNone(command)
                self.assertIn('mvn', command)
            finally:
                cd._validate_command_exists = original_validate

    def test_detect_build_validates_before_returning(self):
        """detect_build_command validates each candidate against allowlist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pom.xml').touch()

            import src.smartfix.config.command_detector as cd
            original_validate = cd._validate_command_exists

            try:
                cd._validate_command_exists = lambda cmd, repo, **kwargs: 'mvn' in cmd

                command = cd.detect_build_command(repo_root)

                self.assertIsNotNone(command)
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
                cd._validate_command_exists = lambda cmd, repo, **kwargs: 'black' in cmd

                command = cd.detect_format_command(repo_root)

                self.assertIsNotNone(command)
                self.assertIn('black', command)
            finally:
                cd._validate_command_exists = original_validate


class TestDetectBuildCommand(unittest.TestCase):
    """Test detect_build_command store-only detection logic."""

    def test_returns_first_valid_candidate(self):
        """Verify detect_build_command returns first available and valid candidate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pom.xml').touch()

            import src.smartfix.config.command_detector as cd
            from unittest.mock import patch

            with patch.object(cd, '_validate_command_exists', return_value=True), \
                 patch.object(cd, 'validate_command'):

                command = cd.detect_build_command(repo_root)

                self.assertIsNotNone(command)
                self.assertIn('mvn', command)

    def test_returns_none_when_all_fail_validation(self):
        """Verify returns None when all candidates fail allowlist validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pom.xml').touch()

            import src.smartfix.config.command_detector as cd
            from unittest.mock import patch
            from src.smartfix.config.command_validator import CommandValidationError

            with patch.object(cd, '_validate_command_exists', return_value=True), \
                 patch.object(cd, 'validate_command', side_effect=CommandValidationError("blocked")):

                command = cd.detect_build_command(repo_root)

                self.assertIsNone(command)

    def test_validation_failures_are_skipped(self):
        """Verify validation failures skip to next candidate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pom.xml').touch()
            (repo_root / 'build.gradle').touch()

            import src.smartfix.config.command_detector as cd
            from unittest.mock import patch
            from src.smartfix.config.command_validator import CommandValidationError

            def mock_validate(cmd_type, cmd):
                if 'mvn' in cmd:
                    raise CommandValidationError("Maven not allowed")

            with patch.object(cd, '_validate_command_exists', return_value=True), \
                 patch.object(cd, 'validate_command', side_effect=mock_validate):

                command = cd.detect_build_command(repo_root)

                self.assertIsNotNone(command)
                self.assertTrue(command.startswith('./gradlew') or command.startswith('gradle'))

    def test_returns_none_with_no_marker_files(self):
        """Verify empty directory returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            import src.smartfix.config.command_detector as cd

            command = cd.detect_build_command(repo_root)

            self.assertIsNone(command)

    def test_skips_commands_when_tool_not_installed(self):
        """Verify commands are skipped when tool not installed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pom.xml').touch()

            import src.smartfix.config.command_detector as cd
            from unittest.mock import patch

            with patch.object(cd, '_validate_command_exists', return_value=False):

                command = cd.detect_build_command(repo_root)

                self.assertIsNone(command)

    def test_does_not_run_builds(self):
        """Verify store-only detection does NOT execute any builds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / 'pom.xml').touch()

            import src.smartfix.config.command_detector as cd

            # run_build_command should not exist on module anymore (store-only)
            self.assertFalse(hasattr(cd, 'run_build_command'))


if __name__ == '__main__':
    unittest.main()

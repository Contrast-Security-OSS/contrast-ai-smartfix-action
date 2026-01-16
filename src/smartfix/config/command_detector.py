# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
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
Command Detector Module

Detects build and format commands from project structure using file markers
and Makefile inspection. Provides deterministic detection layer.
"""

import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


def inspect_makefile_targets(makefile_path: Path) -> List[str]:
    """
    Extract target names from a Makefile.

    Parses Makefile for targets matching pattern: ^([a-zA-Z_][a-zA-Z0-9_-]*)\\s*:
    Prioritizes common targets: test, check, build, all, default

    Args:
        makefile_path: Path to the Makefile

    Returns:
        List of target names, prioritized targets first
    """
    if not makefile_path.exists():
        return []

    priority_targets = ['test', 'check', 'build', 'all', 'default']
    found_targets = []

    try:
        with open(makefile_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Skip comments and empty lines
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue

                # Match target pattern: target:
                match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:', line)
                if match:
                    target = match.group(1)
                    found_targets.append(target)
    except (IOError, UnicodeDecodeError):
        return []

    # Sort: priority targets first, then alphabetically
    priority_found = [t for t in priority_targets if t in found_targets]
    other_targets = [t for t in found_targets if t not in priority_targets]

    return priority_found + other_targets


def generate_build_command_candidates(
    repo_root: Path,
    project_dir: Optional[Path] = None
) -> List[str]:
    """
    Generate build command candidates based on project file markers.

    Detects build system from marker files (pom.xml, build.gradle, package.json, etc.)
    and generates prioritized list of test/build commands.

    For monorepo structures, uses tool-specific directory flags instead of cd:
    - Maven: mvn -f path/to/pom.xml
    - Gradle: ./gradlew -p path/to/subdir
    - npm: npm --prefix path/to/subdir

    Args:
        repo_root: Repository root directory
        project_dir: Optional subdirectory for monorepo projects

    Returns:
        List of build command candidates, prioritized by likelihood
    """
    candidates = []
    search_dir = project_dir if project_dir else repo_root

    # Calculate relative path for monorepo commands
    rel_path = ""
    if project_dir and project_dir != repo_root:
        rel_path = str(project_dir.relative_to(repo_root))

    # Maven
    if (search_dir / 'pom.xml').exists():
        if rel_path:
            pom_path = f"{rel_path}/pom.xml"
            candidates.extend([
                f'mvn -f {pom_path} test',
                f'mvn -f {pom_path} verify',
                f'mvn -f {pom_path} clean install',
            ])
        else:
            candidates.extend([
                'mvn test',
                'mvn verify',
                'mvn clean install',
            ])

    # Gradle (prefer wrapper)
    if (search_dir / 'build.gradle').exists() or (search_dir / 'build.gradle.kts').exists():
        gradle_wrapper = (repo_root / 'gradlew').exists()
        gradle_cmd = './gradlew' if gradle_wrapper else 'gradle'

        if rel_path:
            candidates.extend([
                f'{gradle_cmd} -p {rel_path} test',
                f'{gradle_cmd} -p {rel_path} build',
                f'{gradle_cmd} -p {rel_path} check',
            ])
        else:
            candidates.extend([
                f'{gradle_cmd} test',
                f'{gradle_cmd} build',
                f'{gradle_cmd} check',
            ])

    # Python
    if (search_dir / 'pytest.ini').exists() or (search_dir / 'setup.py').exists() or \
       (search_dir / 'pyproject.toml').exists():
        candidates.extend([
            'pytest',
            'python -m pytest',
            'python setup.py test',
        ])

    # Node.js / JavaScript
    if (search_dir / 'package.json').exists():
        if rel_path:
            candidates.extend([
                f'npm --prefix {rel_path} test',
                f'npm --prefix {rel_path} run build',
                f'npm --prefix {rel_path} run test',
            ])
        else:
            candidates.extend([
                'npm test',
                'npm run build',
                'npm run test',
            ])

    # PHP
    if (search_dir / 'composer.json').exists():
        candidates.extend([
            'composer test',
            'phpunit',
            './vendor/bin/phpunit',
        ])

    # .NET
    if list(search_dir.glob('*.sln')) or list(search_dir.glob('*.csproj')):
        candidates.extend([
            'dotnet test',
            'dotnet build',
        ])

    # Makefile
    makefile_path = search_dir / 'Makefile'
    if makefile_path.exists():
        targets = inspect_makefile_targets(makefile_path)
        for target in targets:
            candidates.append(f'make {target}')

    return candidates


def generate_format_command_candidates(
    repo_root: Path,
    project_dir: Optional[Path] = None
) -> List[str]:
    """
    Generate format command candidates based on project file markers.

    Detects formatters from project structure and generates commands.

    Args:
        repo_root: Repository root directory
        project_dir: Optional subdirectory for monorepo projects

    Returns:
        List of format command candidates
    """
    candidates = []
    search_dir = project_dir if project_dir else repo_root

    # Python formatters
    if (search_dir / 'pyproject.toml').exists() or (search_dir / 'setup.py').exists():
        candidates.extend([
            'black .',
            'ruff format .',
            'autopep8 --in-place --recursive .',
        ])

    # JavaScript/TypeScript formatters
    if (search_dir / 'package.json').exists():
        candidates.extend([
            'prettier --write .',
            'npm run format',
            'yarn format',
        ])

    # Java formatters
    if (search_dir / 'pom.xml').exists():
        candidates.extend([
            'mvn spotless:apply',
            'mvn com.coveo:fmt-maven-plugin:format',
        ])

    # Gradle Java formatters
    if (search_dir / 'build.gradle').exists() or (search_dir / 'build.gradle.kts').exists():
        gradle_wrapper = (repo_root / 'gradlew').exists()
        gradle_cmd = './gradlew' if gradle_wrapper else 'gradle'
        candidates.extend([
            f'{gradle_cmd} spotlessApply',
        ])

    # .NET / C# formatters
    if list(search_dir.glob('*.sln')) or list(search_dir.glob('*.csproj')):
        candidates.extend([
            'dotnet format',
            'csharpier .',
        ])

    # PHP formatters
    if (search_dir / 'composer.json').exists():
        candidates.extend([
            'php-cs-fixer fix',
            './vendor/bin/php-cs-fixer fix',
        ])

    return candidates


def _test_command_safely(command: str, repo_root: Path, timeout: int = 30) -> Tuple[bool, str]:
    """
    Test a command safely without calling error_exit().

    This is used for detection - we want to try multiple candidates without
    terminating the program if one fails.

    Args:
        command: Command string to test
        repo_root: Directory to run command in
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, output)
    """
    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout
        )
        output = result.stdout + result.stderr
        return (result.returncode == 0, output)
    except subprocess.TimeoutExpired:
        return (False, f"Command timed out after {timeout}s")
    except FileNotFoundError:
        return (False, "Command not found")
    except Exception as e:
        return (False, f"Error running command: {str(e)}")


def detect_package_manager(repo_root: Path) -> Optional[str]:
    """
    Detect the package manager used in a Node.js project.

    Args:
        repo_root: Repository root directory

    Returns:
        Package manager name ('npm', 'yarn', 'pnpm', 'bun') or None
    """
    if (repo_root / 'package-lock.json').exists():
        return 'npm'
    if (repo_root / 'yarn.lock').exists():
        return 'yarn'
    if (repo_root / 'pnpm-lock.yaml').exists():
        return 'pnpm'
    if (repo_root / 'bun.lockb').exists():
        return 'bun'
    if (repo_root / 'package.json').exists():
        return 'npm'  # Default to npm if package.json exists
    return None


def detect_build_command(
    repo_root: Path,
    project_dir: Optional[Path] = None
) -> Optional[str]:
    """
    Detect build/test command by testing candidates.

    Generates candidates and tests each by running it. Returns first successful command.

    Args:
        repo_root: Repository root directory
        project_dir: Optional subdirectory for monorepo projects

    Returns:
        First successful build command or None
    """
    candidates = generate_build_command_candidates(repo_root, project_dir)

    for candidate in candidates:
        success, output = _test_command_safely(candidate, repo_root)
        if success:
            return candidate

    return None


def detect_format_command(
    repo_root: Path,
    project_dir: Optional[Path] = None
) -> Optional[str]:
    """
    Detect format command by testing candidates.

    Generates candidates and tests each. Returns first successful command.
    Uses non-fatal testing (doesn't error_exit on failure).

    Args:
        repo_root: Repository root directory
        project_dir: Optional subdirectory for monorepo projects

    Returns:
        First successful format command or None
    """
    candidates = generate_format_command_candidates(repo_root, project_dir)

    for candidate in candidates:
        success, output = _test_command_safely(candidate, repo_root)
        if success:
            return candidate

    return None

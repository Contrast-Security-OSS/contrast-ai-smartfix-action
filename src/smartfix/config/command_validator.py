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
Command Validation Module

Validates build and format commands against an allowlist to prevent
arbitrary command execution in GitHub Actions workflows.
"""

import re
import shlex
from typing import List, Tuple, Optional


class CommandValidationError(Exception):
    """Raised when a command fails allowlist validation."""
    pass


# Allowed executables for build and format commands
ALLOWED_COMMANDS: List[str] = [
    # .NET
    'dotnet', 'msbuild', 'nuget',
    'nunit-console', 'nunit3-console', 'xunit.console',
    'vstest.console', 'mstest',
    'csharpier',

    # Java
    'mvn', 'gradle', 'ant', 'junit', 'testng',
    './gradlew', './mvnw', 'gradlew', 'mvnw',  # Wrapper scripts
    'google-java-format', 'checkstyle',

    # Python
    'pip', 'pip3', 'python', 'python3',
    'pytest', 'nose2', 'unittest', 'coverage',
    'poetry', 'pipenv', 'uv', 'tox', 'virtualenv',
    'black', 'autopep8', 'yapf', 'isort', 'ruff',
    'flake8', 'pylint',

    # Node.js / JavaScript / TypeScript
    'npm', 'npx', 'yarn', 'node', 'pnpm', 'bun',
    'jest', 'mocha', 'jasmine', 'karma', 'ava', 'vitest', 'nyc',
    'prettier', 'eslint', 'standard',

    # PHP
    'composer', 'php', 'phpunit', 'pest', 'codeception',
    'php-cs-fixer', 'phpcbf',

    # Multi-language formatters
    'clang-format',  # Used for Java, JavaScript, Protobuf, etc.

    # Build tools
    'make', 'cmake', 'ninja', 'bazel', 'ctest',

    # Shell utilities
    'echo', 'sh', 'bash', 'grep', 'sed', 'awk', 'cat', 'tee'
]

# Allowed operators for chaining commands
ALLOWED_OPERATORS = ['&&', '||', ';', '|']

# Dangerous patterns to block
BLOCKED_PATTERNS = [
    r'\$\(',           # Command substitution $(...)
    r'`',              # Backtick command substitution
    r'\$\{',           # Variable expansion ${...}
    r'\beval\s',       # eval command
    r'\bexec\s',       # exec command
    r'\brm\s+-rf',     # Dangerous rm
    r'\bcurl.*\|',     # curl piped to interpreter
    r'\bwget.*\|',     # wget piped to interpreter
    r'>\s*/dev/',      # Writing to devices
    r';\s*rm\b',       # rm after command separator
    r'\|\s*sh\b',      # Piping to shell
    r'\|\s*bash\b',    # Piping to bash
]


def contains_dangerous_patterns(command: str) -> Optional[str]:
    """
    Check if command contains dangerous patterns.

    Args:
        command: Command string to check

    Returns:
        The matched pattern if found, None if safe
    """
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return pattern
    return None


def validate_redirect(redirect_path: str) -> bool:
    """
    Validates file redirects are safe.

    Args:
        redirect_path: Path in redirect (e.g., "build.log" from "> build.log")

    Returns:
        True if safe, False if dangerous
    """
    # Block absolute paths
    if redirect_path.startswith('/'):
        return False

    # Block parent directory traversal
    if '..' in redirect_path:
        return False

    # Block home directory expansion
    if redirect_path.startswith('~'):
        return False

    return True


def extract_redirects(segment: str) -> List[str]:
    """
    Extract file redirect paths from a command segment.

    Args:
        segment: Command segment to analyze

    Returns:
        List of redirect file paths found
    """
    redirects = []

    # Match patterns like: > file, >> file, 2> file, 2>> file
    redirect_patterns = [
        r'>\s*([^\s&|;]+)',    # > file
        r'>>\s*([^\s&|;]+)',   # >> file
        r'2>\s*([^\s&|;]+)',   # 2> file
        r'2>>\s*([^\s&|;]+)',  # 2>> file
    ]

    for pattern in redirect_patterns:
        matches = re.findall(pattern, segment)
        for match in matches:
            # Skip special redirects like 2>&1
            if not match.startswith('&'):
                redirects.append(match)

    return redirects


def validate_shell_command(executable: str, args: List[str]) -> bool:
    """
    Validates shell commands (sh/bash).
    Only allows: sh ./script.sh or bash ./script.sh
    Blocks: sh -c "command" or bash -c "..."

    Args:
        executable: The executable name
        args: List of arguments

    Returns:
        True if valid, False if invalid
    """
    if executable not in ['sh', 'bash']:
        return True  # Not a shell command

    # Must have at least one argument
    if not args:
        return False

    # Block inline execution: -c flag
    if '-c' in args:
        return False

    # First non-flag argument must be a .sh file
    script_path = next((arg for arg in args if not arg.startswith('-')), None)
    if not script_path:
        return False

    return script_path.endswith('.sh')


def parse_command_segment(segment: str) -> Tuple[str, List[str]]:
    """
    Parse command segment into executable and arguments.

    Args:
        segment: Command segment string

    Returns:
        Tuple of (executable, arguments list)
    """
    # Strip whitespace and handle empty segments
    segment = segment.strip()
    if not segment:
        return '', []

    # Remove redirects for parsing (they're validated separately)
    # This handles cases like "npm test > output.txt"
    segment_for_parsing = re.sub(r'\d*>\d*\s*[^\s&|;]+', '', segment).strip()

    try:
        # Use shlex to properly handle quoted strings and arguments
        parts = shlex.split(segment_for_parsing)
    except ValueError:
        # If shlex fails, fall back to simple split
        parts = segment_for_parsing.split()

    if not parts:
        return '', []

    executable = parts[0]
    args = parts[1:] if len(parts) > 1 else []

    return executable, args


def split_command_chain(command: str) -> List[Tuple[str, str]]:
    """
    Split command by operators, return list of (command, operator) tuples.

    Args:
        command: Full command string with potential operators

    Returns:
        List of (command_segment, operator) tuples.
        Last tuple has empty string for operator.

    Example:
        "npm install && npm test" -> [("npm install", "&&"), ("npm test", "")]
    """
    # Pattern to match operators while preserving them
    operator_pattern = '(' + '|'.join(re.escape(op) for op in ALLOWED_OPERATORS) + ')'

    # Split by operators
    parts = re.split(operator_pattern, command)

    # Group into (command, operator) pairs
    segments = []
    i = 0
    while i < len(parts):
        cmd = parts[i].strip()
        if i + 1 < len(parts) and parts[i + 1] in ALLOWED_OPERATORS:
            operator = parts[i + 1]
            i += 2
        else:
            operator = ''
            i += 1

        if cmd:  # Skip empty segments
            segments.append((cmd, operator))

    return segments


def validate_command(var_name: str, command: str) -> None:
    """
    Validates a command against the allowlist.

    Args:
        var_name: Name of the config variable (for error messages)
        command: Command string to validate

    Raises:
        CommandValidationError: If command fails validation
    """
    # Check for empty or whitespace-only commands
    if not command or not command.strip():
        raise CommandValidationError(
            f"Error: {var_name} is empty or contains only whitespace.\n"
            f"Please provide a valid build or format command."
        )

    # Handle bash line continuations (backslash-newline)
    # Replace \ followed by newline with a space
    command = re.sub(r'\\\s*\n\s*', ' ', command)

    # Check for dangerous patterns first
    dangerous_pattern = contains_dangerous_patterns(command)
    if dangerous_pattern:
        raise CommandValidationError(
            f"Error: {var_name} contains dangerous pattern: {dangerous_pattern}\n"
            f"Command: {command}\n"
            f"Security validation failed. Please remove unsafe shell operations."
        )

    # Parse and validate each command segment
    segments = split_command_chain(command)
    for segment, operator in segments:
        # Validate operator (if present)
        if operator and operator not in ALLOWED_OPERATORS:
            raise CommandValidationError(
                f"Error: {var_name} uses disallowed operator: {operator}\n"
                f"Allowed operators: {', '.join(ALLOWED_OPERATORS)}\n"
                f"Command: {command}"
            )

        # Parse command into executable and arguments
        executable, args = parse_command_segment(segment)

        if not executable:
            continue  # Skip empty segments

        # Validate executable is in allowlist
        if executable not in ALLOWED_COMMANDS:
            raise CommandValidationError(
                f"Error: {var_name} uses disallowed command: {executable}\n"
                f"Command: {command}\n"
                f"See documentation for allowed build and format commands."
            )

        # Special validation for shell commands
        if not validate_shell_command(executable, args):
            raise CommandValidationError(
                f"Error: {var_name} uses shell command incorrectly: {segment}\n"
                f"Shell commands (sh/bash) can only execute .sh files.\n"
                f"Blocked: sh -c, bash -c\n"
                f"Allowed: sh ./build.sh"
            )

        # Validate redirects if present
        redirects = extract_redirects(segment)
        for redirect_path in redirects:
            if not validate_redirect(redirect_path):
                raise CommandValidationError(
                    f"Error: {var_name} contains unsafe file redirect: {redirect_path}\n"
                    f"Redirects must be to relative paths without '..' traversal.\n"
                    f"Command: {command}"
                )

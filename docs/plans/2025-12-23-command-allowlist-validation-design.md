# Command Allowlist Validation Design

**JIRA**: AIML-337
**Date**: 2025-12-23
**Status**: Approved for Implementation

## Problem Statement

SmartFix currently accepts arbitrary bash commands via `BUILD_COMMAND` and `FORMATTING_COMMAND` environment variables and executes them with `shell=True` in subprocess calls. This creates a security risk in GitHub Actions workflows where malicious or misconfigured commands could be executed.

**Vulnerable Code Locations:**
- `src/smartfix/domains/workflow/build_runner.py:54` - Uses `shell=True` with raw command
- `src/smartfix/domains/workflow/formatter.py:56` - Executes split command without validation
- `src/config.py:82,84` - Reads commands from environment without validation

## Solution Overview

Implement command allowlist validation in the Config class initialization to fail fast with clear error messages when commands don't meet security requirements.

**Validation Strategy**: Moderate strictness
- Allow executables from comprehensive allowlist
- Allow safe chaining operators (`&&`, `||`, `;`, `|`)
- Allow redirects to relative paths only
- Block dangerous patterns and operations
- Parse chained commands and validate each segment

## Architecture

### Component Structure

```
src/smartfix/config/
├── __init__.py
└── command_validator.py  (NEW)
    ├── ALLOWED_COMMANDS
    ├── BLOCKED_PATTERNS
    ├── validate_command()
    ├── split_command_chain()
    ├── parse_command_segment()
    ├── validate_shell_command()
    ├── validate_redirect()
    ├── contains_dangerous_patterns()
    ├── extract_redirects()
    └── CommandValidationError
```

### Allowlist

Commands allowed for execution:

**Java Ecosystem:**
- Build: `mvn`, `gradle`, `ant`, `./gradlew`, `./mvnw`, `gradlew`, `mvnw`
- Test: `junit`, `testng`
- Format: `google-java-format`, `checkstyle`

**.NET Ecosystem:**
- Build: `dotnet`, `msbuild`, `nuget`
- Test: `nunit-console`, `nunit3-console`, `xunit.console`, `vstest.console`, `mstest`
- Format: `csharpier`

**Python Ecosystem:**
- Runtime: `pip`, `pip3`, `python`, `python3`
- Package: `poetry`, `pipenv`, `uv`, `tox`, `virtualenv`
- Test: `pytest`, `nose2`, `unittest`, `coverage`
- Format: `black`, `autopep8`, `yapf`, `isort`, `ruff`
- Lint: `flake8`, `pylint`

**Node.js Ecosystem:**
- Package: `npm`, `npx`, `yarn`, `pnpm`, `bun`, `node`
- Test: `jest`, `mocha`, `jasmine`, `karma`, `ava`, `vitest`, `nyc`
- Format: `prettier`, `eslint`, `standard`

**PHP Ecosystem:**
- Build: `composer`, `php`
- Test: `phpunit`, `pest`, `codeception`
- Format: `php-cs-fixer`, `phpcbf`

**Build Tools:**
- `make`, `cmake`, `ninja`, `bazel`, `ctest`

**Multi-language:**
- `clang-format`

**Shell Utilities:**
- `echo`, `sh`, `bash` (with restrictions)

### Validation Rules

**1. Executable Validation**
- Command must start with executable in allowlist
- Reject any command starting with unlisted executable

**2. Shell Command Validation**
- `sh`/`bash` can only execute `.sh` files
- Block: `sh -c "..."` or `bash -c "..."`
- Allow: `sh ./build.sh` or `bash ./scripts/test.sh`

**3. Redirect Validation**
- Allow: `> build.log`, `>> output.txt`, `2>&1`, `2> error.log`
- Block: `> /etc/passwd`, `> ../../../etc/hosts`, `> ~/secrets.txt`
- Rule: Must be relative path without `..` traversal or absolute paths

**4. Operator Validation**
- Allow: `&&`, `||`, `;`, `|`
- Each command segment validated independently

**5. Dangerous Pattern Detection**

Blocked patterns:
- `$(...)` - Command substitution
- Backticks - Command substitution
- `${...}` - Variable expansion
- `eval` - Dynamic code execution
- `exec` - Command execution
- `rm -rf` - Dangerous file deletion
- `curl ... |` - Piping to interpreter
- `wget ... |` - Piping to interpreter
- `> /dev/` - Writing to devices
- `; rm` - rm after command separator
- `| sh` / `| bash` - Piping to shell

## Error Handling

### CommandValidationError Exception

Custom exception that inherits from `ConfigurationError` with detailed error messages:

**Example error messages:**

```
Error: BUILD_COMMAND contains dangerous pattern: \$\(
Command: npm install && echo $(whoami)
Security validation failed. Please remove unsafe shell operations.
```

```
Error: FORMATTING_COMMAND uses disallowed command: wget
Command: wget https://example.com/format.sh && bash format.sh
See documentation for allowed build and format commands.
```

```
Error: BUILD_COMMAND uses shell command incorrectly: bash -c "make build"
Shell commands (sh/bash) can only execute .sh files.
Blocked: sh -c, bash -c
Allowed: sh ./build.sh
```

### Integration Point

```python
# In Config.__init__() after reading commands
self.BUILD_COMMAND = self._get_env_var("BUILD_COMMAND", required=is_build_command_required)
if self.BUILD_COMMAND:
    self._validate_command("BUILD_COMMAND", self.BUILD_COMMAND)

self.FORMATTING_COMMAND = self._get_env_var("FORMATTING_COMMAND", required=False)
if self.FORMATTING_COMMAND:
    self._validate_command("FORMATTING_COMMAND", self.FORMATTING_COMMAND)
```

## Testing Strategy

**Test Coverage Areas:**

1. Allowlist validation - Each allowed command validates successfully
2. Blocked commands - Disallowed executables rejected
3. Chained commands - Multiple commands with operators validate
4. Shell scripts - `sh`/`bash` with `.sh` files allowed, `-c` blocked
5. Redirects - Safe redirects pass, dangerous fail
6. Dangerous patterns - Command substitution, eval, etc. blocked
7. Edge cases - Empty commands, whitespace, complex chains

**Test File**: `test/test_command_validation.py`

## Implementation Tasks

Created as beads in `.beads/`:

1. **contrast-ai-smartfix-action-gad** (P1) - Create command validation module
2. **contrast-ai-smartfix-action-8re** (P1) - Integrate validation into Config class
3. **contrast-ai-smartfix-action-q9y** (P2) - Create comprehensive test suite
4. **contrast-ai-smartfix-action-wuv** (P3) - Update documentation

**Dependencies:**
- Task 2 depends on Task 1
- Task 3 depends on Tasks 1 & 2
- Task 4 depends on Task 3

**Work Order** (from robot planner):
- Start with: `contrast-ai-smartfix-action-gad` (highest impact, unblocks 1 task)
- Total actionable: 1
- Total blocked: 3

## Security Considerations

**Defense in Depth:**
- Validation happens early (config initialization)
- Fail-fast with clear error messages
- No bypass mechanisms
- Comprehensive pattern detection

**Future Enhancements:**
- Telemetry tracking of validated commands
- Configurable allowlist extensions
- Deprecation warnings for legacy build tools

## Documentation Updates

**README.md additions:**
- Command allowlist section
- Examples of valid/invalid commands per language
- Error message troubleshooting

**security.md additions:**
- Command validation security feature
- Rationale for security controls

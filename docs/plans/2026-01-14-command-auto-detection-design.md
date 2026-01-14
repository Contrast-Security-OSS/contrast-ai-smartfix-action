# Command Auto-Detection Design

**JIRA**: AIML-30
**Date**: 2026-01-14
**Status**: Approved for Implementation

## Problem Statement

SmartFix currently requires users to manually configure `BUILD_COMMAND` and `FORMATTING_COMMAND` via environment variables. This creates a barrier to adoption and leads to workarounds when the AI can identify the build system but is blocked from using it.

**Real-world example:** During testing on a Gradle application (Genie app), the AI correctly identified Gradle as the build system but was blocked from using it. The AI then attempted workarounds like creating `build.sh` scripts, documented at: https://contrast.atlassian.net/wiki/spaces/CL/pages/4183687204/Auto+Remediation+Testing

**Core issue:** If SmartFix can't determine valid build commands, it cannot ensure high-quality PRs that don't break the build. The system must fail fast with clear guidance rather than proceed without build verification.

## Solution Overview

Implement a hybrid command detection system that:
1. **Fast path:** Uses deterministic file scanning and simple mappings for common cases (80% of projects)
2. **Smart fallback:** Uses LLM agent with iteration and error feedback for complex cases (monorepos, custom configurations)
3. **Integration point:** Runs during `Config.__init__()` before any remediation work begins
4. **Validation:** All detected commands pass through existing `command_validator.py` allowlist validation
5. **Testing:** Executes detected commands to verify they work (exit code 0)

## Architecture

### Component Structure

```
src/smartfix/config/
├── __init__.py
├── command_validator.py (EXISTING)
└── command_detector.py (NEW)
    ├── scan_for_build_files()
    ├── get_simple_command_mapping()
    ├── validate_and_test_command()
    └── detect_build_command()

src/smartfix/domains/agents/
├── command_detection_agent.py (NEW)
│   └── CommandDetectionAgent class
└── prompts/
    └── command_detection_system_prompt.txt (NEW)

Config.__init__()
└── _auto_detect_build_command() (NEW method)
```

### Two-Layer Architecture

**Layer 1: Deterministic Detection (command_detector.py)**
- Scans repository for build system marker files
- Maps files to standard commands (e.g., `pom.xml` → `mvn clean install`)
- Validates detected command against allowlist
- Tests command execution (dry run for exit code 0)
- Falls back to Layer 2 for complex cases

**Layer 2: LLM Agent (CommandDetectionAgent)**
- Full ADK agent with MCP filesystem tools
- Reads and analyzes build file contents
- Handles monorepos using tool-specific directory flags
- Iterates on build failures with error feedback (max 6 attempts)
- Follows existing QA subagent pattern

## Detailed Design

### Integration with Config Initialization

```python
# In Config.__init__() (after line 82-85)
self.BUILD_COMMAND = self._get_env_var("BUILD_COMMAND", required=False)
if not self.BUILD_COMMAND and is_build_command_required:
    self.BUILD_COMMAND = self._auto_detect_build_command()
if not self.BUILD_COMMAND and is_build_command_required:
    raise ConfigurationError(
        "Could not auto-detect build command. Please set BUILD_COMMAND manually.\n"
        f"Found these build files: {detected_files}"
    )

# Validate the detected command
if self.BUILD_COMMAND:
    self._validate_command("BUILD_COMMAND", self.BUILD_COMMAND)

# Same logic for FORMATTING_COMMAND (optional)
```

### Deterministic Layer (command_detector.py)

**Supported Build System Markers:**

| Language | Marker Files |
|----------|-------------|
| Java | `pom.xml`, `build.gradle`, `build.gradle.kts`, `gradlew`, `mvnw` |
| .NET | `*.csproj`, `*.sln`, `*.fsproj`, `Directory.Build.props` |
| Python | `setup.py`, `pyproject.toml`, `requirements.txt`, `poetry.lock`, `Pipfile` |
| Node.js | `package.json`, `yarn.lock`, `pnpm-lock.yaml`, `bun.lockb` |
| PHP | `composer.json`, `composer.lock` |
| Go | `go.mod`, `Makefile` (Go-specific patterns) |

**Simple Command Mappings:**

```python
SIMPLE_MAPPINGS = {
    'pom.xml': 'mvn clean install',
    'build.gradle': './gradlew build',
    'build.gradle.kts': './gradlew build',
    'package.json': 'npm test',  # Or read scripts section
    '*.csproj': 'dotnet build',
    '*.sln': 'dotnet build',
    'composer.json': 'composer install && composer test',
    'pyproject.toml': 'python -m pytest',
    'go.mod': 'go test ./...',
}
```

**Validation & Testing Flow:**

```python
def detect_build_command(repo_root: Path, remediation_id: str) -> Optional[str]:
    # Step 1: Scan for build files
    build_files = scan_for_build_files(repo_root)

    if not build_files:
        return None  # No build files found

    # Step 2: Try simple mapping
    simple_command = get_simple_command_mapping(build_files)
    if simple_command:
        # Step 3: Validate command
        try:
            from src.smartfix.config.command_validator import validate_command
            validate_command("BUILD_COMMAND", simple_command)

            # Step 4: Test execution
            from src.smartfix.domains.workflow.build_runner import run_build_command
            success, output = run_build_command(simple_command, repo_root, remediation_id)
            if success:
                return simple_command
        except Exception:
            pass  # Fall through to LLM agent

    # Step 5: Fall back to LLM agent
    from src.smartfix.domains.agents.command_detection_agent import CommandDetectionAgent
    agent = CommandDetectionAgent()
    return agent.detect(repo_root, build_files, remediation_id)
```

### LLM Agent Layer (CommandDetectionAgent)

**Agent Structure:**

```python
class CommandDetectionAgent:
    """
    LLM-powered agent for detecting build commands in complex scenarios.
    Uses SubAgentExecutor with ADK and MCP filesystem tools.
    """

    def __init__(self):
        """Initialize with SubAgentExecutor."""
        self.executor = SubAgentExecutor()

    def detect(
        self,
        repo_root: Path,
        build_files: Dict[str, List[Path]],
        remediation_id: str,
        max_attempts: int = None
    ) -> Optional[str]:
        """
        Detects build command using LLM reasoning.

        Args:
            repo_root: Repository root directory
            build_files: Pre-scanned build files from deterministic layer
            remediation_id: For error tracking and telemetry
            max_attempts: Maximum detection iterations (from config)

        Returns:
            Valid build command string, or None if detection fails
        """
```

**System Prompt (stored locally):**

Location: `src/smartfix/domains/agents/prompts/command_detection_system_prompt.txt`

Content structure (B/C Hybrid):
```
# Role
You are a build system detection specialist for SmartFix, Contrast Security's
AI-powered vulnerability remediation system.

# Supported Languages
- Java (Maven, Gradle, Ant)
- .NET (MSBuild, dotnet CLI)
- Python (pip, pytest, poetry, tox)
- Node.js (npm, yarn, pnpm, bun)
- PHP (Composer, PHPUnit)
- Go (go test, go build)

# Allowed Commands
Your suggestions must use only these allowed executables:
[Full ALLOWED_COMMANDS list from command_validator.py]

# Task
Analyze the repository structure and build files to determine the correct
build command. Consider:
1. Which build system is in use
2. Project structure (single module vs monorepo)
3. Standard commands for each build system
4. Custom configurations in build files

# Monorepo Handling
For monorepos with multiple subprojects, use tool-specific directory flags:
- Maven: `mvn -f backend/pom.xml clean install`
- Gradle: `./gradlew -p backend build`
- npm: `npm --prefix frontend test`
- dotnet: `dotnet build backend/project.csproj`

DO NOT use `cd` commands - they are not in the allowlist.

# Iteration Strategy
If a command fails to execute:
1. Analyze the build error output
2. Review your previous attempts to avoid repeating failures
3. Suggest an improved command based on the error
4. Consider alternative tasks (e.g., `test` instead of `build`)
5. Add necessary flags (e.g., `--no-daemon` for Gradle)

# Output Format
Return a JSON object:
{
  "build_command": "string (required)",
  "format_command": "string (optional)",
  "confidence": "high|medium|low",
  "reasoning": "brief explanation"
}

# Examples
[Include 5-10 example scenarios with expected outputs]
```

**Iteration Loop:**

```python
# Iteration 1: Initial attempt
user_prompt = f"""
Detected build files:
{format_build_files(build_files)}

Repository structure:
{get_repo_structure(repo_root)}

Suggest a valid build command for this project.
"""

# Iteration 2+: Feedback loop
user_prompt = f"""
Previous attempt #{attempt}: {previous_command}
Build result: FAILED (exit code {exit_code})

Build errors (clipped):
{extract_build_errors(build_output)}

Previous attempts history:
{format_attempt_history(attempts)}

Analyze the error and suggest an improved build command.
Avoid repeating failed approaches.
"""
```

### Configuration

New config setting:

```python
# In Config.__init__()
self.MAX_COMMAND_DETECTION_ATTEMPTS = self._get_validated_int(
    "MAX_COMMAND_DETECTION_ATTEMPTS",
    default=6,
    min_val=0,
    max_val=10
)
```

Environment variable: `MAX_COMMAND_DETECTION_ATTEMPTS` (optional, default=6)

## Error Handling

### Error Scenarios

**1. No build files found:**
```
ConfigurationError:
"Could not find any build files in repository.
Searched for: pom.xml, build.gradle, package.json, composer.json, *.csproj, go.mod, pyproject.toml
Supported languages: Java, .NET, Python, Node.js, PHP, Go
Please set BUILD_COMMAND manually."
```

**2. Max iterations exceeded:**
```
ConfigurationError:
"Could not detect valid build command after 6 attempts.
Last attempt: ./gradlew build
Last error: Task 'build' not found in root project.
Suggestion: Try setting BUILD_COMMAND to: ./gradlew test"
```

**3. Agent execution failure:**
```
ConfigurationError:
"Build command detection agent failed: {error_details}
Please set BUILD_COMMAND manually."
```

**4. Validation failure:**
```
ConfigurationError:
"Auto-detected command failed validation: {validation_error}
Detected command: {command}
Please set BUILD_COMMAND manually with an allowed command."
```

### Fail-Fast Principle

All errors exit SmartFix immediately during config initialization. This prevents:
- Running Fix agent without build verification capability
- Creating PRs that might break the build
- Wasting LLM credits on doomed remediation attempts

## Data Flow

```
Config.__init__()
    ↓
Is BUILD_COMMAND set? → YES → Validate → Done
    ↓ NO
_auto_detect_build_command()
    ↓
command_detector.scan_for_build_files(repo_root)
    ↓
Found build files? → NO → ConfigurationError (exit)
    ↓ YES
command_detector.get_simple_command_mapping(build_files)
    ↓
Simple mapping found? → YES → Validate & Test → Success? → YES → Return command
    ↓ NO                                              ↓ NO
    ↓                                                 ↓
CommandDetectionAgent.detect()
    ↓
Create ADK agent with MCP tools + system prompt
    ↓
SubAgentExecutor.create_agent() + execute_agent()
    ↓
Iteration Loop (max 6 attempts):
  1. Agent reads build files via MCP tools
  2. Agent suggests command based on analysis
  3. command_validator.validate_command() - Check allowlist
  4. build_runner.run_build_command() - Test execution
  5. Success? → Return command
  6. Failure? → extract_build_errors() → feedback to agent
  7. Repeat until success or max iterations
    ↓
Max iterations exceeded? → ConfigurationError (exit)
    ↓
Return detected command
    ↓
Config validates with command_validator
    ↓
Config initialization complete with valid BUILD_COMMAND
```

## Reused Components

**Existing infrastructure leveraged:**

1. **command_validator.py** - Validate all detected commands against allowlist
2. **build_runner.py** - Test detected commands for execution
3. **build_output_analyzer.extract_build_errors()** - Clip error feedback for agent
4. **SubAgentExecutor** - Agent lifecycle management (create, execute, cleanup)
5. **MCP tools** - Same filesystem tools used by Fix/QA agents
6. **Config validation patterns** - Follow existing `_validate_command()` pattern
7. **Telemetry tracking** - Integrate with existing telemetry_handler

## Testing Strategy

**Test File:** `test/test_command_detection.py`

### Test Coverage Areas

**1. Deterministic Layer Tests:**
- `test_scan_finds_maven_files()` - Detects pom.xml
- `test_scan_finds_gradle_files()` - Detects build.gradle and build.gradle.kts
- `test_scan_finds_npm_files()` - Detects package.json
- `test_scan_finds_dotnet_files()` - Detects *.csproj and *.sln
- `test_scan_finds_python_files()` - Detects pyproject.toml, setup.py
- `test_scan_finds_php_files()` - Detects composer.json
- `test_scan_finds_go_files()` - Detects go.mod
- `test_simple_mapping_maven()` - pom.xml → `mvn clean install`
- `test_simple_mapping_gradle()` - build.gradle → `./gradlew build`
- `test_simple_mapping_npm()` - package.json → `npm test`
- `test_simple_mapping_validation_failure()` - Detected command fails allowlist
- `test_simple_mapping_execution_failure()` - Detected command fails to run

**2. LLM Agent Tests (mocked SubAgentExecutor):**
- `test_agent_detects_monorepo_maven()` - Suggests `mvn -f backend/pom.xml clean install`
- `test_agent_detects_monorepo_gradle()` - Suggests `./gradlew -p backend build`
- `test_agent_iterates_on_build_failure()` - Uses error feedback to improve
- `test_agent_respects_max_iterations()` - Stops after MAX_COMMAND_DETECTION_ATTEMPTS
- `test_agent_validates_suggested_commands()` - Only returns allowed commands
- `test_agent_avoids_ping_pong()` - Doesn't repeat failed attempts
- `test_agent_reads_package_json_scripts()` - Analyzes custom npm scripts
- `test_agent_handles_custom_gradle_tasks()` - Non-standard task names

**3. Config Integration Tests:**
- `test_config_auto_detects_when_missing()` - BUILD_COMMAND auto-detected
- `test_config_prefers_explicit_over_detection()` - Manual config takes precedence
- `test_config_fails_when_no_build_files()` - Clear error message
- `test_config_fails_after_max_iterations()` - Clear error with suggestions
- `test_format_command_detection()` - FORMATTING_COMMAND also detected (optional)
- `test_config_validates_detected_command()` - Runs through command_validator

**4. Edge Case Tests:**
- `test_monorepo_java_and_nodejs()` - Mixed Java backend + Node.js frontend
- `test_monorepo_multiple_maven_modules()` - Multiple pom.xml files
- `test_python_with_multiple_test_frameworks()` - pytest vs unittest
- `test_gradle_wrapper_not_executable()` - Falls back to `gradle` command
- `test_npm_with_no_test_script()` - Handles missing package.json scripts
- `test_empty_repository()` - No files found

**Test Utilities:**
- Reuse `test_helpers.build_patches` for mocking
- Mock SubAgentExecutor responses
- Mock build_runner execution
- Fixture repositories with various build file combinations

## Telemetry

**New telemetry fields:**

```python
# Add to telemetry_handler
telemetry_handler.update_telemetry("configInfo.buildCommandAutoDetected", True/False)
telemetry_handler.update_telemetry("configInfo.commandDetectionAttempts", N)
telemetry_handler.update_telemetry("configInfo.commandDetectionMethod", "simple_mapping" | "llm_agent")
telemetry_handler.update_telemetry("configInfo.detectedBuildFiles", List[str])
```

## Implementation Tasks

Tasks will be created as beads in `.beads/`:

**P1 - Core Detection Logic:**
1. Create `command_detector.py` with deterministic layer
2. Create `CommandDetectionAgent` class following QA agent pattern
3. Create system prompt for detection agent
4. Integrate into `Config.__init__()`

**P1 - Configuration & Validation:**
5. Add `MAX_COMMAND_DETECTION_ATTEMPTS` config setting
6. Integrate with `command_validator.py`
7. Add error handling and clear error messages

**P2 - Testing:**
8. Create comprehensive test suite for deterministic layer
9. Create test suite for LLM agent (mocked)
10. Create config integration tests
11. Create edge case tests for monorepos

**P3 - Documentation:**
12. Update README.md with auto-detection feature
13. Document supported build systems and marker files
14. Add troubleshooting guide for detection failures

**Dependencies:**
- Task 2 depends on Task 1 (agent uses detector)
- Task 4 depends on Tasks 1, 2, 3 (integration requires all components)
- Task 7 depends on Tasks 1-6 (error handling needs all paths)
- Tasks 8-11 depend on Tasks 1-7 (testing requires implementation)
- Task 12-14 depend on Task 11 (docs after testing)

## Security Considerations

**Command Validation:**
- All detected commands pass through `command_validator.py` allowlist
- No arbitrary command execution possible
- Agent cannot suggest commands outside allowlist

**Monorepo Safety:**
- Uses tool-specific directory flags (`-f`, `-p`, `--prefix`)
- Does NOT use `cd` command (not in allowlist)
- Paths validated to stay within repository

**Iteration Safety:**
- Max attempts limit prevents infinite loops
- Build output clipped to prevent log injection
- Agent session properly cleaned up on failure

## Future Enhancements

**Phase 2 (potential future work):**
1. Add `cd` to allowlist with path validation (no traversal, no absolute paths)
2. Support `BUILD_WORKING_DIR` config separate from command
3. Cache detected commands per repository
4. Learn from successful detections (telemetry analysis)
5. Support custom build file locations via config
6. Detect format commands in addition to build commands

## References

- Related design: `docs/plans/2025-12-23-command-allowlist-validation-design.md` (AIML-337)
- QA agent implementation: `src/smartfix/domains/agents/smartfix_agent.py` lines 463-522
- SubAgentExecutor: `src/smartfix/domains/agents/sub_agent_executor.py`
- Build runner: `src/smartfix/domains/workflow/build_runner.py`
- Genie app test case: https://contrast.atlassian.net/wiki/spaces/CL/pages/4183687204/Auto+Remediation+Testing

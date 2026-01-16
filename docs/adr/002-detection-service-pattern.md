# ADR-002: DetectionService Pattern to Prevent Circular Dependencies

**Status**: Accepted
**Date**: 2026-01-16
**Related Beads**: ogb, yup, ec6, 9tk

## Context

The design doc proposes Config.__init__() calling a method `_auto_detect_build_command()` on the Config class. This creates tight coupling and potential circular dependency risks:

```
Config.__init__()
  → Config._auto_detect_build_command() (method on Config)
    → CommandDetectionAgent.detect()
      → build_runner.run_build_command()
      → command_validator.validate_command()
```

If any of these modules later need Config settings, we get circular imports.

## Current State Analysis

**Good news**: No circular dependency exists yet
- `command_validator.py` imports: `re, shlex, typing` (no Config)
- `build_runner.py` imports: `subprocess, pathlib, src.utils, telemetry_handler` (no Config)
- `CommandDetectionAgent` imports: `pathlib` only (stub phase)

**Risk**: The design proposes adding `_auto_detect_build_command()` as a Config method, which tightly couples detection logic to Config class.

## Decision

**Use DetectionService pattern with dependency injection** to keep concerns separated and prevent circular dependencies.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Config.__init__() (src/config.py)                           │
│ - Minimal logic                                              │
│ - Calls external detection service                           │
│ - No detection implementation details                        │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ Calls
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ DetectionService (src/smartfix/config/detection_service.py) │
│ - Orchestrates two-layer detection                          │
│ - No dependency on Config                                    │
│ - Pure functions                                             │
└──────────────┬────────────────┬─────────────────────────────┘
               │                │
      Layer 1  │                │ Layer 2
               ▼                ▼
┌──────────────────┐  ┌────────────────────────────┐
│ command_detector │  │ CommandDetectionAgent       │
│ (deterministic)  │  │ (LLM-based)                 │
└──────────────────┘  └────────────────────────────┘
```

### Implementation

```python
# src/smartfix/config/detection_service.py (NEW)
"""
Command Detection Service

Orchestrates command detection using deterministic and AI layers.
No dependencies on Config class to prevent circular imports.
"""

from pathlib import Path

def detect_build_command(
    repo_root: Path,
    remediation_id: str = "config-init",
    max_attempts: int = 6
) -> str | None:
    """
    Detect build command using two-layer approach.

    This function has NO dependency on Config class.
    All settings are passed as parameters.

    Args:
        repo_root: Repository root directory
        remediation_id: For error tracking
        max_attempts: Max LLM detection attempts

    Returns:
        Detected command string or None
    """
    from .command_detector import detect_build_command as detect_deterministic
    from ..domains.agents.command_detection_agent import detect_command_with_agent

    # Layer 1: Try deterministic detection (fast, covers 80% of cases)
    command = detect_deterministic(repo_root)
    if command:
        return command

    # Layer 2: Fall back to LLM agent (handles complex cases)
    build_files = scan_for_build_files(repo_root)
    if not build_files:
        return None

    command = detect_command_with_agent(
        repo_root=repo_root,
        build_files=build_files,
        failed_attempts=[],
        remediation_id=remediation_id,
        max_attempts=max_attempts
    )

    return command

def scan_for_build_files(repo_root: Path) -> list[str]:
    """Scan for build system marker files."""
    # Implementation here
    pass
```

```python
# src/smartfix/domains/agents/command_detection_agent.py (UPDATED)
"""
Command Detection Agent

NO dependency on Config class.
All configuration passed via parameters or constructor injection.
"""

def detect_command_with_agent(
    repo_root: Path,
    build_files: list[str],
    failed_attempts: list[dict[str, str]],
    remediation_id: str,
    max_attempts: int = 6
) -> str | None:
    """
    Public function for command detection using LLM agent.

    No Config dependency - all settings passed as parameters.
    """
    agent = CommandDetectionAgent(
        repo_root=repo_root,
        max_attempts=max_attempts
    )
    return agent.detect(build_files, failed_attempts, remediation_id)

class CommandDetectionAgent:
    """
    Agent uses dependency injection for all external dependencies.
    No direct imports of Config.
    """

    def __init__(
        self,
        repo_root: Path,
        project_dir: Path | None = None,
        max_attempts: int = 6
    ) -> None:
        self.repo_root = repo_root
        self.project_dir = project_dir
        self.max_attempts = max_attempts

    def detect(
        self,
        build_files: list[str],
        failed_attempts: list[dict[str, str]],
        remediation_id: str
    ) -> str | None:
        """Sync wrapper - no Config dependency."""
        from ..agents.event_loop_utils import _run_agent_in_event_loop
        return _run_agent_in_event_loop(
            self.detect_async,
            build_files,
            failed_attempts,
            remediation_id
        )

    async def detect_async(
        self,
        build_files: list[str],
        failed_attempts: list[dict[str, str]],
        remediation_id: str
    ) -> str | None:
        """Async implementation - no Config dependency."""
        # Uses injected repo_root, max_attempts from __init__
        # Uses passed parameters for build_files, remediation_id
        pass
```

```python
# src/config.py (UPDATED)
class Config:
    def __init__(self, env=None, testing=False):
        # ... existing code ...

        # Auto-detect build command if not provided
        is_build_command_required = self.RUN_TASK == "generate_fix" and is_smartfix_coding_agent

        if not testing:
            self.BUILD_COMMAND = self._get_env_var("BUILD_COMMAND", required=False)

            # Call EXTERNAL service, not a method on Config
            if not self.BUILD_COMMAND and is_build_command_required:
                from src.smartfix.config.detection_service import detect_build_command

                self.BUILD_COMMAND = detect_build_command(
                    repo_root=Path(self.REPO_ROOT),
                    remediation_id="config-init",
                    max_attempts=6  # Could come from env var MAX_COMMAND_DETECTION_ATTEMPTS
                )

            if not self.BUILD_COMMAND and is_build_command_required:
                raise ConfigurationError(
                    "Could not auto-detect build command. "
                    "Please set BUILD_COMMAND environment variable."
                )

            # Validate the detected or provided command
            if self.BUILD_COMMAND:
                self._validate_command("BUILD_COMMAND", self.BUILD_COMMAND)
```

## Dependency Graph

### BEFORE (Risky - tight coupling)
```
Config (class with _auto_detect_build_command method)
  ↓
CommandDetectionAgent
  ↓
build_runner, command_validator
  ↓ (future risk)
Config (circular!)
```

### AFTER (Safe - loose coupling)
```
Config
  ↓
detection_service (pure functions, no Config dependency)
  ↓
command_detector (deterministic)
  ↓
command_validator (no Config)

detection_service
  ↓
CommandDetectionAgent (with dependency injection)
  ↓
build_runner, command_validator (no Config)
```

## Alternatives Considered

### Option 1: Keep _auto_detect_build_command() on Config
**Rejected**: Tight coupling, violates single responsibility, makes testing harder

### Option 2: Import Config in detection modules
**Rejected**: Creates circular dependency risk

### Option 3: Pass Config instance to detection functions
**Rejected**: Couples detection to Config structure, makes testing require full Config mock

### Option 4: Global config singleton
**Rejected**: Hidden dependencies, hard to test, anti-pattern

## Consequences

### Positive

✅ **No circular dependencies**: Clean import hierarchy
✅ **Loose coupling**: Detection modules don't know about Config
✅ **Testability**: Can test detection without full Config setup
✅ **Dependency injection**: All dependencies explicit
✅ **Single Responsibility**: Config handles config, DetectionService handles detection
✅ **Reusability**: DetectionService can be used outside Config context

### Negative

⚠️ **More files**: Need detection_service.py module
⚠️ **Parameter passing**: Settings passed as parameters, not pulled from Config

### Neutral

- Follows clean architecture dependency rule (dependencies point inward)
- Matches existing pattern (build_runner, command_validator don't import Config)

## Testing Strategy

```python
# test/test_detection_service.py
def test_detect_build_command_deterministic_success(tmp_path):
    """Test deterministic layer succeeds."""
    (tmp_path / "pom.xml").touch()
    result = detect_build_command(tmp_path)
    assert result == "mvn test"

def test_detect_build_command_falls_back_to_llm(tmp_path, mocker):
    """Test fallback to LLM layer."""
    # Mock deterministic failure
    mocker.patch('...detect_deterministic', return_value=None)
    # Mock LLM success
    mocker.patch('...detect_command_with_agent', return_value="gradle test")

    result = detect_build_command(tmp_path)
    assert result == "gradle test"

def test_detect_build_command_no_config_dependency():
    """Verify no Config import in detection modules."""
    import src.smartfix.config.detection_service as ds
    import src.smartfix.domains.agents.command_detection_agent as agent

    # Neither module should import Config
    assert 'Config' not in dir(ds)
    assert 'get_config' not in dir(ds)
    assert 'Config' not in dir(agent)
```

## Implementation Plan

### Phase 1: Create DetectionService (new bead or part of yup)

1. Create `src/smartfix/config/detection_service.py`
2. Implement `detect_build_command()` function
3. Implement `scan_for_build_files()` helper
4. Add tests for detection_service.py

### Phase 2: Update CommandDetectionAgent (amendment to 73f or new bead)

1. Remove any Config imports/dependencies
2. Add `detect_command_with_agent()` public function
3. Ensure all settings come from parameters
4. Update tests to verify no Config dependency

### Phase 3: Config Integration (beads-yup)

1. Import `detection_service.detect_build_command` in Config.__init__()
2. Call with explicit parameters (repo_root, max_attempts)
3. Remove any `_auto_detect_build_command()` method on Config
4. Add integration tests

### Phase 4: Verification

1. Run import cycle checker: `python -m pytest --import-mode=importlib`
2. Verify no circular imports
3. Test Config initialization with detection
4. Document dependency graph

## References

- Design doc: `docs/plans/2026-01-14-command-auto-detection-design.md:66`
- command_validator: `src/smartfix/config/command_validator.py` (no Config import)
- build_runner: `src/smartfix/domains/workflow/build_runner.py` (no Config import)
- CommandDetectionAgent: `src/smartfix/domains/agents/command_detection_agent.py`

## Approval

Approved by: Architectural review for beads-ogb
Implements: Circular dependency prevention
Unblocks: beads-yup (Config integration)
Complements: ADR-001 (async/sync pattern)

# ADR-001: Async/Sync Pattern for CommandDetectionAgent

**Status**: Accepted
**Date**: 2026-01-16
**Related Beads**: g0g, 7nf, yup, 73f

## Context

CommandDetectionAgent needs to integrate with SubAgentExecutor (fully async) while being callable from Config.__init__() (synchronous). This creates an async/sync integration challenge.

## Analysis

### Current Architecture Patterns

The codebase already solves this problem for Fix and QA agents:

**Pattern**: Sync wrapper → Event loop bridge → Async implementation

```python
# 1. Public sync method (smartfix_agent.py:463)
def _run_qa_agent(self, context, build_output, changed_files):
    qa_summary = _run_agent_in_event_loop(  # Sync wrapper
        _run_agent_internal_with_prompts,    # Async coroutine
        'qa', ...
    )
    return qa_summary

# 2. Event loop wrapper (event_loop_utils.py:50)
def _run_agent_in_event_loop(coroutine_func, *args, **kwargs):
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(coroutine_func(*args, **kwargs))
    # ... cleanup ...
    return result

# 3. Async implementation (event_loop_utils.py:173)
async def _run_agent_internal_with_prompts(agent_type, repo_root, query, ...):
    executor = SubAgentExecutor()
    agent = await executor.create_agent(...)
    summary = await executor.execute_agent(...)
    return summary
```

### Key Observations

1. **SubAgentExecutor is fully async**: All methods use `async def` and `await`
2. **Config.__init__() is sync**: Cannot use `await` directly
3. **Event loop wrapper exists**: `_run_agent_in_event_loop()` handles sync-to-async
4. **Established pattern**: Fix/QA agents already use this exact pattern
5. **Platform handling**: Wrapper handles Windows ProactorEventLoop requirements
6. **Cleanup**: Wrapper manages task cancellation and resource cleanup

## Decision

**Use the established event loop wrapper pattern** for CommandDetectionAgent.

### Implementation Approach

```python
# src/smartfix/domains/agents/command_detection_agent.py
class CommandDetectionAgent:
    async def detect_async(
        self,
        build_files: list[str],
        failed_attempts: list[dict[str, str]],
        remediation_id: str
    ) -> str | None:
        """Async implementation using SubAgentExecutor."""
        # Actual async logic here
        pass

    def detect(
        self,
        build_files: list[str],
        failed_attempts: list[dict[str, str]],
        remediation_id: str
    ) -> str | None:
        """Sync wrapper for use from Config.__init__()."""
        from src.smartfix.domains.agents.event_loop_utils import _run_agent_in_event_loop

        return _run_agent_in_event_loop(
            self.detect_async,
            build_files,
            failed_attempts,
            remediation_id
        )

# Alternative: Helper function pattern
async def _detect_command_internal(
    repo_root: Path,
    build_files: list[str],
    failed_attempts: list[dict[str, str]],
    remediation_id: str
) -> str | None:
    """Internal async helper following _run_agent_internal_with_prompts pattern."""
    executor = SubAgentExecutor()
    # Create and execute agent
    pass

def detect_build_command(repo_root: Path, build_files: list[str], ...) -> str | None:
    """Public sync function for Config integration."""
    return _run_agent_in_event_loop(
        _detect_command_internal,
        repo_root,
        build_files,
        ...
    )
```

## Alternatives Considered

### Option 1: Keep detect() synchronous, wrap SubAgentExecutor calls
**Rejected**: Violates SubAgentExecutor contract, creates awkward nested event loops

### Option 2: Make Config.__init__() async
**Rejected**: Massive refactoring, breaks existing code, Config is used everywhere synchronously

### Option 3: Use threading with run_in_executor
**Rejected**: Adds complexity, doesn't match existing patterns, harder to test

### Option 4: Create separate sync CommandDetectionAgent
**Rejected**: Duplicate logic, doesn't use SubAgentExecutor benefits (telemetry, MCP tools, event limits)

## Consequences

### Positive

✅ **Follows established patterns**: Identical to Fix/QA agent architecture
✅ **Clean async implementation**: No compromises in async code
✅ **Reuses infrastructure**: Uses existing event loop wrapper
✅ **Testability**: Can test async methods directly, sync wrapper separately
✅ **Future-proof**: Ready for SubAgentExecutor integration
✅ **Platform compatible**: Inherits Windows ProactorEventLoop handling

### Negative

⚠️ **Two methods**: `detect()` (sync wrapper) and `detect_async()` (implementation)
⚠️ **Event loop overhead**: Creates/destroys event loop per call (acceptable for infrequent Config init)

### Neutral

- Requires updating beads-73f to add async method before beads-7nf
- Tests need to test both sync wrapper and async implementation

## Implementation Plan

### Phase 1: Update CommandDetectionAgent (beads-73f amendment or new bead)

1. Rename `detect()` → `detect_async()`, make it `async def`
2. Add sync `detect()` wrapper using `_run_agent_in_event_loop()`
3. Update tests to test both methods
4. Update all TODO comments to use async/await patterns

### Phase 2: Implement SubAgentExecutor Integration (beads-7nf)

1. Use `SubAgentExecutor()` in `detect_async()`
2. Call `executor.create_agent()` with command detection prompt
3. Call `executor.execute_agent()` with iteration loop
4. Add telemetry tracking following existing patterns

### Phase 3: Config Integration (beads-yup)

```python
# In Config.__init__() around line 85
if not self.BUILD_COMMAND and is_build_command_required:
    from src.smartfix.config.detection_service import detect_build_command
    self.BUILD_COMMAND = detect_build_command(
        repo_root=Path.cwd(),
        build_files=scan_for_build_files(),
        failed_attempts=[],
        remediation_id="config-init"
    )
```

## Testing Strategy

```python
# test/test_command_detection_agent.py

class TestCommandDetectionAgent(unittest.TestCase):
    def test_detect_sync_wrapper(self):
        """Test sync wrapper calls async implementation."""
        agent = CommandDetectionAgent(repo_root)
        result = agent.detect(build_files, [], "test-id")
        # Sync call works from test

    async def test_detect_async_implementation(self):
        """Test async implementation directly."""
        agent = CommandDetectionAgent(repo_root)
        result = await agent.detect_async(build_files, [], "test-id")
        # Async implementation testable

    def test_event_loop_wrapper_integration(self):
        """Test event loop wrapper handles cleanup."""
        # Test with mocked SubAgentExecutor
        pass
```

## References

- SubAgentExecutor: `src/smartfix/domains/agents/sub_agent_executor.py:53`
- Event loop wrapper: `src/smartfix/domains/agents/event_loop_utils.py:50`
- QA agent usage: `src/smartfix/domains/agents/smartfix_agent.py:463`
- Config integration point: `src/config.py:85`

## Approval

Approved by: Architectural review for beads-g0g
Implements: Async/sync mismatch resolution
Unblocks: beads-7nf (LLM agent tests), beads-yup (Config integration)

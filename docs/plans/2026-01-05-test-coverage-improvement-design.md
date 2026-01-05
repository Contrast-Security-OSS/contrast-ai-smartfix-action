# Test Coverage Improvement Design

**Date:** 2026-01-05
**Status:** Approved
**Current Coverage:** 51% (3879 statements, 1889 missed)
**Target Coverage:** 70%+ overall

## Goal

Achieve robust test coverage across all functional domains before refactoring. Focus on critical paths and error conditions rather than 100% line coverage. Ensure tests prevent accidental git operations that could affect the working directory.

## Current State

**Branch:** `release_candidate`
**Tests:** 373 passing
**Test Command:** `make test` (canonical)
**Lint Command:** `make lint`

### Coverage by Domain

| Domain | Module | Current | Target | Priority |
|--------|--------|---------|--------|----------|
| **Agent Orchestration** | smartfix_agent.py | 10% | 70% | Critical |
| | event_loop_utils.py | 13% | 70% | Critical |
| | sub_agent_executor.py | 15% | 70% | Critical |
| | mcp_manager.py | 27% | 70% | High |
| **Build/Test Workflow** | formatter.py | 19% | 70% | High |
| | build_runner.py | 27% | 70% | High |
| **API Integration** | contrast_api.py | 28% | 70% | High |
| | closed_handler.py | 50% | 70% | Medium |
| | merge_handler.py | 66% | 75% | Low |
| **SCM Operations** | github_operations.py | 38% | 75% | Medium |
| | git_operations.py | 64% | 75% | Low |
| | scm_operations.py | 68% | 75% | Low |
| **Entry Point** | main.py | 32% | 60% | High |

## Testing Strategy

### Established Pattern

The project uses `unittest` with full mocking via `@patch` decorators. This approach prevents accidental git operations (branch switching, cleanup) that have caused test failures in the past.

**Key Pattern (from `test_agent_domain.py`):**
```python
GIT_OPERATIONS_PATCHES = [
    'src.smartfix.domains.scm.git_operations.GitOperations.prepare_feature_branch',
    'src.smartfix.domains.scm.git_operations.GitOperations.stage_changes',
    # ... all git operations
]

class TestSomething(unittest.TestCase):
    def setUp(self):
        self.git_mocks = []
        for patch_target in GIT_OPERATIONS_PATCHES:
            patcher = patch(patch_target)
            mock = patcher.start()
            self.git_mocks.append((patcher, mock))

    def tearDown(self):
        for patcher, mock in self.git_mocks:
            patcher.stop()
```

### Domain-Based Organization

Tests grouped by functional domain. Each domain has:
- Dedicated test file(s)
- Reusable "PATCHES" list defining external calls to mock
- setUp/tearDown that starts/stops all patches
- Focus on critical paths, error conditions, edge cases

## Domain 1: Agent Orchestration

**Modules:** smartfix_agent.py (10%), event_loop_utils.py (13%), sub_agent_executor.py (15%), mcp_manager.py (27%)

### smartfix_agent.py Testing

**Focus:** Remediation workflow state machine

**Critical Paths:**
- Initial build validation (pass/fail)
- Fix agent execution (success/failure)
- QA loop (success/retry/failure)
- Session completion (all failure categories)

**Test Cases:**
- Build fails before fix attempt → INITIAL_BUILD_FAILURE
- Fix agent succeeds, no build command → immediate success
- Fix agent succeeds, QA loop passes → success
- Fix agent succeeds, QA loop exhausts retries → QA_FAILURE
- Fix agent throws exception → AGENT_FAILURE
- Build never passes after fix → BUILD_FAILURE

**Mocking:**
- `_run_ai_fix_agent` (return mock PR body or None)
- `_run_ai_qa_agent` (return success/failure)
- `run_build_command` (return success/failure + output)
- All git operations via `GIT_OPERATIONS_PATCHES`

### event_loop_utils.py Testing

**Focus:** Async event loop lifecycle and error handling

**Critical Paths:**
- Event loop creation and cleanup
- Agent execution with success
- Agent execution with exceptions
- Timeout scenarios
- Cleanup on errors

**Test Cases:**
- `_run_agent_in_event_loop` with successful agent
- `_run_agent_in_event_loop` with agent exception (ensure cleanup)
- `_run_agent_internal_with_prompts` with timeout
- Event loop cleanup even when errors occur
- Multiple sequential agent runs (ensure no loop contamination)

**Mocking:**
- Agent execution (mock the actual LLM calls)
- `asyncio.new_event_loop()`, `asyncio.set_event_loop()`
- File operations
- Build commands

**Async Test Pattern:**
```python
def test_async_function(self):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(async_function())
        self.assertEqual(result, expected)
    finally:
        loop.close()
```

### sub_agent_executor.py Testing

**Focus:** Sub-agent orchestration logic

**Critical Paths:**
- Spawning sub-agents
- Collecting results
- Handling sub-agent failures
- Timeout management

**Test Cases:**
- Execute sub-agent successfully
- Sub-agent throws exception (isolation)
- Sub-agent timeout
- Multiple parallel sub-agents
- Result aggregation

**Mocking:**
- LLM client calls
- Agent execution
- All I/O operations

### mcp_manager.py Testing

**Focus:** MCP server connection lifecycle

**Critical Paths:**
- Server connection establishment
- Tool discovery
- Connection failures
- Timeout handling
- Cleanup

**Test Cases:**
- Connect to MCP server successfully
- Connection timeout
- Server not available
- Tool discovery (empty list, populated list)
- Connection cleanup on errors

**Mocking:**
- MCP protocol calls (stdio transport)
- Subprocess operations
- Timeout mechanisms

## Domain 2: Build/Test Workflow

**Modules:** build_runner.py (27%), formatter.py (19%)

### build_runner.py Testing

**Focus:** Build execution and output capture

**Critical Paths:**
- Successful builds
- Build failures with error output
- Timeout scenarios
- Exit code handling
- Telemetry integration

**Test Cases:**
- Build succeeds (exit 0, clean output)
- Build fails (exit 1, error output)
- Build timeout
- Build output parsing (stdout/stderr)
- Different exit codes (0, 1, 2, 124, 137)
- Telemetry recording of build metrics

**Mocking:**
- `subprocess.run` with different return codes and outputs
- Timeout exceptions
- Telemetry updates

**Security Note:** Test that command validation (allowlist) is respected

### formatter.py Testing

**Focus:** Formatter execution and graceful degradation

**Critical Paths:**
- Successful formatting
- Formatter failures (don't fail remediation)
- Missing formatter binaries
- Timeout scenarios

**Test Cases:**
- Formatter succeeds (files changed)
- Formatter fails (exit non-zero) → log warning, continue
- Formatter not found → log warning, continue
- Formatter timeout → log warning, continue
- Multiple formatters in sequence

**Mocking:**
- `subprocess.run` for formatter commands
- File system operations
- Timeout mechanisms

## Domain 3: SCM Operations

**Modules:** github_operations.py (38%), git_operations.py (64%), scm_operations.py (68%)

### github_operations.py Testing (Main Focus)

**Focus:** GitHub-specific operations with 38% current coverage

**Critical Paths:**
- PR creation with labels
- Issue creation and search
- Label management
- GraphQL queries
- PR file count retrieval

**Test Cases:**
- Create PR successfully
- Create PR with GitHub API error
- Find issue by label (exists/doesn't exist)
- Create issue successfully
- Add labels to PR
- GraphQL branch discovery (pagination)
- Get PR changed files count (success, failure, invalid response)
- Ensure label exists (already exists, needs creation, creation fails)
- Check if issues enabled (true/false)

**Mocking:**
- `gh` CLI commands via `run_command`
- GraphQL API responses
- Subprocess operations
- HTTP errors and timeouts

**Expand from existing `test_github_operations.py` (100 lines → ~300 lines)**

### git_operations.py Testing (Fill Gaps)

**Focus:** Complete remaining gaps from 64% → 75%

**Areas to Cover:**
- Branch cleanup edge cases (branch doesn't exist)
- Push with authentication errors
- Error handling when git commands fail
- Concurrent git operations (if applicable)

**Extend existing `test_git_operations.py`**

### scm_operations.py Testing (Minimal Gaps)

**Focus:** Complete SCM abstraction layer from 68% → 75%

**Areas to Cover:**
- Interface contract enforcement
- Error propagation from underlying implementations
- Edge cases in abstraction layer

## Domain 4: API Integration

**Modules:** contrast_api.py (28%), closed_handler.py (50%), merge_handler.py (66%)

### contrast_api.py Testing (Main Focus)

**Focus:** Contrast Security API client with 28% current coverage

**Critical Paths:**
- Fetch prompt details
- Notify remediation status (opened, failed, merged)
- Credit tracking checks
- HTTP error handling
- Timeout scenarios

**Test Cases:**
- Fetch prompt details: success (200), 404, 500, timeout, invalid JSON
- Notify remediation opened: success (204), retry on 500
- Notify remediation failed: success (204), 400 bad request
- Notify remediation merged: success (204), retry logic
- Credit tracking enabled with credits available
- Credit tracking disabled
- Credit tracking with credits exhausted
- Credit tracking API errors (404, 500, timeout)
- URL construction with different host configurations
- Authentication header construction

**Mocking:**
- `requests.get`, `requests.post`, `requests.put`
- HTTP responses (status codes, JSON bodies)
- Timeouts and connection errors
- JSON parsing errors

**Recent Work:** PR #94 added some tests, expand further

### closed_handler.py Testing (Fill Gaps)

**Focus:** PR closed event handling from 50% → 70%

**Critical Paths:**
- Distinguish merged vs unmerged
- Extract remediation ID from labels
- Extract remediation ID from branch names
- Notify Contrast API appropriately

**Test Cases:**
- PR closed and merged → delegate to merge_handler
- PR closed unmerged → notify API, cleanup
- Extract remediation ID from labels (success, failure)
- Extract remediation ID from branch name (various patterns)
- External agent detection (Copilot, Claude Code)
- PR with no changed files → report as failed

**Extend existing `test_closed_handler.py`**

### merge_handler.py Testing (Minimal Gaps)

**Focus:** Complete from 66% → 75%

**Areas to Cover:**
- Edge cases in merge detection
- Error paths in API notification
- Telemetry recording

**Extend existing `test_merge_handler.py`**

## Domain 5: Application Entry Point

**Module:** main.py (32%)

### main.py Testing

**Focus:** Top-level workflow orchestration

**Critical Paths:**
- SmartFix agent workflow
- External agent workflows (Copilot, Claude Code)
- Merge handler path
- Closed handler path
- Version checking
- Configuration validation
- Top-level error handling

**Test Cases:**
- SmartFix workflow: fetch vuln → create agent → remediate → create PR
- GitHub Copilot workflow: create issue with Copilot assignment
- Claude Code workflow: create issue mentioning Claude
- Merge handler: detect merged PR → notify API → telemetry
- Closed handler: detect unmerged closed PR → cleanup → notify
- Version check failure: outdated version warning
- Missing required environment variables → error_exit
- Top-level exception: telemetry recorded, error logged
- Credit exhaustion: skip remediation

**Mocking:**
- All agent factories
- All handlers (merge, closed)
- `contrast_api` calls
- Git operations
- Telemetry updates
- `version_check.do_version_check`
- `sys.exit` calls

**Target:** 60% (focus on main paths, not every conditional)

**Extend existing `test_main.py`**

## Implementation Structure

### Test File Organization

```
test/
├── test_smartfix_agent.py          # Expand for agent orchestration
├── test_event_loop_utils.py        # New: async event loop tests
├── test_sub_agent_executor.py      # New: sub-agent orchestration
├── test_mcp_manager.py             # New: MCP server management
├── test_build_runner.py            # New: build execution
├── test_formatter.py               # New: formatter execution
├── test_github_operations.py       # Expand (38% → 75%)
├── test_git_operations.py          # Expand (64% → 75%)
├── test_contrast_api.py            # Expand (28% → 70%)
├── test_closed_handler.py          # Expand (50% → 70%)
├── test_merge_handler.py           # Expand (66% → 75%)
├── test_main.py                    # Expand (32% → 60%)
└── test_helpers/                   # New: shared patch lists
    ├── agent_patches.py            # AGENT_PATCHES list
    ├── build_patches.py            # BUILD_WORKFLOW_PATCHES list
    ├── api_patches.py              # API_INTEGRATION_PATCHES list
    └── common_patches.py           # Shared utilities
```

### Makefile Addition

Add `coverage` target to Makefile:

```makefile
# Run tests with coverage report
coverage:
	@echo "Running tests with coverage..."
	.venv/bin/coverage run -m unittest discover -s test
	.venv/bin/coverage report --include="src/*" --omit="src/__pycache__/*"
	.venv/bin/coverage html
	@echo "HTML coverage report generated in htmlcov/"
```

### Shared Test Helpers

**test_helpers/agent_patches.py:**
```python
"""Shared patches for agent orchestration tests."""

AGENT_PATCHES = [
    'src.smartfix.domains.agents.smartfix_agent.SmartFixAgent._run_ai_fix_agent',
    'src.smartfix.domains.agents.smartfix_agent.SmartFixAgent._run_ai_qa_agent',
    'src.smartfix.domains.agents.event_loop_utils._run_agent_in_event_loop',
    'src.smartfix.domains.agents.sub_agent_executor.execute_sub_agent',
    'src.smartfix.domains.agents.mcp_manager.MCPManager.connect',
    # Add all agent-related external calls
]
```

**test_helpers/build_patches.py:**
```python
"""Shared patches for build/test workflow tests."""

BUILD_WORKFLOW_PATCHES = [
    'subprocess.run',
    'subprocess.Popen',
    'src.smartfix.domains.workflow.build_runner.run_build_command',
    'src.smartfix.domains.workflow.formatter.run_formatting_command',
    # Add all build-related external calls
]
```

**test_helpers/api_patches.py:**
```python
"""Shared patches for API integration tests."""

API_INTEGRATION_PATCHES = [
    'requests.get',
    'requests.post',
    'requests.put',
    'src.contrast_api.fetch_prompt_details',
    'src.contrast_api.notify_remediation_opened',
    'src.contrast_api.notify_remediation_failed',
    # Add all API-related external calls
]
```

## Success Criteria

1. **Coverage Targets Met:**
   - Agent Orchestration: 10-27% → 70%+
   - Build/Test Workflow: 19-27% → 70%+
   - SCM Operations: 38-68% → 75%+
   - API Integration: 28-66% → 70%+
   - Application Entry Point: 32% → 60%+
   - **Overall: 51% → 70%+**

2. **All Tests Pass:**
   - `make test` succeeds
   - No flaky tests
   - Tests run in < 5 seconds

3. **No Linting Errors:**
   - `make lint` passes

4. **No Accidental Git Operations:**
   - No branch switching during tests
   - No cleanup of actual working directory
   - All git operations properly mocked

5. **Fast Test Execution:**
   - Full suite remains under 5 seconds
   - No real I/O or network calls
   - No real subprocess executions

## Risks & Mitigations

### Risk 1: Accidental Git Operations

**Impact:** Critical - tests could switch branches, delete files
**Mitigation:**
- Comprehensive patch lists for all git operations
- Verify in setUp that all patches are active
- Add assertions that no real git commands execute
- Review all test files for missing patches

### Risk 2: Async Tests Become Flaky

**Impact:** High - intermittent failures block development
**Mitigation:**
- Mock all I/O and network calls in async code
- Use proper `asyncio` test utilities
- Avoid real sleeps (use mock time)
- Test async code synchronously where possible

### Risk 3: Tests Become Brittle

**Impact:** Medium - break on refactoring
**Mitigation:**
- Test behavior/contracts, not implementation
- Mock at appropriate boundaries (not too deep)
- Use existing established patterns
- Focus on inputs/outputs, not internal state

### Risk 4: Coverage Work Takes Too Long

**Impact:** Low - delays other work
**Mitigation:**
- Work domain by domain
- Get each domain to target before moving on
- Can stop after any complete domain
- Parallelize work across independent domains

## Implementation Order

1. **Makefile updates** (add coverage target)
2. **Test helpers** (create shared patch lists)
3. **Domain 1: Agent Orchestration** (highest priority, lowest coverage)
4. **Domain 2: Build/Test Workflow** (high priority, low coverage)
5. **Domain 4: API Integration** (high priority, contrast_api.py at 28%)
6. **Domain 5: Entry Point** (main.py orchestration)
7. **Domain 3: SCM Operations** (lowest priority, already 64-68%)

Domains 1, 2, 4 can be worked in parallel after test helpers are ready.

## Notes

- Command to run tests: `make test`
- Command to check linting: `make lint`
- Command to check coverage: `make coverage` (after implementation)
- All tests use `unittest`, not `pytest`
- Use `@patch` decorators consistently
- Follow existing test file patterns
- No real git operations - mock everything
- Tests must be fast (< 5 sec total)

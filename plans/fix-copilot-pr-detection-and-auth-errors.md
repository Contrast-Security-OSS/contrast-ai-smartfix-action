# Fix GitHub Copilot PR Detection and Authentication Error Handling

## Overview

Fix two related GitHub integration bugs in contrast-ai-smartfix-action:

1. **AIML-245**: GitHub Copilot PR detection fails because Copilot changed branch naming from `copilot/fix-{issue_number}` to `copilot/fix-semantic-name`. Current code uses pattern matching and title matching which no longer work reliably.

2. **AIML-320**: Authentication errors (401/403) from `gh pr list` are silently caught and return 0, masking configuration problems and causing confusing "No vulnerabilities were processed" messages.

## Problem Statement

**AIML-245 Root Cause:**
- Copilot evolved its branch naming from predictable numeric patterns to semantic naming
- Current code in `external_coding_agent.py` uses `find_open_pr_for_issue()` which relies on:
  - Pattern matching: `copilot/fix-{issue_number}`
  - Title matching: `in:title` parameter in `gh pr list`
- Both approaches are now unreliable with semantic branch names

**AIML-320 Root Cause:**
- `count_open_prs_with_prefix()` in `github_operations.py:270-306` catches all exceptions generically
- Returns 0 on failure, including authentication errors
- Masks critical configuration issues that should fail the build
- Users see "No vulnerabilities processed" instead of clear auth error message

## Proposed Solution

Refactor Copilot handling to use workflow run watching (similar to Claude Code), and propagate authentication errors with clear remediation steps.

### Architecture Changes

**Current Flow (Broken):**
```
Issue Created → Copilot Workflow Triggered → PR Created by Copilot
                                              ↓
                                     Poll for PR by pattern matching
                                              ↓
                                          FAILS ❌
```

**New Flow (Fixed):**
```
Issue Created → Copilot Workflow Triggered → PR Created by Copilot
                     ↓
              Watch Workflow Run
                     ↓
         Get headBranch from metadata
                     ↓
          Find PR using actual branch
                     ↓
              SUCCESS ✅
```

## Technical Approach

### Component 1: New Method `get_copilot_workflow_run_id()`

**Location:** `src/github/github_operations.py`

**Purpose:** Find Copilot's workflow run and extract actual branch name from metadata

**Implementation:**
```python
def get_copilot_workflow_run_id(self, issue_number: int) -> tuple[int | None, str | None]:
    """
    Find the most recent Copilot workflow run for an issue.

    Returns:
        (run_id, head_branch): Workflow run ID and branch name, or (None, None)
    """
    workflow_command = [
        "gh", "run", "list",
        "--workflow", "Copilot coding agent",  # Exact workflow display name
        "--json", "databaseId,status,event,createdAt,conclusion,headBranch",
        "--limit", "50"
    ]

    try:
        output = run_command(workflow_command, env=gh_env, check=True)
        runs = json.loads(output)

        # Find most recent workflow for this issue
        # Note: May need to check workflow inputs or commit messages
        # to definitively link workflow to issue
        for run in runs:
            # TODO: Determine linkage strategy (see Critical Questions below)
            if self._is_workflow_for_issue(run, issue_number):
                return run['databaseId'], run.get('headBranch')

        return None, None

    except Exception as e:
        log(f"Error finding Copilot workflow: {e}", is_error=True)
        return None, None
```

**Critical Questions to Resolve:**
1. How to definitively link workflow run to issue number?
   - Option A: Parse commit messages in workflow
   - Option B: Check workflow inputs if available
   - Option C: Use creation timestamp proximity

2. What if multiple workflows match?
   - Take most recent by `createdAt`?
   - Check status (prefer `in_progress` over `completed`)?

### Component 2: New Method `_process_copilot_workflow_run()`

**Location:** `src/github/external_coding_agent.py`

**Purpose:** Handle Copilot workflow completion and PR finding using actual branch name

**Implementation:**
```python
def _process_copilot_workflow_run(
    self,
    git_handler: GitHandler,
    issue_number: int,
    issue_title: str,
    check_interval: int = 30,
    timeout: int = 900
) -> dict | None:
    """
    Watch Copilot workflow, get actual branch, find PR.

    Returns:
        PR info dict with url, number, title, branch
    """
    github_ops = GitHubOperations()

    # Get workflow run ID and branch
    run_id, head_branch = github_ops.get_copilot_workflow_run_id(issue_number)

    if not run_id:
        log(f"No Copilot workflow found for issue #{issue_number}", is_error=True)
        return None

    if not head_branch:
        log(f"Workflow {run_id} has no headBranch metadata", is_error=True)
        return None

    log(f"Found Copilot workflow {run_id} on branch {head_branch}")

    # Watch workflow completion (reuse existing method)
    watch_result = git_handler.watch_github_action_run(
        run_id=run_id,
        check_interval=check_interval,
        timeout=timeout
    )

    if not watch_result or watch_result != "success":
        log(f"Copilot workflow {run_id} did not complete successfully", is_error=True)
        return None

    # Find PR using actual branch name
    pr_info = github_ops.find_pr_by_branch(head_branch)

    if not pr_info:
        log(f"No PR found for Copilot branch {head_branch}", is_error=True)
        return None

    return pr_info
```

**Critical Questions to Resolve:**
3. Should we support fallback to old pattern matching?
   - For backward compatibility with older Copilot workflows?
   - Risk: Perpetuates unreliable approach

4. What timeout is appropriate for Copilot workflows?
   - Currently using 900s (15 min) - is this sufficient?
   - Should timeout be configurable?

### Component 3: Refactor `_process_external_coding_agent_run()`

**Location:** `src/github/external_coding_agent.py:294-296`

**Purpose:** Unify Claude Code and Copilot to both use workflow-watching approach

**Current Code:**
```python
else:
    # GitHub Copilot agent
    github_ops = GitHubOperations()
    pr_info = github_ops.find_open_pr_for_issue(issue_number, issue_title)
```

**New Code:**
```python
else:
    # GitHub Copilot agent - watch workflow for actual branch
    pr_info = self._process_copilot_workflow_run(
        git_handler=git_handler,
        issue_number=issue_number,
        issue_title=issue_title,
        check_interval=check_interval,
        timeout=timeout
    )
```

**Critical Questions to Resolve:**
5. Remove `find_open_pr_for_issue()` method entirely?
   - Currently only used by Copilot path
   - May have utility for manual PR verification?

6. Should we extract common workflow-watching logic?
   - Both Claude and Copilot now watch workflows
   - Opportunity for shared helper method?

### Component 4: Fix Authentication Error Handling

**Location:** `src/github/github_operations.py:270-306`

**Current Code (Broken):**
```python
def count_open_prs_with_prefix(self, label_prefix: str) -> int:
    try:
        pr_list_output = run_command(pr_list_command, env=gh_env, check=True)
        prs_data = json.loads(pr_list_output)
    except Exception as e:
        log(f"Error running gh pr list command: {e}", is_error=True)
        return 0  # ← BUG: masks auth failures
```

**New Code (Fixed):**
```python
def count_open_prs_with_prefix(self, label_prefix: str, remediation_id: str) -> int:
    try:
        pr_list_output = run_command(pr_list_command, env=gh_env, check=True)
        prs_data = json.loads(pr_list_output)
    except CalledProcessError as e:
        # Check for authentication errors
        error_output = e.stderr.lower() if e.stderr else str(e).lower()

        if '401' in error_output or '403' in error_output or 'authentication' in error_output:
            log("""GitHub authentication failed. Please check your github_token configuration.

Verify that:
  - GITHUB_TOKEN is set correctly
  - Token has required permissions (repo scope)
  - Token has not expired

See documentation: docs/github_authentication.md""", is_error=True)

            error_exit(remediation_id, FailureCategory.GIT_COMMAND_FAILURE.value)
        else:
            # Non-auth error - log and re-raise
            log(f"Error running gh pr list command: {e}", is_error=True)
            raise
    except Exception as e:
        log(f"Unexpected error in count_open_prs_with_prefix: {e}", is_error=True)
        raise
```

**Critical Questions to Resolve:**
7. What error patterns definitively indicate auth failure?
   - Status codes: 401 (unauthorized), 403 (forbidden)
   - Message keywords: "authentication", "credentials", "token"
   - Are there other patterns to catch?

8. Should we detect expired tokens specifically?
   - Different message than missing tokens?
   - Suggest refresh/regeneration workflow?

### Component 5: Update Abstract Base Class

**Location:** `src/smartfix/domains/scm/scm_operations.py:~270`

**Current Signature:**
```python
@abstractmethod
def count_open_prs_with_prefix(self, label_prefix: str) -> int:
    pass
```

**New Signature:**
```python
@abstractmethod
def count_open_prs_with_prefix(self, label_prefix: str, remediation_id: str) -> int:
    """
    Count open PRs with given label prefix.

    Args:
        label_prefix: Prefix to filter PR labels
        remediation_id: Unique ID for error reporting/tracking

    Returns:
        Count of matching PRs

    Raises:
        Calls error_exit() on authentication failures
    """
    pass
```

### Component 6: Update All Callers

**Affected Files:**
- `src/main.py` - Primary entry point
- `src/github/github_operations.py` - Internal calls
- Any other files calling `count_open_prs_with_prefix()`

**Update Pattern:**
```python
# OLD:
count = github_ops.count_open_prs_with_prefix(label_prefix)

# NEW:
count = github_ops.count_open_prs_with_prefix(label_prefix, remediation_id)
```

**Critical Questions to Resolve:**
9. How to handle callers without remediation_id context?
   - Generate temporary ID?
   - Make parameter optional with default?
   - Fail fast if not provided?

10. Should we add remediation_id to other GitHub operations?
    - `find_pr_by_branch()`?
    - `get_copilot_workflow_run_id()`?
    - Consistent error reporting across all GitHub ops?

## Technical Considerations

### GitHub CLI API Usage
- **Workflow listing**: `gh run list --workflow "Copilot coding agent" --json databaseId,status,event,createdAt,conclusion,headBranch`
- **Rate limiting**: Consider caching workflow lookups if called frequently
- **Field availability**: Verify `headBranch` exists in all workflow run responses

### Error Handling Patterns
- **Authentication errors**: Fail fast with clear remediation steps
- **Network errors**: Distinguish transient from permanent failures
- **Missing workflows**: Log clearly but don't fail build (Copilot may not have run)

### Backward Compatibility
- Old Copilot branches (`copilot/fix-{issue_number}`) may still exist in repos
- Consider supporting both patterns during transition period
- Document deprecation timeline if maintaining fallback

### Performance Implications
- Workflow watching adds latency (current timeout: 900s)
- Consider async/concurrent workflow watching if processing multiple issues
- Cache workflow lookups to avoid repeated API calls

## Acceptance Criteria

### Functional Requirements

- [ ] **AIML-245**: Copilot PR detection works with semantic branch names
  - `get_copilot_workflow_run_id()` finds workflow by display name "Copilot coding agent"
  - Method extracts `headBranch` from workflow metadata
  - `_process_copilot_workflow_run()` uses actual branch to find PR
  - No pattern matching or title matching used

- [ ] **AIML-320**: Authentication errors fail build with clear message
  - `count_open_prs_with_prefix()` detects 401/403 errors
  - Error message includes remediation steps (check token, permissions, expiry)
  - Method calls `error_exit()` with appropriate failure category
  - No silent return of 0 on auth failures

- [ ] Abstract base class updated correctly
  - `ScmOperations.count_open_prs_with_prefix()` signature includes `remediation_id`
  - All implementing classes updated
  - All callers pass `remediation_id` parameter

### Non-Functional Requirements

- [ ] **Performance**: Workflow watching completes within 15 minutes
- [ ] **Reliability**: Handles missing workflows gracefully (Copilot may not run)
- [ ] **Maintainability**: Clear separation between Claude Code and Copilot paths
- [ ] **Observability**: Comprehensive logging at each step (workflow found, branch extracted, PR found)

### Quality Gates

- [ ] **Unit tests**: Cover new methods with mock GitHub CLI responses
  - Test `get_copilot_workflow_run_id()` with various workflow states
  - Test auth error detection with different error messages
  - Test parameter passing for `remediation_id`

- [ ] **Integration tests**: Verify end-to-end Copilot workflow watching
  - Mock workflow run with `headBranch` in response
  - Verify PR found using extracted branch
  - Verify auth errors trigger `error_exit()`

- [ ] **Error path testing**: Verify all error conditions handled
  - No workflow found for issue
  - Workflow missing `headBranch` field
  - Workflow completes but no PR exists
  - Authentication failures (401, 403)
  - Network timeouts

## Success Metrics

- **AIML-245**: 100% success rate finding Copilot PRs regardless of branch name
- **AIML-320**: Zero silent auth failures; all auth errors reported clearly
- **Monitoring**: No "No vulnerabilities processed" messages when auth fails

## Dependencies & Prerequisites

### Required
- GitHub CLI (`gh`) with authentication configured
- Access to repository workflow runs via GitHub API
- `headBranch` field available in workflow run JSON (verify with `gh` version)

### Assumed
- Copilot workflow name remains "Copilot coding agent" (exact string)
- Workflow run metadata includes sufficient info to link to issue
- `watch_github_action_run()` method works reliably for Copilot workflows

## Risk Analysis & Mitigation

| Risk | Severity | Mitigation |
|------|----------|------------|
| Workflow name changes | Medium | Document exact name; add config option |
| Multiple workflows match issue | Medium | Use most recent by timestamp; document behavior |
| `headBranch` field missing | Low | Validate field presence; log clear error |
| Breaking existing Copilot integrations | High | Test thoroughly; consider feature flag |
| Auth error detection too broad | Low | Use specific error codes (401/403); test edge cases |

## References & Research

### Internal References

- **External coding agent patterns**: `src/github/external_coding_agent.py:342-451` (Claude Code workflow watching)
- **Current Copilot handling**: `src/github/external_coding_agent.py:294-296` (broken pattern matching)
- **Error handling example**: `src/github/github_operations.py:952-1011` (`get_claude_workflow_run_id()`)
- **Workflow watching reusable method**: `src/github/github_operations.py:917-950` (`watch_github_action_run()`)

### External References

- **GitHub CLI documentation**: https://cli.github.com/manual/gh_run_list
- **Workflow run JSON fields**: https://docs.github.com/en/rest/actions/workflow-runs
- **GitHub authentication guide**: https://docs.github.com/en/authentication

### Related Work

- **AIML-359**: Destructive Command Guard integration (completed)
- **CSRF vulnerability exclusion**: `docs/smartfix_coding_agent.md:220`

## Implementation Notes

### Workflow Name Detection
The workflow display name "Copilot coding agent" was confirmed from actual workflow run output:
```
Running Copilot coding agent Copilot coding agent #73: by Copilot AI
```

This is the human-readable name, not the workflow filename. Verify this remains stable across Copilot updates.

### Issue-to-Workflow Linkage Strategy
**Recommended approach**: Use most recent workflow by `createdAt` timestamp within reasonable proximity (e.g., 5 minutes) of issue creation. This handles:
- Multiple Copilot workflows in repository
- Concurrent issue remediation
- Workflow retries

**Alternative approaches** to consider:
- Parse commit messages for issue number
- Check workflow inputs if exposed via API
- Use GitHub issue-to-PR linkage as validation

### Testing Strategy
1. **Unit test** each new method with mocked GitHub CLI responses
2. **Integration test** with real workflow run data (captured JSON)
3. **Manual verification** with actual Copilot-created PRs
4. **Regression test** with old branch naming pattern (if supporting fallback)

### Rollout Plan
1. Implement and test in feature branch
2. Enable for single-issue testing in staging
3. Monitor error logs for unexpected auth failures
4. Roll out to production with feature flag (if available)
5. Document new behavior in `docs/github_integration.md`

---

**Questions for Product/Design:**
1. Should we maintain backward compatibility with old Copilot branch patterns?
2. What is acceptable timeout for Copilot workflow watching?
3. Should auth errors be distinguishable in failure categories (separate from generic GIT_COMMAND_FAILURE)?
4. Do we need to support multiple concurrent Copilot workflows per repository?

**Questions for Engineering:**
5. Is there a better way to link workflow runs to issue numbers?
6. Should workflow watching be extracted to shared utility?
7. What is the upgrade path for existing Copilot integrations?
8. Should we add metrics/monitoring for workflow watching success rate?

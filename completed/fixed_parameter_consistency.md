# Fixed Parameter Naming Consistency

## Bug Description

Even after fixing the parameter order in previous commits, there was still a method signature mismatch causing:

```
TypeError: AgentSystem.run_qa_agent() got an unexpected keyword argument 'max_events_per_agent'
```

The issue was that `AgentSystem.run_qa_agent()` was using `max_events` as the parameter name, but the caller (`BuildQaManager`) was passing `max_events_per_agent`.

## Root Cause Analysis

When creating the class hierarchy, we inconsistently named parameters:

1. `AgentRunner.run_qa_agent()` was using `max_events_per_agent`
2. `AgentSystem.run_qa_agent()` was using `max_events` 
3. `BuildQaManager.run_qa_process()` was passing `max_events_per_agent`

This inconsistency in parameter naming caused the TypeError.

## Solution

We updated the method signature in `AgentSystem.run_qa_agent()` to use `max_events_per_agent` instead of `max_events`:

```python
def run_qa_agent(
    self,
    build_output: str,
    changed_files: List[str],
    build_command: str,
    repo_root: Path,
    max_events_per_agent: int,  # Changed from max_events
    remediation_id: str,
    agent_model: str,
    qa_history: Optional[List[str]] = None,
    qa_system_prompt: Optional[str] = None,
    qa_user_prompt: Optional[str] = None
) -> str:
```

We also updated the function body to use the new parameter name:

```python
return self.agent_runner.run_qa_agent(
    build_output=build_output,
    changed_files=changed_files,
    build_command=build_command,
    repo_root=repo_root,
    remediation_id=remediation_id,
    agent_model=agent_model,
    max_events_per_agent=max_events_per_agent or self.max_events_per_agent,  # Changed from max_events
    qa_history=qa_history,
    qa_system_prompt=qa_system_prompt,
    qa_user_prompt=qa_user_prompt
)
```

And finally updated the method documentation to match the new parameter name.

## Benefits of This Approach

This approach has several advantages:

1. **Consistency**: All classes use the same parameter name (`max_events_per_agent`)
2. **Minimal changes**: We only needed to change one class, not all callers
3. **Self-documenting**: The name clearly describes that it's a per-agent limit
4. **Future-proof**: Helps prevent similar errors in future refactorings

## Lesson Learned

When refactoring to object-oriented code, be sure to maintain consistency in method signatures, especially parameter names, throughout the class hierarchy.
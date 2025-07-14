# Fixed QA Agent Method Call

## Bug Description
Even after updating the method signatures in `AgentSystem.run_qa_agent()` and `AgentRunner.run_qa_agent()`, an error persisted:

```
TypeError: AgentSystem.run_qa_agent() got an unexpected keyword argument 'max_events_per_agent'
```

This error occurred because while we fixed the method signatures in the implementation classes, we didn't update the actual call site in `build_qa_manager.py`.

## Root Cause
The parameter order in `build_qa_manager.py` didn't match the updated method signatures:

```python
qa_summary = qa_agent_runner.run_qa_agent(
    build_output=truncated_output,
    changed_files=changed_files,
    build_command=build_command,
    repo_root=repo_root,
    max_events_per_agent=max_events_per_agent,  # This parameter was in the wrong position
    remediation_id=remediation_id,
    agent_model=agent_model,
    qa_history=qa_summary_log,
    qa_system_prompt=qa_agent.system_prompt,
    qa_user_prompt=qa_agent.user_prompt
)
```

## Solution
Updated the parameter order in the method call to match the method signature:

```python
qa_summary = qa_agent_runner.run_qa_agent(
    build_output=truncated_output,
    changed_files=changed_files,
    build_command=build_command,
    repo_root=repo_root,
    remediation_id=remediation_id,
    agent_model=agent_model,
    max_events_per_agent=max_events_per_agent,  # Moved to correct position
    qa_history=qa_summary_log,
    qa_system_prompt=qa_agent.system_prompt,
    qa_user_prompt=qa_agent.user_prompt
)
```

## Lesson Learned
When updating method signatures in a refactoring project, it's essential to:

1. Check all call sites that use the method
2. Update the parameter order in all calls to match the new signature
3. Consider using named parameters to make the code more resilient to signature changes
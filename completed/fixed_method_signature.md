# Fixed Method Signature Issue

## Bug Description
When executing the QA agent process, the following error occurred:

```
TypeError: AgentSystem.run_qa_agent() got an unexpected keyword argument 'max_events_per_agent'
```

This error happened in `build_qa_manager.py`, which was trying to call `AgentSystem.run_qa_agent()` with `max_events_per_agent` as a named parameter, but the method expected this parameter with a different position in the signature.

## Root Cause
There was a parameter order mismatch between:

1. The caller in `build_qa_manager.py`, which called the method with `max_events_per_agent` as a named argument
2. The method signature in `AgentSystem.run_qa_agent()`, which was expecting the argument in a different position
3. The underlying implementation in `AgentRunner.run_qa_agent()`, which had a different parameter order

## Changes Made

### 1. In AgentRunner.run_qa_agent()
Changed the method signature from:
```python
def run_qa_agent(self, build_output: str, changed_files: List[str], build_command: str, repo_root: Path, max_events_per_agent: int, remediation_id: str, agent_model: str, qa_history: Optional[List[str]] = None, qa_system_prompt: Optional[str] = None, qa_user_prompt: Optional[str] = None) -> str:
```

To:
```python
def run_qa_agent(self, build_output: str, changed_files: List[str], build_command: str, repo_root: Path, remediation_id: str, agent_model: str, max_events_per_agent: int = 120, qa_history: Optional[List[str]] = None, qa_system_prompt: Optional[str] = None, qa_user_prompt: Optional[str] = None) -> str:
```

### 2. In AgentSystem.run_qa_agent()
Updated the call to match the new parameter order:
```python
return self.agent_runner.run_qa_agent(
    build_output=build_output,
    changed_files=changed_files,
    build_command=build_command,
    repo_root=repo_root,
    remediation_id=remediation_id,
    agent_model=agent_model,
    max_events_per_agent=max_events or self.max_events_per_agent,
    qa_history=qa_history,
    qa_system_prompt=qa_system_prompt,
    qa_user_prompt=qa_user_prompt
)
```

## Benefits
1. The parameter order now matches between the caller and implementation
2. The method can be called with named arguments without error
3. Added a default value for `max_events_per_agent` to make it more resilient
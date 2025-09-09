"""Contrast AI SmartFix Library

This library provides reusable SmartFix functionality for vulnerability remediation
that is independent of specific SCM providers and deployment environments.

The library is organized into domain-driven modules:
- domains.vulnerability: Vulnerability processing and remediation logic
- domains.agents: AI agent orchestration and management
- domains.analysis: Code analysis and build management
- domains.scm: Source control management abstractions
- domains.integrations: External service integrations
- domains.workflow: Workflow orchestration and execution
- extensions: Enhanced LLM integrations and extensions
- config: Configuration management and dependency injection
- telemetry: Telemetry collection and cost tracking
- shared: Shared utilities and common functionality

Example usage:
    ```python
    from smartfix import SmartFixAgent, SmartFixConfig
    from smartfix.extensions import SmartFixLiteLlm, SmartFixLlmAgent

    # Create configuration
    config = SmartFixConfig(
        llm_provider="anthropic",
        model="claude-3-sonnet-20240229"
    )

    # Create agent
    agent = SmartFixAgent(config=config)

    # Process vulnerability
    result = agent.process_vulnerability(
        repo_path="/path/to/repo",
        vulnerability_data=vuln_data,
        prompts=prompts
    )
    ```

For testing harness integration:
    ```python
    # Import the core agent for batch processing
    from smartfix import SmartFixAgent
    from smartfix.config import SmartFixConfig

    # Create agent in testing mode
    config = SmartFixConfig(testing_mode=True)
    agent = SmartFixAgent(config=config)

    # Batch process multiple vulnerabilities
    results = []
    for vuln in vulnerabilities:
        result = agent.process_vulnerability(
            repo_path=test_repo_path,
            vulnerability_data=vuln,
            prompts=prompts
        )
        results.append(result)
    ```
"""

__version__ = "1.0.0-dev"
__author__ = "Contrast Security"
__description__ = "AI-powered vulnerability remediation library"

# Core library exports - these will be available as components are implemented
__all__ = [
    # Metadata
    "__version__",
    "__author__",
    "__description__",

    # Core interfaces (to be implemented in later tasks)
    # "SmartFixAgent",           # Main agent interface
    # "SmartFixConfig",          # Configuration management
    # "CodingAgentStrategy",     # Agent strategy interface
    # "RemediationWorkflow",     # Workflow orchestration
    # "RemediationContext",      # Vulnerability context
    # "BuildResult",             # Build execution results
    # "ScmProvider",             # SCM abstraction interface
]

# Enhanced LLM extensions are already available
try:
    from .extensions import SmartFixLiteLlm, SmartFixLlmAgent  # noqa: F401
    __all__.extend(["SmartFixLiteLlm", "SmartFixLlmAgent"])
except ImportError:
    # Extensions may not be available in all environments
    pass

# Future imports will be added as components are implemented:
# from .domains.agents import SmartFixAgent, CodingAgentStrategy
# from .domains.workflow import RemediationWorkflow
# from .domains.vulnerability import RemediationContext
# from .domains.analysis import BuildResult
# from .domains.scm import ScmProvider
# from .config import SmartFixConfig

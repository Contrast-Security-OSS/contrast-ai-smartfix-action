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
"""

__version__ = "1.0.0-dev"
__author__ = "Contrast Security"
__description__ = "AI-powered vulnerability remediation library"

# Core library exports will be added as components are implemented
__all__ = [
    "__version__",
    "__author__",
    "__description__",
]

# TODO: Add core component exports as they are implemented:
# - SmartFixAgent
# - SmartFixConfig
# - CodingAgentStrategy
# - RemediationWorkflow
# - And other key interfaces

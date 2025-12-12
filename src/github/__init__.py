"""GitHub Provider Implementation

This package contains GitHub-specific implementations for the SmartFix system,
including SCM provider implementations, API clients, and GitHub Action integrations.

Key Components:
- GitHubScmProvider: GitHub implementation of the ScmProvider interface
- GitHubApiClient: GitHub API integration and operations
- ExternalCodingAgent: GitHub Copilot integration (moved from src/)
"""

# Import classes for easy access
try:
    from .external_coding_agent import ExternalCodingAgent  # noqa: F401
    __all__ = [
        "ExternalCodingAgent",
    ]
except ImportError:
    # During development, dependencies may not be available
    __all__ = []

# Import GitHub operations separately to avoid circular imports
try:
    from .github_operations import GitHubOperations  # noqa: F401
    __all__.append("GitHubOperations")
except ImportError:
    pass

# TODO: Add other GitHub components as they are implemented:
# - GitHubScmProvider
# - GitHubApiClient

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
    from .external_coding_agent import ExternalCodingAgent

    __all__ = [
        "ExternalCodingAgent",
    ]
except ImportError:
    # During development, dependencies may not be available
    __all__ = []

# TODO: Add other GitHub components as they are implemented:
# - GitHubScmProvider
# - GitHubApiClient

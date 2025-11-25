"""Source Control Management Domain

This domain provides SCM-agnostic abstractions for repository operations,
branch management, and pull request handling across different providers.

Key Components:
- GitOperations: Git command operations and repository management
- Repository: Repository operations and workspace management (to be implemented)
- PullRequest: Pull request lifecycle and metadata management (to be implemented)
- Branch: Branch operations and state tracking (to be implemented)
- ScmProvider: Abstract interface for SCM provider implementations (to be implemented)
"""

from .git_operations import GitOperations
from .scm_operations import ScmOperations

__all__ = [
    "GitOperations",
    "ScmOperations",
]

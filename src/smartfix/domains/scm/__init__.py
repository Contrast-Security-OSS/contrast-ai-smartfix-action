"""Source Control Management Domain

This domain provides SCM-agnostic abstractions for repository operations,
branch management, and pull request handling across different providers.

Key Components:
- GitOperations: Git command operations and repository management
- ScmOperations: Abstract interface for SCM provider implementations (such as GitHubOperations in `src/github`)
"""

from .git_operations import GitOperations
from .scm_operations import ScmOperations

__all__ = [
    "GitOperations",
    "ScmOperations",
]

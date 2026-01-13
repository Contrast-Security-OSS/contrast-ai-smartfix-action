"""
GitHub-specific constants for the SmartFix action.
"""

# GitHub API Limits
# GitHub recommends keeping PR/issue bodies under 65536 chars
# We use a conservative limit to ensure reliable delivery
GITHUB_MAX_PR_BODY_SIZE = 32000
GITHUB_MAX_ISSUE_BODY_SIZE = 32000

# GitHub API Query Limits
GITHUB_PR_LIST_LIMIT = 100
GITHUB_WORKFLOW_RUN_LIMIT = 50

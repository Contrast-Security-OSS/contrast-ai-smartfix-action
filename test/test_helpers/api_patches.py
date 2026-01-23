"""Shared patches for API integration tests.

This module provides reusable patch lists for testing Contrast API,
GitHub API, and handler functionality.
"""

# HTTP request patches - prevent actual network calls
HTTP_PATCHES = [
    'requests.get',
    'requests.post',
    'requests.put',
    'requests.delete',
    'requests.patch',
]

# Contrast API patches - prevent actual Contrast Security API calls
CONTRAST_API_PATCHES = [
    'src.contrast_api.fetch_prompt_details',
    'src.contrast_api.notify_remediation_opened',
    'src.contrast_api.notify_remediation_failed',
    'src.contrast_api.notify_remediation_merged',
    'src.contrast_api.check_credit_tracking',
]

# GitHub operations patches - prevent actual GitHub API calls
GITHUB_API_PATCHES = [
    'src.github.github_operations.GitHubOperations.create_pull_request',
    'src.github.github_operations.GitHubOperations.create_issue',
    'src.github.github_operations.GitHubOperations.find_issue_by_label',
    'src.github.github_operations.GitHubOperations.add_labels_to_pr',
    'src.github.github_operations.GitHubOperations.ensure_label_exists',
    'src.github.github_operations.GitHubOperations.get_pr_changed_files_count',
    'src.github.github_operations.run_command',  # For gh CLI commands
]

# Handler patches - prevent actual handler logic
HANDLER_PATCHES = [
    'src.handlers.merge_handler.handle_merged_pr',
    'src.handlers.closed_handler.handle_closed_pr',
    'src.handlers.closed_handler.extract_remediation_id_from_labels',
    'src.handlers.closed_handler.extract_remediation_id_from_branch',
]

# Combined API integration patches (all of the above)
API_INTEGRATION_PATCHES = (
    HTTP_PATCHES
    + CONTRAST_API_PATCHES
    + GITHUB_API_PATCHES
    + HANDLER_PATCHES
)

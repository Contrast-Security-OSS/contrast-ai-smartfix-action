# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2026 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security's commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

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

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
GitHub Status Check

Verifies that GitHub is fully operational before SmartFix runs.
SmartFix relies heavily on the GitHub CLI and API; any incident degrades
results and can produce misleading errors.
"""

import requests

from src.utils import debug_log, log, error_exit
from src.smartfix.shared.failure_categories import FailureCategory

GITHUB_STATUS_URL = "https://www.githubstatus.com/api/v2/status.json"
REQUEST_TIMEOUT_SECONDS = 5


def check_github_status() -> None:
    """
    Abort if GitHub is reporting any active incident.

    Fetches https://www.githubstatus.com/api/v2/status.json and checks the
    top-level indicator.  Any indicator other than 'none' means GitHub is
    experiencing problems and SmartFix exits immediately with a clear message.

    If the status API itself is unreachable (network error, timeout, etc.)
    the check is skipped and SmartFix continues — we do not add a new failure
    mode for an unavailable status page.

    Uses error_exit() so that the failure is reported back to the Contrast
    telemetry/remediation service before the process exits.
    """
    try:
        response = requests.get(GITHUB_STATUS_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        debug_log(f"GitHub status API unreachable ({e}). Skipping status check.")
        return

    status = data.get("status", {})
    indicator = status.get("indicator", "none")
    description = status.get("description", "Unknown")

    if indicator == "none":
        debug_log(f"GitHub status: {description}")
        return

    log(f"GitHub is currently reporting an incident: {description} (severity: {indicator})")
    log("SmartFix depends on the GitHub CLI and API. Running during an incident")
    log("can produce incorrect results or misleading errors.")
    log("See https://www.githubstatus.com/ for details and try again once the incident is resolved.")
    error_exit("unknown", FailureCategory.GENERAL_FAILURE.value)

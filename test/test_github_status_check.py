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
Tests for github_status_check.py

Covers:
- indicator="none"  → proceeds without exit
- indicator="minor"|"major"|"critical" → error_exit() called with GENERAL_FAILURE
- Network/timeout errors → proceeds without exit (best-effort)
"""

import unittest
from unittest.mock import patch, MagicMock

from src.github_status_check import check_github_status
from src.smartfix.shared.failure_categories import FailureCategory


def _make_response(indicator: str, description: str = "All Systems Operational") -> MagicMock:
    """Build a mock requests.Response for the status API."""
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "status": {"indicator": indicator, "description": description}
    }
    return response


class TestCheckGithubStatus(unittest.TestCase):

    def setUp(self):
        self.requests_patcher = patch('src.github_status_check.requests')
        self.mock_requests = self.requests_patcher.start()
        self.mock_requests.exceptions.RequestException = Exception

        self.log_patcher = patch('src.github_status_check.log')
        self.mock_log = self.log_patcher.start()

        self.debug_log_patcher = patch('src.github_status_check.debug_log')
        self.mock_debug_log = self.debug_log_patcher.start()

        self.error_exit_patcher = patch('src.github_status_check.error_exit')
        self.mock_error_exit = self.error_exit_patcher.start()

    def tearDown(self):
        self.requests_patcher.stop()
        self.log_patcher.stop()
        self.debug_log_patcher.stop()
        self.error_exit_patcher.stop()

    # --- Healthy (indicator="none") ---

    def test_all_operational_does_not_exit(self):
        """When indicator is 'none', check_github_status returns normally."""
        self.mock_requests.get.return_value = _make_response("none", "All Systems Operational")
        check_github_status()
        self.mock_error_exit.assert_not_called()

    def test_all_operational_does_not_log_warning(self):
        """When indicator is 'none', no warning is logged to the user."""
        self.mock_requests.get.return_value = _make_response("none")
        check_github_status()
        self.mock_log.assert_not_called()

    def test_all_operational_calls_correct_url(self):
        """Status check hits the githubstatus.com API endpoint."""
        self.mock_requests.get.return_value = _make_response("none")
        check_github_status()
        call_args = self.mock_requests.get.call_args
        self.assertIn("githubstatus.com", call_args[0][0])

    # --- Incidents (indicator != "none") ---

    def test_minor_incident_calls_error_exit(self):
        """A 'minor' indicator calls error_exit with GENERAL_FAILURE."""
        self.mock_requests.get.return_value = _make_response("minor", "Minor Service Disruption")
        check_github_status()
        self.mock_error_exit.assert_called_once_with("unknown", FailureCategory.GENERAL_FAILURE.value)

    def test_major_incident_calls_error_exit(self):
        """A 'major' indicator calls error_exit with GENERAL_FAILURE."""
        self.mock_requests.get.return_value = _make_response("major", "Partial System Outage")
        check_github_status()
        self.mock_error_exit.assert_called_once_with("unknown", FailureCategory.GENERAL_FAILURE.value)

    def test_critical_incident_calls_error_exit(self):
        """A 'critical' indicator calls error_exit with GENERAL_FAILURE."""
        self.mock_requests.get.return_value = _make_response("critical", "Major System Outage")
        check_github_status()
        self.mock_error_exit.assert_called_once_with("unknown", FailureCategory.GENERAL_FAILURE.value)

    def test_incident_logs_description(self):
        """The incident description from the API is included in the log output."""
        description = "Partial System Outage"
        self.mock_requests.get.return_value = _make_response("major", description)
        check_github_status()
        logged_text = " ".join(str(c) for c in self.mock_log.call_args_list)
        self.assertIn(description, logged_text)

    def test_incident_log_mentions_githubstatus_url(self):
        """The exit message directs users to githubstatus.com."""
        self.mock_requests.get.return_value = _make_response("minor", "Disruption")
        check_github_status()
        logged_text = " ".join(str(c) for c in self.mock_log.call_args_list)
        self.assertIn("githubstatus.com", logged_text)

    # --- Network failures (best-effort: proceed) ---

    def test_network_error_does_not_call_error_exit(self):
        """A network error reaching the status API is treated as a no-op."""
        self.mock_requests.get.side_effect = Exception("connection refused")
        check_github_status()
        self.mock_error_exit.assert_not_called()

    def test_timeout_does_not_call_error_exit(self):
        """A timeout reaching the status API is treated as a no-op."""
        self.mock_requests.get.side_effect = Exception("timed out")
        check_github_status()
        self.mock_error_exit.assert_not_called()

    def test_network_error_does_not_log_warning_to_user(self):
        """Network failures are debug-logged only, not surfaced as user-visible warnings."""
        self.mock_requests.get.side_effect = Exception("connection refused")
        check_github_status()
        self.mock_log.assert_not_called()

    def test_http_error_does_not_call_error_exit(self):
        """An HTTP error response from the status API is treated as a no-op."""
        self.mock_requests.get.side_effect = Exception("503 Service Unavailable")
        check_github_status()
        self.mock_error_exit.assert_not_called()

    # --- Request parameters ---

    def test_uses_timeout(self):
        """Request is made with a timeout to avoid hanging the action."""
        self.mock_requests.get.return_value = _make_response("none")
        check_github_status()
        call_kwargs = self.mock_requests.get.call_args[1]
        self.assertIn("timeout", call_kwargs)
        self.assertGreater(call_kwargs["timeout"], 0)


if __name__ == '__main__':
    unittest.main()

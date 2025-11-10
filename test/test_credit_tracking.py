#!/usr/bin/env python3
# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
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

import unittest

from src.smartfix.domains.workflow.credit_tracking import CreditTrackingResponse


class TestCreditTrackingResponse(unittest.TestCase):
    """Test cases for CreditTrackingResponse dataclass."""

    def setUp(self):
        """Set up test data before each test."""
        self.sample_api_data = {
            "organizationId": "12345678-1234-1234-1234-123456789abc",
            "enabled": True,
            "maxCredits": 50,
            "creditsUsed": 7,
            "startDate": "2024-10-01T14:30:00Z",
            "endDate": "2024-11-12T14:30:00Z"
        }

        self.disabled_api_data = {
            "organizationId": "87654321-4321-4321-4321-cba987654321",
            "enabled": False,
            "maxCredits": 0,
            "creditsUsed": 0,
            "startDate": "",
            "endDate": ""
        }

    def test_from_api_response(self):
        """Test creating instance from API response data."""
        response = CreditTrackingResponse.from_api_response(self.sample_api_data)

        self.assertEqual(response.organization_id, "12345678-1234-1234-1234-123456789abc")
        self.assertTrue(response.enabled)
        self.assertEqual(response.max_credits, 50)
        self.assertEqual(response.credits_used, 7)
        self.assertEqual(response.start_date, "2024-10-01T14:30:00Z")
        self.assertEqual(response.end_date, "2024-11-12T14:30:00Z")

    def test_credits_remaining_property(self):
        """Test that credits_remaining calculates available credits correctly."""
        response = CreditTrackingResponse.from_api_response(self.sample_api_data)
        self.assertEqual(response.credits_remaining, 43)  # 50 - 7

        # Test calculation with different usage levels
        response.credits_used = 25
        self.assertEqual(response.credits_remaining, 25)  # 50 - 25

        response.credits_used = 50
        self.assertEqual(response.credits_remaining, 0)  # 50 - 50

    def test_to_log_message_enabled(self):
        """Test log message formatting when enabled."""
        response = CreditTrackingResponse.from_api_response(self.sample_api_data)
        message = response.to_log_message()

        expected = "Free trial credits: 7/50 used (43 remaining). Trial expires 2024-11-12T14:30:00Z"
        self.assertEqual(message, expected)

    def test_to_log_message_disabled(self):
        """Test log message formatting when disabled."""
        response = CreditTrackingResponse.from_api_response(self.disabled_api_data)
        message = response.to_log_message()

        expected = "Credit tracking is disabled for this organization"
        self.assertEqual(message, expected)

    def test_to_pr_body_section_enabled(self):
        """Test PR body section formatting when enabled."""
        response = CreditTrackingResponse.from_api_response(self.sample_api_data)
        pr_section = response.to_pr_body_section()

        self.assertIn("### Contrast LLM Free Trial Credits", pr_section)
        self.assertIn("**Used:** 7/50", pr_section)
        self.assertIn("**Remaining:** 43", pr_section)
        self.assertIn("**Trial Period:** 2024-10-01T14:30:00Z to 2024-11-12T14:30:00Z", pr_section)
        self.assertTrue(pr_section.startswith("\n---\n"))

    def test_to_pr_body_section_disabled(self):
        """Test PR body section formatting when disabled."""
        response = CreditTrackingResponse.from_api_response(self.disabled_api_data)
        pr_section = response.to_pr_body_section()

        self.assertEqual(pr_section, "")

    def test_with_incremented_usage(self):
        """Test creating copy with incremented usage."""
        original = CreditTrackingResponse.from_api_response(self.sample_api_data)
        incremented = original.with_incremented_usage()

        # Original should be unchanged
        self.assertEqual(original.credits_used, 7)
        self.assertEqual(original.credits_remaining, 43)

        # Incremented should have +1 usage
        self.assertEqual(incremented.credits_used, 8)
        self.assertEqual(incremented.credits_remaining, 42)

        # Other fields should be identical
        self.assertEqual(incremented.organization_id, original.organization_id)
        self.assertEqual(incremented.enabled, original.enabled)
        self.assertEqual(incremented.max_credits, original.max_credits)
        self.assertEqual(incremented.start_date, original.start_date)
        self.assertEqual(incremented.end_date, original.end_date)

    def test_with_incremented_usage_at_limit(self):
        """Test incrementing usage when already at max credits."""
        data = self.sample_api_data.copy()
        data["creditsUsed"] = 50

        original = CreditTrackingResponse.from_api_response(data)
        incremented = original.with_incremented_usage()

        self.assertEqual(original.credits_used, 50)
        self.assertEqual(original.credits_remaining, 0)

        self.assertEqual(incremented.credits_used, 51)
        self.assertEqual(incremented.credits_remaining, -1)

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Test zero credits used
        data = self.sample_api_data.copy()
        data["creditsUsed"] = 0

        response = CreditTrackingResponse.from_api_response(data)
        self.assertEqual(response.credits_remaining, 50)

        log_msg = response.to_log_message()
        self.assertIn("0/50 used (50 remaining)", log_msg)

        # Test empty dates
        data["startDate"] = ""
        data["endDate"] = ""

        response = CreditTrackingResponse.from_api_response(data)
        pr_section = response.to_pr_body_section()
        self.assertIn("**Trial Period:**  to ", pr_section)


if __name__ == '__main__':
    unittest.main()

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

"""Credit tracking data models and utilities for Contrast LLM usage."""

from dataclasses import dataclass


@dataclass
class CreditTrackingResponse:
    """Response model for credit tracking API."""
    organization_id: str
    enabled: bool
    max_credits: int
    credits_used: int
    start_date: str
    end_date: str

    @property
    def credits_remaining(self) -> int:
        """Calculate remaining credits."""
        return self.max_credits - self.credits_used

    def to_log_message(self) -> str:
        """Format credit information for log output."""
        if not self.enabled:
            return "Credit tracking is disabled for this organization"

        return (f"Free trial credits: {self.credits_used}/{self.max_credits} used "
                f"({self.credits_remaining} remaining). Trial expires {self.end_date}")

    def to_pr_body_section(self) -> str:
        """Format credit information for PR body append."""
        if not self.enabled:
            return ""

        return f"""
---
### Contrast LLM Free Trial Credits
- **Used:** {self.credits_used}/{self.max_credits}
- **Remaining:** {self.credits_remaining}
- **Trial Period:** {self.start_date} to {self.end_date}
"""

    @classmethod
    def from_api_response(cls, response_data: dict) -> 'CreditTrackingResponse':
        """Create instance from API response data."""
        return cls(
            organization_id=response_data['organizationId'],
            enabled=response_data['enabled'],
            max_credits=response_data['maxCredits'],
            credits_used=response_data['creditsUsed'],
            start_date=response_data['startDate'],
            end_date=response_data['endDate']
        )

    def with_incremented_usage(self) -> 'CreditTrackingResponse':
        """Return a copy with credits_used incremented by 1."""
        return CreditTrackingResponse(
            organization_id=self.organization_id,
            enabled=self.enabled,
            max_credits=self.max_credits,
            credits_used=self.credits_used + 1,
            start_date=self.start_date,
            end_date=self.end_date
        )

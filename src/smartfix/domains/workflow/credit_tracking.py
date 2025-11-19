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
from datetime import datetime


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

    @property
    def is_exhausted(self) -> bool:
        """Check if credits are exhausted."""
        return self.credits_remaining <= 0

    @property
    def is_low(self) -> bool:
        """Check if credits are running low (5 or fewer remaining)."""
        return self.credits_remaining <= 5 and self.credits_remaining > 0

    def _format_timestamp(self, iso_timestamp: str) -> str:
        """Format ISO timestamp to human-readable format."""
        if not iso_timestamp:
            return "Unknown"

        try:
            # Parse ISO format timestamp (e.g., "2025-10-30T01:00:00Z")
            dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
            # Format as "Oct 30, 2025"
            return dt.strftime("%b %d, %Y")
        except (ValueError, AttributeError):
            # If parsing fails, return the original timestamp
            return iso_timestamp

    def to_log_message(self) -> str:
        """Format credit information for log output."""
        if not self.enabled:
            return "Credit tracking is disabled for this organization"

        return (f"Credits: {self.credits_used}/{self.max_credits} used "
                f"({self.credits_remaining} remaining). Trial expires {self.end_date}")

    def get_credit_warning_message(self) -> str:
        """Get warning message for credit status, with color formatting."""
        if self.is_exhausted:
            return "Credits have been exhausted. Contact your CSM to request additional credits."
        elif self.is_low:
            # Yellow text formatting for low credits warning
            return f"\033[0;33m{self.credits_remaining} credits remaining \033[0m"
        return ""

    def should_log_warning(self) -> bool:
        """Check if a warning should be logged."""
        return self.is_exhausted or self.is_low

    def to_pr_body_section(self) -> str:
        """Format credit information for PR body append."""
        if not self.enabled:
            return ""

        start_formatted = self._format_timestamp(self.start_date)
        end_formatted = self._format_timestamp(self.end_date)

        return f"""
---
### Contrast LLM Credits
- **Used:** {self.credits_used}/{self.max_credits}
- **Remaining:** {self.credits_remaining}
- **Trial Period:** {start_formatted} to {end_formatted}
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

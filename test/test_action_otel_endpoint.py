#!/usr/bin/env python
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

import subprocess
import unittest

# The shell normalization logic extracted from action.yml "Set OTel defaults" step.
# Must be kept in sync with that step if the logic changes.
_NORMALIZE_SHELL = """
HOST="${INPUT_CONTRAST_HOST}"
HOST="${HOST//https:\\/\\//}"
HOST="${HOST//http:\\/\\//}"
while [ "${HOST%/}" != "${HOST}" ]; do
  HOST="${HOST%/}"
done
echo "https://${HOST}/aiml/otel"
"""


def _normalize_via_shell(contrast_host: str) -> str:
    result = subprocess.run(
        ["bash", "-c", _NORMALIZE_SHELL],
        env={"INPUT_CONTRAST_HOST": contrast_host},
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class TestActionOtelEndpoint(unittest.TestCase):
    """Tests for the OTel endpoint shell normalization in action.yml."""

    def test_plain_hostname(self):
        self.assertEqual(_normalize_via_shell("example.com"), "https://example.com/aiml/otel")

    def test_https_prefix_stripped(self):
        self.assertEqual(_normalize_via_shell("https://example.com"), "https://example.com/aiml/otel")

    def test_http_prefix_stripped(self):
        self.assertEqual(_normalize_via_shell("http://example.com"), "https://example.com/aiml/otel")

    def test_single_trailing_slash_stripped(self):
        self.assertEqual(_normalize_via_shell("https://example.com/"), "https://example.com/aiml/otel")

    def test_multiple_trailing_slashes_stripped(self):
        self.assertEqual(_normalize_via_shell("https://example.com///"), "https://example.com/aiml/otel")

    def test_double_scheme_stripped(self):
        self.assertEqual(_normalize_via_shell("http://https://example.com"), "https://example.com/aiml/otel")

    def test_double_https_scheme_stripped(self):
        self.assertEqual(_normalize_via_shell("https://https://example.com"), "https://example.com/aiml/otel")

    def test_hostname_with_port(self):
        self.assertEqual(_normalize_via_shell("https://example.com:8080"), "https://example.com:8080/aiml/otel")

    def test_hostname_only_no_trailing_slash(self):
        self.assertEqual(_normalize_via_shell("example.com"), "https://example.com/aiml/otel")


if __name__ == "__main__":
    unittest.main()

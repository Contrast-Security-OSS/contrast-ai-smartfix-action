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

import unittest

# Test setup imports (path is set up by conftest.py)
from src.utils import normalize_host


class TestNormalizeHost(unittest.TestCase):
    """Tests for the normalize_host function in utils.py"""

    def test_normalize_host_with_https(self):
        """Test that https:// prefix is removed"""
        input_host = "https://example.com"
        expected = "example.com"
        result = normalize_host(input_host)
        self.assertEqual(result, expected)

    def test_normalize_host_with_http(self):
        """Test that http:// prefix is removed"""
        input_host = "http://example.com"
        expected = "example.com"
        result = normalize_host(input_host)
        self.assertEqual(result, expected)

    def test_normalize_host_without_protocol(self):
        """Test that host without protocol is unchanged"""
        input_host = "example.com"
        expected = "example.com"
        result = normalize_host(input_host)
        self.assertEqual(result, expected)

    def test_normalize_host_with_port(self):
        """Test that host with port works correctly"""
        input_host = "https://example.com:8080"
        expected = "example.com:8080"
        result = normalize_host(input_host)
        self.assertEqual(result, expected)

    def test_normalize_host_with_path(self):
        """Test that host with path works correctly"""
        input_host = "https://example.com/api/v1"
        expected = "example.com/api/v1"
        result = normalize_host(input_host)
        self.assertEqual(result, expected)

    def test_normalize_host_with_subdomain(self):
        """Test that host with subdomain works correctly"""
        input_host = "https://api.example.com"
        expected = "api.example.com"
        result = normalize_host(input_host)
        self.assertEqual(result, expected)

    def test_normalize_host_multiple_protocols(self):
        """Test that multiple protocol prefixes are handled correctly"""
        input_host = "http://https://example.com"
        expected = "example.com"
        result = normalize_host(input_host)
        self.assertEqual(result, expected)

    def test_normalize_host_empty_string(self):
        """Test that empty string is handled correctly"""
        input_host = ""
        expected = ""
        result = normalize_host(input_host)
        self.assertEqual(result, expected)

    def test_normalize_host_protocol_in_middle(self):
        """Test that protocol in middle of string is also removed"""
        input_host = "example.com/https://path"
        expected = "example.com/path"
        result = normalize_host(input_host)
        self.assertEqual(result, expected)


if __name__ == '__main__':
    unittest.main()

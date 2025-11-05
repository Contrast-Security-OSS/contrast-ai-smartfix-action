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
from unittest.mock import patch, MagicMock

# Test setup imports (path is set up by conftest.py)
from src.config import get_config, reset_config
from src.smartfix.extensions.smartfix_litellm import SmartFixLiteLlm


class TestSmartFixLiteLlmContrast(unittest.TestCase):
    """Tests for the SmartFixLiteLlm Contrast model functionality"""

    def setUp(self):
        """Set up test fixtures before each test method."""
        reset_config()  # Reset the config singleton
        get_config(testing=True)  # Initialize with testing config
        self.system_prompt = "You are a security assistant."

        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            self.model = SmartFixLiteLlm(
                model="contrast/claude-sonnet-4-5",
                system=self.system_prompt
            )

    def tearDown(self):
        """Clean up after each test"""
        reset_config()

    def test_init_with_system_prompt(self):
        """Test that SmartFixLiteLlm initializes correctly with system prompt"""
        self.assertEqual(self.model._system_prompt, self.system_prompt)
        self.assertEqual(self.model.model, "contrast/claude-sonnet-4-5")

    def test_init_without_system_prompt(self):
        """Test that SmartFixLiteLlm initializes correctly without system prompt"""
        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            model = SmartFixLiteLlm(model="contrast/claude-sonnet-4-5")
        self.assertIsNone(model._system_prompt)

    def test_ensure_system_message_no_system_no_developer(self):
        """Test adding system message when no system or developer messages exist"""
        messages = [
            {'role': 'user', 'content': 'Hello'}
        ]

        result = self.model._ensure_system_message_for_contrast(messages)

        # Should have: system message, original user message (no decoy developer needed)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['role'], 'system')
        self.assertEqual(result[0]['content'], self.system_prompt)
        self.assertEqual(result[1]['role'], 'user')
        self.assertEqual(result[1]['content'], 'Hello')

    def test_ensure_system_message_has_developer_no_system(self):
        """Test adding system message when developer exists but no system message"""
        messages = [
            {'role': 'developer', 'content': 'Original developer message'},
            {'role': 'user', 'content': 'Hello'}
        ]

        result = self.model._ensure_system_message_for_contrast(messages)

        # Should have: system message, decoy developer, user message (original developer filtered out)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['role'], 'system')
        self.assertEqual(result[0]['content'], self.system_prompt)
        self.assertEqual(result[1]['role'], 'developer')
        self.assertEqual(result[1]['content'], [{'type': 'text', 'text': ''}])
        self.assertEqual(result[2]['role'], 'user')
        self.assertEqual(result[2]['content'], 'Hello')

    def test_ensure_system_message_has_system(self):
        """Test that existing system message is preserved"""
        messages = [
            {'role': 'system', 'content': 'Existing system'},
            {'role': 'user', 'content': 'Hello'}
        ]

        result = self.model._ensure_system_message_for_contrast(messages)

        # Should return unchanged messages
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['role'], 'system')
        self.assertEqual(result[0]['content'], 'Existing system')
        self.assertEqual(result[1]['role'], 'user')
        self.assertEqual(result[1]['content'], 'Hello')

    def test_ensure_system_message_filters_multiple_developers(self):
        """Test that multiple developer messages are filtered out"""
        messages = [
            {'role': 'developer', 'content': 'Dev message 1'},
            {'role': 'developer', 'content': 'Dev message 2'},
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Response'}
        ]

        result = self.model._ensure_system_message_for_contrast(messages)

        # Should have: system message, decoy developer, user message, assistant message
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]['role'], 'system')
        self.assertEqual(result[1]['role'], 'developer')
        self.assertEqual(result[1]['content'], [{'type': 'text', 'text': ''}])
        self.assertEqual(result[2]['role'], 'user')
        self.assertEqual(result[3]['role'], 'assistant')

    def test_ensure_system_message_no_system_prompt(self):
        """Test behavior when no system prompt is available"""
        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            model = SmartFixLiteLlm(model="contrast/claude-sonnet-4-5")  # No system prompt
        messages = [{'role': 'user', 'content': 'Hello'}]

        result = model._ensure_system_message_for_contrast(messages)

        # Should return unchanged messages
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['role'], 'user')

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_ensure_system_message_debug_logging(self, mock_debug_log):
        """Test that appropriate debug messages are logged"""
        messages = [
            {'role': 'developer', 'content': 'Dev message'},
            {'role': 'user', 'content': 'Hello'}
        ]

        self.model._ensure_system_message_for_contrast(messages)

        # Verify debug logging calls
        mock_debug_log.assert_any_call("Message analysis: has_system=False, has_developer=True")
        mock_debug_log.assert_any_call("Developer message found but no system message, adding system message for Contrast")

    @unittest.skip("Integration test fails due to circular import issues - use mock tests instead")
    def test_apply_role_conversion_and_caching_contrast_model(self):
        """Test that Contrast models get proper caching without role conversion"""
        pass

    def test_message_object_handling(self):
        """Test handling of message objects (not just dicts)"""
        # Create mock message objects
        user_message = MagicMock()
        user_message.role = 'user'
        user_message.__dict__ = {'role': 'user', 'content': 'Hello'}

        messages = [user_message]

        result = self.model._ensure_system_message_for_contrast(messages)

        # Should add system message (no decoy developer needed when no existing developer messages)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['role'], 'system')
        # Original object should be preserved
        self.assertEqual(result[1], user_message)


if __name__ == '__main__':
    unittest.main()

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
from src.smartfix.domains.providers import CONTRAST_CLAUDE_SONNET_4_5


class TestSmartFixLiteLlmContrast(unittest.TestCase):
    """Tests for the SmartFixLiteLlm Contrast model functionality"""

    def setUp(self):
        """Set up test fixtures before each test method."""
        reset_config()  # Reset the config singleton
        get_config(testing=True)  # Initialize with testing config
        self.system_prompt = "You are a security assistant."

        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            self.model = SmartFixLiteLlm(
                model=CONTRAST_CLAUDE_SONNET_4_5,
                system=self.system_prompt
            )

    def tearDown(self):
        """Clean up after each test"""
        reset_config()

    def test_init_with_system_prompt(self):
        """Test that SmartFixLiteLlm initializes correctly with system prompt"""
        self.assertEqual(self.model._system_prompt, self.system_prompt)
        self.assertEqual(self.model.model, CONTRAST_CLAUDE_SONNET_4_5)

    def test_init_without_system_prompt(self):
        """Test that SmartFixLiteLlm initializes correctly without system prompt"""
        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            model = SmartFixLiteLlm(model=CONTRAST_CLAUDE_SONNET_4_5)
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
            model = SmartFixLiteLlm(model=CONTRAST_CLAUDE_SONNET_4_5)  # No system prompt
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

    def test_add_cache_control_skipped_when_contrast_llm_enabled(self):
        """Test that _add_cache_control_to_message skips when USE_CONTRAST_LLM is True"""
        # Default test config has USE_CONTRAST_LLM=True
        message = {
            'role': 'user',
            'content': 'Test message'
        }
        original_content = message['content']

        self.model._add_cache_control_to_message(message)

        # Content should remain unchanged (string, not converted to array with cache_control)
        self.assertEqual(message['content'], original_content)
        self.assertIsInstance(message['content'], str)

    @patch.dict('os.environ', {'USE_CONTRAST_LLM': 'false', 'ENABLE_ANTHROPIC_PROMPT_CACHING': 'true'})
    def test_add_cache_control_applied_when_contrast_llm_disabled(self):
        """Test that _add_cache_control_to_message applies caching when USE_CONTRAST_LLM is False"""
        reset_config()
        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            model = SmartFixLiteLlm(model="anthropic/claude-sonnet-4-5")

        message = {
            'role': 'user',
            'content': 'Test message'
        }

        model._add_cache_control_to_message(message)

        # Content should be converted to array format with cache_control
        self.assertIsInstance(message['content'], list)
        self.assertEqual(len(message['content']), 1)
        self.assertEqual(message['content'][0]['type'], 'text')
        self.assertEqual(message['content'][0]['text'], 'Test message')
        self.assertIn('cache_control', message['content'][0])
        self.assertEqual(message['content'][0]['cache_control']['type'], 'ephemeral')

    @patch.dict('os.environ', {'USE_CONTRAST_LLM': 'false', 'ENABLE_ANTHROPIC_PROMPT_CACHING': 'false'})
    def test_add_cache_control_skipped_when_caching_disabled(self):
        """Test that _add_cache_control_to_message skips when ENABLE_ANTHROPIC_PROMPT_CACHING is False"""
        reset_config()
        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            model = SmartFixLiteLlm(model="anthropic/claude-sonnet-4-5")

        message = {
            'role': 'user',
            'content': 'Test message'
        }
        original_content = message['content']

        model._add_cache_control_to_message(message)

        # Content should remain unchanged (caching disabled)
        self.assertEqual(message['content'], original_content)
        self.assertIsInstance(message['content'], str)


if __name__ == '__main__':
    unittest.main()

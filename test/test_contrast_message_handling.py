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
# the applicable End User License Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackage, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

import unittest
from unittest.mock import MagicMock

# Import just the function we need to test, avoiding full class initialization
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class MockSmartFixLiteLlm:
    """Mock version of SmartFixLiteLlm for testing message handling logic"""

    def __init__(self, system_prompt=None):
        self._system_prompt = system_prompt

    def _ensure_system_message_for_contrast(self, messages):
        """Copy of the actual method for testing"""
        system_prompt = self._system_prompt
        if not system_prompt:
            return messages

        # Check if we have any system message
        has_system = False
        has_developer = False

        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get('role')
            elif hasattr(msg, 'role'):
                role = getattr(msg, 'role')
            else:
                continue

            if role == 'system':
                has_system = True
            elif role == 'developer':
                has_developer = True

        # For Contrast models, ensure we have system message and remove any developer messages
        if not has_system and not has_developer:
            system_message = {
                'role': 'system',
                'content': system_prompt
            }
            messages = [system_message] + list(messages)
        elif not has_system and has_developer:
            # Add system message with actual prompt
            system_message = {
                'role': 'system',
                'content': system_prompt
            }
            # Add decoy developer message to prevent LiteLLM from moving system message
            decoy_developer = {
                'role': 'developer',
                'content': [{'type': 'text', 'text': ''}]
            }

            # Filter out original developer messages to avoid duplicates
            filtered_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    role = msg.get('role')
                elif hasattr(msg, 'role'):
                    role = getattr(msg, 'role')
                else:
                    role = None

                # Skip developer messages - we'll use our decoy instead
                if role != 'developer':
                    filtered_messages.append(msg)

            messages = [system_message, decoy_developer] + filtered_messages

        return messages


class TestContrastMessageHandling(unittest.TestCase):
    """Tests for Contrast-specific message handling logic"""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.system_prompt = "You are a security assistant."
        self.model = MockSmartFixLiteLlm(system_prompt=self.system_prompt)

    def test_ensure_system_message_no_system_no_developer(self):
        """Test adding system message when no system or developer messages exist"""
        messages = [
            {'role': 'user', 'content': 'Hello'}
        ]

        result = self.model._ensure_system_message_for_contrast(messages)

        # Should have: system message, original user message
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
        model = MockSmartFixLiteLlm()  # No system prompt
        messages = [{'role': 'user', 'content': 'Hello'}]

        result = model._ensure_system_message_for_contrast(messages)
        # Should return unchanged messages
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['role'], 'user')

    def test_message_object_handling(self):
        """Test handling of message objects (not just dicts)"""
        # Create mock message objects
        user_message = MagicMock()
        user_message.role = 'user'
        messages = [user_message]

        result = self.model._ensure_system_message_for_contrast(messages)

        # Should add system message
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['role'], 'system')
        # Original object should be preserved
        self.assertEqual(result[1], user_message)

    def test_decoy_developer_format(self):
        """Test that decoy developer message has correct format"""
        messages = [
            {'role': 'developer', 'content': 'Some content'},
            {'role': 'user', 'content': 'Hello'}
        ]

        result = self.model._ensure_system_message_for_contrast(messages)

        # Check decoy developer message format
        decoy = result[1]
        self.assertEqual(decoy['role'], 'developer')
        self.assertEqual(decoy['content'], [{'type': 'text', 'text': ''}])
        self.assertIsInstance(decoy['content'], list)
        self.assertEqual(len(decoy['content']), 1)
        self.assertEqual(decoy['content'][0]['type'], 'text')
        self.assertEqual(decoy['content'][0]['text'], '')


if __name__ == '__main__':
    unittest.main()

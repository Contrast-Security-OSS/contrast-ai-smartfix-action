"""
Unit tests for litellm_caching.py

This test suite covers:
- Provider support detection
- Cache control application
- Graceful fallback behavior
- Logging behavior
- Model instantiation for all provider types
"""

import unittest
from unittest.mock import Mock, patch

# Import the classes we're testing
from src.extensions.extended_litellm import ExtendedLiteLlm


class TestExtendedLiteLlm(unittest.TestCase):
    """Test suite for ExtendedLiteLlm class."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the logging functions
        self.mock_log = Mock()
        self.mock_debug_log = Mock()

        # Patch the logging functions in the module
        self.log_patcher = patch('src.extensions.extended_litellm.log', self.mock_log)
        self.debug_log_patcher = patch('src.extensions.extended_litellm.debug_log', self.mock_debug_log)

        self.log_patcher.start()
        self.debug_log_patcher.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.log_patcher.stop()
        self.debug_log_patcher.stop()

    def get_log_calls(self):
        """Get the captured log calls."""
        return {
            'log': self.mock_log.call_args_list,
            'debug_log': self.mock_debug_log.call_args_list
        }

    def test_init_with_caching_enabled(self):
        """Test initialization with caching enabled."""
        model = ExtendedLiteLlm(
            model="anthropic/claude-3-5-sonnet-20240620",
            cache_system_instruction=True,
            temperature=0.2
        )

        self.assertEqual(model.model, "anthropic/claude-3-5-sonnet-20240620")
        self.assertTrue(model.cache_system_instruction)
        self.assertEqual(model.cache_control_type, "ephemeral")

        # Should log that caching is enabled
        log_output = self.get_log_output()
        self.assertIn("Prompt caching enabled", log_output)
        self.assertIn("anthropic/claude-3-5-sonnet-20240620", log_output)

    def test_init_with_caching_disabled(self):
        """Test initialization with caching disabled."""
        model = ExtendedLiteLlm(
            model="openai/gpt-4o",
            cache_system_instruction=False,
            temperature=0.2
        )

        self.assertEqual(model.model, "openai/gpt-4o")
        self.assertFalse(model.cache_system_instruction)

        # Should not log anything about caching
        log_output = self.get_log_output()
        self.assertNotIn("Prompt caching enabled", log_output)

    def test_supports_caching_openai(self):
        """Test caching support detection for OpenAI models."""
        model = ExtendedLiteLlm(model="openai/gpt-4o", cache_system_instruction=True)
        self.assertTrue(model._supports_caching())

    def test_supports_caching_azure_openai(self):
        """Test caching support detection for Azure OpenAI models."""
        model = ExtendedLiteLlm(model="azure/gpt-4o", cache_system_instruction=True)
        self.assertTrue(model._supports_caching())

    def test_supports_caching_anthropic(self):
        """Test caching support detection for Anthropic models."""
        model = ExtendedLiteLlm(model="anthropic/claude-3-5-sonnet-20240620", cache_system_instruction=True)
        self.assertTrue(model._supports_caching())

    def test_supports_caching_bedrock(self):
        """Test caching support detection for Bedrock models."""
        model = ExtendedLiteLlm(model="bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0", cache_system_instruction=True)
        self.assertTrue(model._supports_caching())

    def test_supports_caching_gemini_fallback(self):
        """Test graceful fallback for Gemini models."""
        model = ExtendedLiteLlm(model="gemini-1.5-pro", cache_system_instruction=True)
        self.assertFalse(model._supports_caching())

        # Should log info message about lack of caching support
        log_output = self.get_log_output()
        self.assertIn("doesn't support prompt caching", log_output)
        self.assertIn("will work normally without it", log_output)

    def test_supports_caching_deepseek_policy_block(self):
        """Test that Deepseek models are blocked due to policy."""
        model = ExtendedLiteLlm(model="deepseek/deepseek-chat", cache_system_instruction=True)
        self.assertFalse(model._supports_caching())

        # Should log specific policy message
        log_output = self.get_log_output()
        self.assertIn("not supported due to policy restrictions", log_output)
        self.assertIn("deepseek/deepseek-chat", log_output)

    def test_supports_caching_disabled(self):
        """Test that caching support check doesn't log when caching is disabled."""
        model = ExtendedLiteLlm(model="gemini-1.5-pro", cache_system_instruction=False)
        result = model._supports_caching()

        # Should return False but not log anything
        self.assertFalse(result)
        log_output = self.get_log_output()
        self.assertNotIn("doesn't support prompt caching", log_output)

    @patch('litellm_caching.ExtendedLiteLlm._add_anthropic_style_cache_control')
    def test_add_cache_control_anthropic(self, mock_add_anthropic):
        """Test cache control application for Anthropic models."""
        model = ExtendedLiteLlm(model="anthropic/claude-3-5-sonnet-20240620", cache_system_instruction=True)

        completion_args = {
            "messages": [Mock(role="developer", content="test content")]
        }

        model._add_cache_control(completion_args)

        # Should call the Anthropic-specific cache control method
        mock_add_anthropic.assert_called_once_with(completion_args["messages"])

    def test_add_cache_control_openai(self):
        """Test cache control application for OpenAI models."""
        model = ExtendedLiteLlm(model="openai/gpt-4o", cache_system_instruction=True)

        completion_args = {
            "messages": [Mock(role="developer", content="test content")]
        }

        model._add_cache_control(completion_args)

        # Should log about automatic caching
        log_output = self.get_log_output()
        self.assertIn("OpenAI model detected", log_output)
        self.assertIn("automatic caching will apply", log_output)

    def test_add_cache_control_azure_openai(self):
        """Test cache control application for Azure OpenAI models."""
        model = ExtendedLiteLlm(model="azure/gpt-4o", cache_system_instruction=True)

        completion_args = {
            "messages": [Mock(role="developer", content="test content")]
        }

        model._add_cache_control(completion_args)

        # Should log about Azure OpenAI automatic caching
        log_output = self.get_log_output()
        self.assertIn("Azure OpenAI model detected", log_output)
        self.assertIn("automatic caching will apply", log_output)

    def test_add_cache_control_unsupported(self):
        """Test cache control application for unsupported models."""
        model = ExtendedLiteLlm(model="gemini-1.5-pro", cache_system_instruction=True)

        completion_args = {
            "messages": [Mock(role="developer", content="test content")]
        }

        # Should not modify anything since caching is not supported
        original_args = completion_args.copy()
        model._add_cache_control(completion_args)

        # Arguments should remain unchanged
        self.assertEqual(completion_args, original_args)

    def test_add_anthropic_style_cache_control_string_content(self):
        """Test adding cache control to string content for Anthropic models."""
        model = ExtendedLiteLlm(model="anthropic/claude-3-5-sonnet-20240620", cache_system_instruction=True)

        # Create a mock message with string content
        mock_message = Mock()
        mock_message.role = "developer"
        mock_message.content = "This is a test system instruction"

        messages = [mock_message]
        model._add_anthropic_style_cache_control(messages)

        # Should convert string to list with cache control
        expected_content = [
            {
                "type": "text",
                "text": "This is a test system instruction",
                "cache_control": {"type": "ephemeral"}
            }
        ]
        self.assertEqual(mock_message.content, expected_content)

    def test_add_anthropic_style_cache_control_list_content(self):
        """Test adding cache control to list content for Anthropic models."""
        model = ExtendedLiteLlm(model="anthropic/claude-3-5-sonnet-20240620", cache_system_instruction=True)

        # Create a mock message with list content
        mock_message = Mock()
        mock_message.role = "developer"
        mock_message.content = [
            {"type": "text", "text": "First part"},
            {"type": "text", "text": "Second part"}  # This should get cache control
        ]

        messages = [mock_message]
        model._add_anthropic_style_cache_control(messages)

        # Should add cache control to the last text item
        expected_cache_control = {"type": "ephemeral"}
        self.assertEqual(mock_message.content[1]["cache_control"], expected_cache_control)
        # First item should not have cache control
        self.assertNotIn("cache_control", mock_message.content[0])

    @patch('litellm_caching.ExtendedLiteLlm.llm_client')
    def test_generate_content_async_with_caching(self, mock_llm_client):
        """Test content generation with caching enabled."""
        # Setup mock
        mock_acompletion = Mock()
        mock_llm_client.acompletion = mock_acompletion

        model = ExtendedLiteLlm(model="anthropic/claude-3-5-sonnet-20240620", cache_system_instruction=True)
        mock_request = Mock()

        # Mock the parent class method
        with patch('google.adk.models.lite_llm.LiteLlm.generate_content_async') as mock_parent:
            async def mock_generator():
                yield Mock()

            mock_parent.return_value = mock_generator()

            # Test that our wrapper is called
            gen = model.generate_content_async(mock_request, stream=False)

            # The method should return an async generator
            self.assertTrue(hasattr(gen, '__aiter__'))

    def test_custom_cache_control_type(self):
        """Test using custom cache control type."""
        model = ExtendedLiteLlm(
            model="anthropic/claude-3-5-sonnet-20240620",
            cache_system_instruction=True,
            cache_control_type="custom_type"
        )

        self.assertEqual(model.cache_control_type, "custom_type")

        # Test that custom type is used in cache control
        mock_message = Mock()
        mock_message.role = "developer"
        mock_message.content = "test content"

        messages = [mock_message]
        model._add_anthropic_style_cache_control(messages)

        # Should use custom cache control type
        expected_content = [
            {
                "type": "text",
                "text": "test content",
                "cache_control": {"type": "custom_type"}
            }
        ]
        self.assertEqual(mock_message.content, expected_content)


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for real-world usage scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the logging functions
        self.mock_log = Mock()
        self.mock_debug_log = Mock()

        # Patch the logging functions in the module
        self.log_patcher = patch('src.extensions.extended_litellm.log', self.mock_log)
        self.debug_log_patcher = patch('src.extensions.extended_litellm.debug_log', self.mock_debug_log)

        self.log_patcher.start()
        self.debug_log_patcher.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.log_patcher.stop()
        self.debug_log_patcher.stop()

    def test_multi_provider_scenario(self):
        """Test scenario where user switches between different providers."""
        providers = [
            ("openai/gpt-4o", True),  # Should support caching
            ("azure/gpt-4o", True),   # Should support caching
            ("anthropic/claude-3-5-sonnet-20240620", True),  # Should support caching
            ("gemini-1.5-pro", False),  # Should not support caching
            ("deepseek/deepseek-chat", False),  # Should be blocked by policy
        ]

        for model_name, should_support_caching in providers:
            with self.subTest(model=model_name):
                model = ExtendedLiteLlm(
                    model=model_name,
                    cache_system_instruction=True,
                    temperature=0.2
                )

                # All models should be created successfully
                self.assertEqual(model.model, model_name)
                self.assertTrue(model.cache_system_instruction)

                # Check caching support
                supports_caching = model._supports_caching()
                self.assertEqual(supports_caching, should_support_caching)

    def test_agent_creation_pattern(self):
        """Test the typical agent creation pattern from user's code."""
        # Simulate the user's typical usage pattern
        def create_agent_model(agent_model, temperature=0.2):
            """Simulate user's agent creation function."""
            return ExtendedLiteLlm(
                model=agent_model,
                temperature=temperature,
                cache_system_instruction=True,
                stream_options={"include_usage": True}
            )

        # Test with different model types
        test_cases = [
            "anthropic/claude-3-5-sonnet-20240620",
            "openai/gpt-4o",
            "azure/gpt-4o",
            "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0",
            "gemini-1.5-pro"
        ]

        for model_name in test_cases:
            with self.subTest(model=model_name):
                # Should create successfully without errors
                model = create_agent_model(model_name)
                self.assertIsInstance(model, ExtendedLiteLlm)
                self.assertEqual(model.model, model_name)
                self.assertTrue(model.cache_system_instruction)

    def test_error_handling_robustness(self):
        """Test that the implementation handles edge cases gracefully."""
        # Test with empty model name
        with self.assertRaises(TypeError):
            # This should fail at the parent class level, not our code
            ExtendedLiteLlm()

        # Test with None values
        model = ExtendedLiteLlm(
            model="openai/gpt-4o",
            cache_system_instruction=None  # Should handle gracefully
        )
        # Should default to False
        self.assertFalse(model.cache_system_instruction)

    def test_logging_levels(self):
        """Test that logging works correctly at different levels."""
        # Test info level logging
        model = ExtendedLiteLlm(model="gemini-1.5-pro", cache_system_instruction=True)
        model._supports_caching()

        # Check that log was called with the expected message
        self.mock_log.assert_called()
        log_calls = [str(call_arg) for call_arg in self.mock_log.call_args_list]
        self.assertTrue(any("doesn't support prompt caching" in call_str for call_str in log_calls))

        # Reset mocks for next test
        self.mock_log.reset_mock()
        self.mock_debug_log.reset_mock()

        # Test policy restriction logging
        model = ExtendedLiteLlm(model="deepseek/deepseek-chat", cache_system_instruction=True)
        model._supports_caching()

        # Check that log was called with policy restriction message
        self.mock_log.assert_called()
        log_calls = [str(call_arg) for call_arg in self.mock_log.call_args_list]
        self.assertTrue(any("policy restrictions" in call_str for call_str in log_calls))


if __name__ == '__main__':
    # Create test suite
    suite = unittest.TestSuite()

    # Add all test classes
    test_classes = [
        TestExtendedLiteLlm,
        TestIntegrationScenarios
    ]

    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print(f"\n{'='*60}")
    print("Test Summary:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    print(f"{'='*60}")

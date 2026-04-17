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

"""
Tests for contrast_app_ids configuration input (AIML-569).

Tests the new contrast_app_ids JSON array input and the precedence logic
for resolving the active application ID:
  1. contrast_app_id (singular) set → use it directly (backward compat)
  2. contrast_app_ids (plural) set, singular not set → use first element
  3. Both set → singular wins
  4. Neither set → ConfigurationError
"""

import unittest
import os
from src.config import Config, ConfigurationError, reset_config


class TestContrastAppIds(unittest.TestCase):
    """Tests for contrast_app_ids config parsing and precedence logic."""

    def setUp(self):
        self.original_env = os.environ.copy()
        reset_config()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        reset_config()

    def _get_base_env(self):
        """Base env vars needed for Config initialization, without any app ID fields."""
        return {
            'GITHUB_WORKSPACE': '/tmp',
            'BUILD_COMMAND': 'echo "Mock build"',
            'GITHUB_TOKEN': 'mock-token',
            'GITHUB_REPOSITORY': 'mock/repo',
            'GITHUB_SERVER_URL': 'https://github.com',
            'BASE_BRANCH': 'main',
            'CONTRAST_HOST': 'test.contrastsecurity.com',
            'CONTRAST_ORG_ID': 'test-org-id',
            'CONTRAST_AUTHORIZATION_KEY': 'test-auth-key',
            'CONTRAST_API_KEY': 'test-api-key',
            # Use Contrast LLM to avoid AWS Bedrock validation complexity
            'USE_CONTRAST_LLM': 'true',
        }

    # =========================================================================
    # Backward compatibility: contrast_app_id (singular) unchanged
    # =========================================================================

    def test_contrast_app_id_singular_used_when_set(self):
        """When contrast_app_id (singular) is set, it is used as the app ID."""
        env = self._get_base_env()
        env['CONTRAST_APP_ID'] = 'my-single-app'

        config = Config(env=env, testing=False)

        self.assertEqual(config.CONTRAST_APP_ID, 'my-single-app')

    def test_both_set_singular_takes_precedence(self):
        """When both contrast_app_id and contrast_app_ids are set, contrast_app_id takes precedence."""
        env = self._get_base_env()
        env['CONTRAST_APP_ID'] = 'singular-app'
        env['CONTRAST_APP_IDS'] = '["plural-first", "plural-second"]'

        config = Config(env=env, testing=False)

        self.assertEqual(config.CONTRAST_APP_ID, 'singular-app')
        self.assertEqual(config.CONTRAST_APP_IDS, ['singular-app'])

    def test_neither_set_raises_config_error(self):
        """When neither contrast_app_id nor contrast_app_ids is set, raises ConfigurationError."""
        env = self._get_base_env()
        # Intentionally: no CONTRAST_APP_ID and no CONTRAST_APP_IDS

        with self.assertRaises(ConfigurationError):
            Config(env=env, testing=False)

    # =========================================================================
    # New behavior: contrast_app_ids (plural) JSON array
    # =========================================================================

    def test_contrast_app_ids_first_element_used_when_singular_not_set(self):
        """When contrast_app_id is absent but contrast_app_ids is set, uses first element."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = '["app-id-1", "app-id-2", "app-id-3"]'

        config = Config(env=env, testing=False)

        self.assertEqual(config.CONTRAST_APP_ID, 'app-id-1')

    def test_contrast_app_ids_single_element_array(self):
        """contrast_app_ids with a single-element array resolves to that element."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = '["only-app"]'

        config = Config(env=env, testing=False)

        self.assertEqual(config.CONTRAST_APP_ID, 'only-app')

    def test_contrast_app_ids_list_stored_on_config(self):
        """When contrast_app_ids is set, the full list is stored as CONTRAST_APP_IDS."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = '["app-id-1", "app-id-2", "app-id-3"]'

        config = Config(env=env, testing=False)

        self.assertEqual(config.CONTRAST_APP_IDS, ['app-id-1', 'app-id-2', 'app-id-3'])

    def test_contrast_app_ids_contains_singular_when_only_singular_set(self):
        """When only contrast_app_id (singular) is set, CONTRAST_APP_IDS is a one-element list."""
        env = self._get_base_env()
        env['CONTRAST_APP_ID'] = 'my-app'

        config = Config(env=env, testing=False)

        self.assertEqual(config.CONTRAST_APP_IDS, ['my-app'])

    # =========================================================================
    # Error cases: invalid contrast_app_ids values
    # =========================================================================

    def test_contrast_app_ids_invalid_json_raises_config_error(self):
        """When contrast_app_ids contains invalid JSON, raises ConfigurationError."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = 'not-valid-json'

        with self.assertRaises(ConfigurationError):
            Config(env=env, testing=False)

    def test_contrast_app_ids_empty_array_raises_config_error(self):
        """When contrast_app_ids is an empty array, raises ConfigurationError."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = '[]'

        with self.assertRaises(ConfigurationError):
            Config(env=env, testing=False)

    def test_contrast_app_ids_not_a_list_raises_config_error(self):
        """When contrast_app_ids is valid JSON but not a list, raises ConfigurationError."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = '"just-a-string"'

        with self.assertRaises(ConfigurationError):
            Config(env=env, testing=False)

    def test_contrast_app_ids_object_raises_config_error(self):
        """When contrast_app_ids is a JSON object (not an array), raises ConfigurationError."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = '{"app": "id"}'

        with self.assertRaises(ConfigurationError):
            Config(env=env, testing=False)

    def test_contrast_app_ids_empty_string_element_raises_config_error(self):
        """An empty string element in contrast_app_ids raises ConfigurationError."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = '["valid-id", ""]'

        with self.assertRaises(ConfigurationError):
            Config(env=env, testing=False)

    def test_contrast_app_ids_whitespace_only_element_raises_config_error(self):
        """A whitespace-only string element in contrast_app_ids raises ConfigurationError."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = '["valid-id", "   "]'

        with self.assertRaises(ConfigurationError):
            Config(env=env, testing=False)

    def test_contrast_app_ids_null_element_raises_config_error(self):
        """A null element in contrast_app_ids raises ConfigurationError."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = '["valid-id", null]'

        with self.assertRaises(ConfigurationError):
            Config(env=env, testing=False)

    def test_contrast_app_ids_strips_whitespace_from_valid_elements(self):
        """Valid elements with surrounding whitespace are stripped."""
        env = self._get_base_env()
        env['CONTRAST_APP_IDS'] = '["  app-id-1  ", "app-id-2"]'

        config = Config(env=env, testing=False)

        self.assertEqual(config.CONTRAST_APP_IDS, ['app-id-1', 'app-id-2'])
        self.assertEqual(config.CONTRAST_APP_ID, 'app-id-1')

    # =========================================================================
    # _check_contrast_config_values_exist: CONTRAST_APP_IDS non-empty guard
    # =========================================================================

    def test_check_config_raises_when_app_ids_empty(self):
        """_check_contrast_config_values_exist raises ConfigurationError when CONTRAST_APP_IDS is empty."""
        env = self._get_base_env()
        env['CONTRAST_APP_ID'] = 'my-app'
        config = Config(env=env, testing=False)
        # Manually corrupt the list to simulate the guard being needed
        config.CONTRAST_APP_IDS = []
        with self.assertRaises(ConfigurationError):
            config._check_contrast_config_values_exist()

    # =========================================================================
    # Testing mode: defaults unchanged
    # =========================================================================

    def test_testing_mode_uses_default_app_id_when_not_set(self):
        """In testing mode, CONTRAST_APP_ID defaults to 'test-app' when not set."""
        os.environ.pop('CONTRAST_APP_ID', None)
        config = Config(testing=True)

        self.assertEqual(config.CONTRAST_APP_ID, 'test-app')

    def test_testing_mode_contrast_app_ids_defaults_to_empty_list(self):
        """In testing mode with no CONTRAST_APP_IDS set, CONTRAST_APP_IDS defaults to []."""
        config = Config(testing=True)

        self.assertEqual(config.CONTRAST_APP_IDS, [])

    def test_testing_mode_derives_app_id_from_plural_when_singular_unset(self):
        """In testing mode, CONTRAST_APP_ID is derived from CONTRAST_APP_IDS when singular is not set."""
        os.environ.pop('CONTRAST_APP_ID', None)
        os.environ['CONTRAST_APP_IDS'] = '["test-id-from-plural"]'
        config = Config(testing=True)

        self.assertEqual(config.CONTRAST_APP_ID, 'test-id-from-plural')
        self.assertEqual(config.CONTRAST_APP_IDS, ['test-id-from-plural'])


if __name__ == '__main__':
    unittest.main()

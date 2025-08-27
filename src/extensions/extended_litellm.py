# -
# #%L
# Extended LiteLLM with Prompt Caching
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# This work is a derivative of Google's ADK LiteLlm class, which is
# Copyright 2025 Google LLC and licensed under the Apache License, Version 2.0.
# Original source: https://github.com/google/adk-python
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

from typing import List, AsyncGenerator
import logging

from google.adk.models.lite_llm import (
    LiteLlm, _get_completion_inputs, _build_request_log
)
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from litellm import Message

logger = logging.getLogger(__name__)


class ExtendedLiteLlm(LiteLlm):
    """Extended LiteLlm with automatic prompt caching and comprehensive cost analysis.

    This class extends the base LiteLlm to automatically apply prompt caching
    and provide detailed cost analysis for all LLM interactions:
    - Automatic caching: Applies cache_control to system, user, and assistant messages
    - Complete cost tracking: Captures costs for both streaming and non-streaming calls
    - Cache-aware pricing: Uses model-specific pricing including cache read/write costs
    - Comprehensive metrics: Token usage, cache efficiency, and cost savings

    Supported providers:
    - Direct Anthropic API: Uses cache_control on message content
    - Bedrock Claude models: Uses cache_control on message content
    - Other models: Work normally without caching but with cost tracking

    Example usage:
    ```python
    # Anthropic Direct API - will apply cache_control automatically
    model = ExtendedLiteLlm(model="anthropic/claude-3-5-sonnet-20241022")

    # Bedrock Claude - will apply cache_control automatically
    model = ExtendedLiteLlm(model="bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0")

    # OpenAI - works with cost tracking (no caching applied)
    model = ExtendedLiteLlm(model="openai/gpt-4o")

    # Other models - work normally with cost tracking
    model = ExtendedLiteLlm(model="gemini/gemini-1.5-pro")
    ```
    """

    def __init__(self, model: str, **kwargs):
        super().__init__(model=model, **kwargs)
        print(f"[EXTENDED] ExtendedLiteLlm initialized with model: {model}")
        logger.info(f"ExtendedLiteLlm initialized with model: {model}")

    def _add_cache_control_to_message(self, message: dict) -> None:
        """Add cache_control to message content for Anthropic API compatibility.

        Applies cache_control to the content array within each message, which is
        the documented format for Anthropic's prompt caching feature.
        """
        if isinstance(message, dict) and 'content' in message:
            content = message['content']
            if isinstance(content, str):
                # Convert string content to array format with cache_control
                message['content'] = [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]
                print(f"[EXTENDED] Added cache_control to content for role: {message.get('role', 'unknown')}")
            elif isinstance(content, list):
                # Add cache_control to existing content array
                for item in content:
                    if isinstance(item, dict):
                        item['cache_control'] = {"type": "ephemeral"}
                print(f"[EXTENDED] Added cache_control to content array for role: {message.get('role', 'unknown')}")
        elif isinstance(message, dict):
            print(f"[EXTENDED] Message has no content field for role: {message.get('role', 'unknown')}")

    def _apply_role_conversion_and_caching(self, messages: List[Message]) -> None:  # noqa: C901
        """Convert developer->system for non-OpenAI models and apply caching.

        This prevents LiteLLM's internal role conversion that strips cache_control fields.
        """
        model_lower = self.model.lower()

        # Early return if model doesn't support caching
        if not (("bedrock/" in model_lower and "claude" in model_lower)
                or ("anthropic/" in model_lower and "bedrock/" not in model_lower)):
            return

        if "bedrock/" in model_lower and "claude" in model_lower:
            # Bedrock Claude: Convert developer->system and add cache_control
            for i, message in enumerate(messages):
                if isinstance(message, dict):
                    role = message.get('role')
                elif hasattr(message, 'role'):
                    role = getattr(message, 'role', None)
                    # Convert to dict for easier manipulation
                    if hasattr(message, '__dict__'):
                        message_dict = message.__dict__.copy()
                        messages[i] = message_dict
                        message = message_dict
                        role = message.get('role')
                else:
                    continue

                # Convert developer->system and add cache_control in one step
                if role == 'developer':
                    if isinstance(message, dict):
                        message['role'] = 'system'  # Prevent LiteLLM conversion
                        # Add cache_control to content instead of message
                        self._add_cache_control_to_message(message)

                # Add cache_control to user and assistant messages as well
                elif role in ['user', 'assistant']:
                    if isinstance(message, dict):
                        # Add cache_control to content instead of message
                        self._add_cache_control_to_message(message)

        elif "anthropic/" in model_lower and "bedrock/" not in model_lower:
            # Direct Anthropic API: Just add cache_control (developer role is fine)
            for i, message in enumerate(messages):
                if isinstance(message, dict):
                    role = message.get('role')
                elif hasattr(message, 'role'):
                    role = getattr(message, 'role', None)
                    # Convert to dict for easier manipulation
                    if hasattr(message, '__dict__'):
                        message_dict = message.__dict__.copy()
                        messages[i] = message_dict
                        message = message_dict
                        role = message.get('role')
                else:
                    continue

                # Add cache_control to developer, user, and assistant messages
                if role in ['developer', 'user', 'assistant']:
                    if isinstance(message, dict):
                        # Add cache_control to content instead of message
                        self._add_cache_control_to_message(message)

    def _log_usage_and_costs(self, response) -> LlmResponse:
        """Override to extract cache-specific token metrics from raw LiteLLM response.

        This method captures cache token data from the raw response before any processing.
        Combines the working approach from temp.txt with current cost analysis.
        """
        print("[CACHE-EXTRACTION] Intercepting response for cache token extraction")

        # Extract cache-specific metrics from the raw response (like temp.txt)
        usage = response.get("usage", {})
        print(f"[CACHE-EXTRACTION] Usage data: {usage}")
        print(f"[CACHE-EXTRACTION] Usage type: {type(usage)}")

        # Convert to dict for processing, handling both dict and Usage object cases
        if isinstance(usage, dict):
            usage_dict = usage
            # Extract from dict
            cache_read_input_tokens = (
                usage_dict.get("cache_read_input_tokens", 0)
                or usage_dict.get("cacheReadInputTokens", 0)
                or usage_dict.get("cacheReadInputTokenCount", 0)
            )
            cache_write_input_tokens = (
                usage_dict.get("cache_creation_input_tokens", 0)
                or usage_dict.get("cacheWriteInputTokens", 0)
                or usage_dict.get("cacheWriteInputTokenCount", 0)
            )
        elif hasattr(usage, '__dict__'):
            # For Usage objects, access properties directly (they're not in __dict__)
            cache_read_input_tokens = getattr(usage, 'cache_read_input_tokens', 0)
            cache_write_input_tokens = getattr(usage, 'cache_creation_input_tokens', 0)

            print("[CACHE-EXTRACTION] Direct property access:")
            print(f"[CACHE-EXTRACTION]   cache_read_input_tokens: {cache_read_input_tokens}")
            print(f"[CACHE-EXTRACTION]   cache_creation_input_tokens: {cache_write_input_tokens}")

            # Convert to dict for _log_usage_and_costs, but add the cache fields manually
            usage_dict = usage.__dict__.copy()
            usage_dict['cache_read_input_tokens'] = cache_read_input_tokens
            usage_dict['cache_creation_input_tokens'] = cache_write_input_tokens
            print(f"[CACHE-EXTRACTION] Enhanced usage dict with cache tokens: {usage_dict.keys()}")
        else:
            print(f"[CACHE-EXTRACTION] Unknown usage type: {type(usage)}")
            usage_dict = {}
            cache_read_input_tokens = 0
            cache_write_input_tokens = 0

        # Extract cache tokens using the successful field names from temp.txt

        if cache_read_input_tokens > 0 or cache_write_input_tokens > 0:
            print("[CACHE-EXTRACTION] FOUND CACHE TOKENS!")
            print(f"[CACHE-EXTRACTION]   Cache Read: {cache_read_input_tokens}")
            print(f"[CACHE-EXTRACTION]   Cache Write: {cache_write_input_tokens}")

            # Use our cost analysis method
            self._log_usage_and_costs(usage_dict, "CACHE-EXTRACTION")
        else:
            print("[CACHE-EXTRACTION] No cache tokens found - may indicate caching not working")

        print("[CACHE-EXTRACTION] Response processing completed")

    async def generate_content_async(  # noqa: C901
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Generates content asynchronously with automatic prompt caching.

        Args:
            llm_request: LlmRequest, the request to send to the LiteLlm model.
            stream: bool = False, whether to do streaming call.

        Yields:
            LlmResponse: The model response.
        """
        self._maybe_append_user_content(llm_request)
        print(f"[EXTENDED] generate_content_async called for model: {self.model}")
        logger.debug(_build_request_log(llm_request))

        # Get completion inputs
        messages, tools, response_format, generation_params = (
            _get_completion_inputs(llm_request)
        )

        # Apply role conversion and caching
        self._apply_role_conversion_and_caching(messages)

        if "functions" in self._additional_args:
            # LiteLLM does not support both tools and functions together.
            tools = None

        completion_args = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "response_format": response_format,
        }
        completion_args.update(self._additional_args)

        if generation_params:
            completion_args.update(generation_params)

        print("DEBUG: Entering NON-STREAMING code branch")
        response = await self.llm_client.acompletion(**completion_args)

        # Capture cache tokens from raw response
        self._log_usage_and_costs(response)

        # Call the parent method to get the standard LlmResponse
        from google.adk.models.lite_llm import _model_response_to_generate_content_response
        yield _model_response_to_generate_content_response(response)

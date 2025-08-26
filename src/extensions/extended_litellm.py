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

import litellm
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

    def _log_usage_and_costs(self, usage_data: dict, source: str = "") -> None:
        """Log usage and cost analysis for both streaming and non-streaming responses.

        Args:
            usage_data: Dictionary containing usage information
            source: String indicating if this is from streaming or non-streaming
        """
        # Log cache token metrics
        source_prefix = f"[{source}] " if source else ""

        # Debug: Log all usage_data keys to see what we're getting
        print(f"{source_prefix}Raw usage_data keys: {list(usage_data.keys())}")
        print(f"{source_prefix}Raw usage_data: {usage_data}")

        # Extract token counts - try multiple field name variations
        cache_read_input_tokens = (
            usage_data.get("cacheReadInputTokenCount", 0)
            or usage_data.get("cacheReadInputTokens", 0)
            or usage_data.get("cache_read_input_tokens", 0)
            or usage_data.get("cache_read_tokens", 0)
            or usage_data.get("cached_tokens", 0)
        )
        cache_write_input_tokens = (
            usage_data.get("cacheWriteInputTokenCount", 0)
            or usage_data.get("cacheWriteInputTokens", 0)
            or usage_data.get("cache_write_input_tokens", 0)
            or usage_data.get("cache_write_tokens", 0)
            or usage_data.get("cache_creation_tokens", 0)
            or usage_data.get("cache_creation_input_tokens", 0)
        )
        input_tokens = (
            usage_data.get("inputTokens", 0)
            or usage_data.get("prompt_tokens", 0)
            or usage_data.get("input_tokens", 0)
        )
        output_tokens = (
            usage_data.get("outputTokens", 0)
            or usage_data.get("completion_tokens", 0)
            or usage_data.get("output_tokens", 0)
        )
        total_tokens = (
            usage_data.get("totalTokens", 0)
            or usage_data.get("total_tokens", 0)
        )

        # Calculate total cached tokens (read + write)
        total_cached_tokens = cache_read_input_tokens + cache_write_input_tokens

        # Log cache token metrics
        source_prefix = f"[{source}] " if source else ""
        print(f"{source_prefix}Cache Token Metrics:")
        print(f"{source_prefix}  Cache Read Input Tokens: {cache_read_input_tokens}")
        print(f"{source_prefix}  Cache Write Input Tokens: {cache_write_input_tokens}")
        print(f"{source_prefix}  Total Cached Tokens: {total_cached_tokens}")
        print(f"{source_prefix}  Input Tokens: {input_tokens}")
        print(f"{source_prefix}  Output Tokens: {output_tokens}")
        print(f"{source_prefix}  Total Tokens: {total_tokens}")

        # Get cost information and log cost analysis
        try:
            model_info = litellm.get_model_info(self.model)

            regular_input_cost = model_info.get("input_cost_per_token", 3e-06)
            cache_read_cost = model_info.get("cache_read_input_token_cost", 3e-07)
            cache_write_cost = model_info.get("cache_creation_input_token_cost", 3.75e-06)
            output_cost = model_info.get("output_cost_per_token", 1.5e-05)

            print(f"{source_prefix}Model Costs (per token):")
            print(f"{source_prefix}  Regular Input: ${regular_input_cost:.2e}")
            print(f"{source_prefix}  Cache Read: ${cache_read_cost:.2e}")
            print(f"{source_prefix}  Cache Write: ${cache_write_cost:.2e}")
            print(f"{source_prefix}  Output: ${output_cost:.2e}")

            # Calculate actual costs
            total_input_cost = 0
            total_output_cost = output_tokens * output_cost
            cache_savings = 0

            if cache_read_input_tokens > 0:
                # Cost with caching
                cache_read_total_cost = cache_read_input_tokens * cache_read_cost
                # What it would have cost without caching
                regular_cost_equivalent = cache_read_input_tokens * regular_input_cost
                cache_savings = regular_cost_equivalent - cache_read_total_cost
                total_input_cost += cache_read_total_cost

            if cache_write_input_tokens > 0:
                cache_write_total_cost = cache_write_input_tokens * cache_write_cost
                total_input_cost += cache_write_total_cost

            # Non-cached input tokens (if any)
            non_cached_input_tokens = input_tokens - total_cached_tokens
            if non_cached_input_tokens > 0:
                total_input_cost += non_cached_input_tokens * regular_input_cost

            total_cost = total_input_cost + total_output_cost

            print(f"{source_prefix}Cost Breakdown:")
            print(f"{source_prefix}  Input Cost: ${total_input_cost:.6f}")
            print(f"{source_prefix}  Output Cost: ${total_output_cost:.6f}")
            print(f"{source_prefix}  Total Cost: ${total_cost:.6f}")

            if cache_savings > 0:
                print(f"{source_prefix}  Cache Savings: ${cache_savings:.6f} ({cache_read_input_tokens} tokens)")
                savings_percentage = (cache_savings / (cache_savings + total_input_cost)) * 100
                print(f"{source_prefix}  Savings Rate: {savings_percentage:.1f}%")
            elif total_cached_tokens > 0:
                cache_efficiency = (total_cached_tokens / total_tokens) * 100 if total_tokens > 0 else 0
                print(f"{source_prefix}  Cache Efficiency: {cache_efficiency:.1f}% ({total_cached_tokens}/{total_tokens})")

        except Exception as e:
            print(f"{source_prefix}Could not retrieve model cost information: {e}")
            logger.warning(f"Could not retrieve model cost information: {e}")

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
        # Debug: Log the non-streaming response structure
        print(f"NON-STREAMING: Response type: {type(response)}")
        if hasattr(response, 'keys'):
            print(f"NON-STREAMING: Response keys: {list(response.keys())}")
        else:
            print("NON-STREAMING: Response has no keys method")

        # Log non-streaming costs immediately after API call
        if response.get("usage"):
            # Use raw response usage dict (like the old override) instead of Usage object
            raw_usage = response.get("usage")
            print(f"NON-STREAMING: Raw usage type: {type(raw_usage)}")

            if isinstance(raw_usage, dict):
                print(f"NON-STREAMING: Raw usage is dict with keys: {list(raw_usage.keys())}")
                self._log_usage_and_costs(raw_usage, "NON-STREAMING")
            else:
                # Fallback to Usage object conversion
                print("NON-STREAMING: Raw usage is object, converting...")
                if hasattr(raw_usage, '__dict__'):
                    print(f"NON-STREAMING: Usage attributes: {list(raw_usage.__dict__.keys())}")
                    usage_dict = raw_usage.__dict__.copy()
                    self._log_usage_and_costs(usage_dict, "NON-STREAMING")
                else:
                    print(f"NON-STREAMING: Unknown usage object type: {type(raw_usage)}")
        else:
            print("NON-STREAMING: No usage data in response!")

        # Call our override to capture cache tokens from raw response
        yield self._model_response_to_generate_content_response(response)

    def _model_response_to_generate_content_response(self, response) -> LlmResponse:
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

        # Call the parent method to get the standard LlmResponse
        from google.adk.models.lite_llm import _model_response_to_generate_content_response
        result = _model_response_to_generate_content_response(response)
        print("[CACHE-EXTRACTION] Response processing completed")
        return result

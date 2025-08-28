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
import json

import litellm
from google.adk.models.lite_llm import LiteLlm, _get_completion_inputs
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from litellm import Message
from pydantic import Field
from src.utils import debug_log


class TokenCostAccumulator:
    """Accumulator for tracking token usage and costs across multiple LLM calls."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Reset all accumulated values to zero."""
        # Token counts
        self.total_new_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_read_tokens = 0
        self.total_cache_write_tokens = 0

        # Costs
        self.total_new_input_cost = 0.0
        self.total_cache_read_cost = 0.0
        self.total_cache_write_cost = 0.0
        self.total_output_cost = 0.0

        # Call count
        self.call_count = 0

    def add_usage(self, input_tokens: int, output_tokens: int, cache_read_tokens: int,
                  cache_write_tokens: int, new_input_cost: float, cache_read_cost: float,
                  cache_write_cost: float, output_cost: float):
        """Add usage statistics from a single LLM call."""
        # Accumulate tokens
        self.total_new_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_read_tokens += cache_read_tokens
        self.total_cache_write_tokens += cache_write_tokens

        # Accumulate costs
        self.total_new_input_cost += new_input_cost
        self.total_cache_read_cost += cache_read_cost
        self.total_cache_write_cost += cache_write_cost
        self.total_output_cost += output_cost

        # Increment call count
        self.call_count += 1

    @property
    def total_tokens(self):
        """Calculate total tokens across all types."""
        return (self.total_new_input_tokens + self.total_output_tokens
                + self.total_cache_read_tokens + self.total_cache_write_tokens)

    @property
    def total_input_cost(self):
        """Calculate total input cost (new + cache read + cache write)."""
        return self.total_new_input_cost + self.total_cache_read_cost + self.total_cache_write_cost

    @property
    def total_cost(self):
        """Calculate total cost across all operations."""
        return self.total_input_cost + self.total_output_cost

    @property
    def cache_savings(self):
        """Calculate total cache savings (what cache reads would have cost at regular price)."""
        if self.total_cache_read_tokens == 0:
            return 0.0
        # Estimate regular input cost per token from new input cost
        if self.total_new_input_tokens > 0:
            regular_cost_per_token = self.total_new_input_cost / self.total_new_input_tokens
            return self.total_cache_read_tokens * (regular_cost_per_token - (self.total_cache_read_cost / self.total_cache_read_tokens))
        return 0.0

    @property
    def cache_savings_percentage(self):
        """Calculate cache savings as a percentage of what input cost would have been without caching."""
        if self.total_cache_read_tokens == 0:
            return 0.0
        savings = self.cache_savings
        total_input_without_cache = self.total_input_cost + savings
        if total_input_without_cache > 0:
            return (savings / total_input_without_cache) * 100
        return 0.0


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

    Example usage:
    ```python
    # Bedrock Claude - Works with all features and cost tracking
    model = ExtendedLiteLlm(model="bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0")

    # Direct Anthropic - Works with all features and cost tracking
    model = ExtendedLiteLlm(model="anthropic/claude-3-7-sonnet-20250219")

    # OpenAI - works with cost tracking (no caching applied)
    model = ExtendedLiteLlm(model="openai/gpt-4o")

    # Other models - work normally with cost tracking
    model = ExtendedLiteLlm(model="gemini/gemini-1.5-pro")
    ```
    """

    cost_accumulator: TokenCostAccumulator = Field(default_factory=TokenCostAccumulator)
    """Accumulator for tracking token usage and costs across multiple LLM calls."""

    def __init__(self, model: str, **kwargs):
        super().__init__(model=model, **kwargs)

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
            elif isinstance(content, list):
                # Add cache_control to existing content array
                for item in content:
                    if isinstance(item, dict):
                        item['cache_control'] = {"type": "ephemeral"}

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

        response = await self.llm_client.acompletion(**completion_args)

        # Call our override to capture cache tokens from raw response
        self._log_cost_analysis(response)

        # Call the parent method to get the standard LlmResponse
        from google.adk.models.lite_llm import _model_response_to_generate_content_response
        yield _model_response_to_generate_content_response(response)

    def _log_cost_analysis(self, response) -> None:
        """Log detailed cost analysis with cache token information."""

        usage = response.get("usage", {})
        if not usage:
            return

        # Extract tokens - handle both dict and Usage object cases
        if isinstance(usage, dict):
            input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
            output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
            cache_read_tokens = usage.get("cache_read_input_tokens", 0)
            cache_write_tokens = usage.get("cache_creation_input_tokens", 0)
        elif hasattr(usage, '__dict__'):
            # For Usage objects, access properties directly
            input_tokens = getattr(usage, 'prompt_tokens', 0)
            output_tokens = getattr(usage, 'completion_tokens', 0)
            total_tokens = getattr(usage, 'total_tokens', input_tokens + output_tokens)
            cache_read_tokens = getattr(usage, 'cache_read_input_tokens', 0)
            cache_write_tokens = getattr(usage, 'cache_creation_input_tokens', 0)
        else:
            return

        # Log basic usage
        debug_log("Token Usage:")
        debug_log(f"  New Input: {input_tokens}, Output: {output_tokens}")
        debug_log(f"  Cache Read: {cache_read_tokens}, Cache Write: {cache_write_tokens}")
        debug_log(f"  Total: {total_tokens}")

        # Calculate and log costs
        try:
            model_info = litellm.get_model_info(self.model)

            input_cost_per_token = model_info.get("input_cost_per_token", 3e-06)
            output_cost_per_token = model_info.get("output_cost_per_token", 1.5e-05)
            cache_read_cost_per_token = model_info.get("cache_read_input_token_cost", 3e-07)
            cache_write_cost_per_token = model_info.get("cache_creation_input_token_cost", 3.75e-06)

            # Calculate costs - tokens are additive, not overlapping
            new_input_cost = input_tokens * input_cost_per_token
            cache_read_cost = cache_read_tokens * cache_read_cost_per_token
            cache_write_cost = cache_write_tokens * cache_write_cost_per_token

            total_input_cost = new_input_cost + cache_read_cost + cache_write_cost
            output_cost = output_tokens * output_cost_per_token
            total_cost = total_input_cost + output_cost

            debug_log("Cost Analysis:")
            debug_log(f"  Input: ${total_input_cost:.6f} (New: ${new_input_cost:.6f}, Cache Read: ${cache_read_cost:.6f}, Cache Write: ${cache_write_cost:.6f})")
            debug_log(f"  Output: ${output_cost:.6f}, Total: ${total_cost:.6f}")

            # Add to accumulator
            self.cost_accumulator.add_usage(
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                new_input_cost, cache_read_cost, cache_write_cost, output_cost
            )

            # Show savings only if we have cache read tokens
            if cache_read_tokens > 0:
                # What the cached tokens would have cost at regular price
                cache_savings = cache_read_tokens * (input_cost_per_token - cache_read_cost_per_token)

                # Calculate what total input cost would have been without caching
                total_input_without_cache = total_input_cost + cache_savings
                savings_pct = (cache_savings / total_input_without_cache) * 100
                debug_log(f"  Cache Savings: ${cache_savings:.6f} ({savings_pct:.1f}%) from {cache_read_tokens} cached tokens")
        except Exception as e:
            debug_log(f"Could not calculate costs: {e}")

    def gather_accumulated_stats_dict(self) -> dict:
        """Gather accumulated token usage and cost statistics as dictionary.

        Returns:
            dict: Dictionary containing accumulated statistics
        """
        acc = self.cost_accumulator

        if acc.call_count == 0:
            return {"message": "No accumulated statistics available (no calls made yet)."}

        # Build the statistics as a structured dictionary
        stats = {
            "summary": f"ACCUMULATED STATISTICS ({acc.call_count} calls)",
            "call_count": acc.call_count,
            "token_usage": {
                "total_tokens": acc.total_tokens,
                "new_input_tokens": acc.total_new_input_tokens,
                "output_tokens": acc.total_output_tokens,
                "cache_read_tokens": acc.total_cache_read_tokens,
                "cache_write_tokens": acc.total_cache_write_tokens
            },
            "cost_analysis": {
                "total_cost": round(acc.total_cost, 6),
                "input_cost": round(acc.total_input_cost, 6),
                "output_cost": round(acc.total_output_cost, 6),
                "new_input_cost": round(acc.total_new_input_cost, 6),
                "cache_read_cost": round(acc.total_cache_read_cost, 6),
                "cache_write_cost": round(acc.total_cache_write_cost, 6)
            },
            "averages": {
                "cost_per_call": round(acc.total_cost / acc.call_count, 6),
                "tokens_per_call": round(acc.total_tokens / acc.call_count, 1)
            }
        }

        # Add cache savings if available
        if acc.total_cache_read_tokens > 0:
            savings = acc.cache_savings
            savings_pct = acc.cache_savings_percentage
            stats["cache_savings"] = {
                "total_savings": round(savings, 6),
                "savings_percentage": round(savings_pct, 1),
                "cached_tokens_used": acc.total_cache_read_tokens
            }

        return stats

    def gather_accumulated_stats(self) -> str:
        """Gather accumulated token usage and cost statistics as JSON string.

        Returns:
            str: JSON formatted string containing accumulated statistics
        """
        stats = self.gather_accumulated_stats_dict()
        # Convert to JSON string with proper formatting
        return json.dumps(stats, indent=2)

    def reset_accumulated_stats(self):
        """Reset accumulated statistics to start fresh."""
        self.cost_accumulator.reset()
        debug_log("Accumulated statistics have been reset.")

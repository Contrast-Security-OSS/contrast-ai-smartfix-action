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
import json

import litellm
from google.adk.models.lite_llm import (
    LiteLlm, _get_completion_inputs, _build_request_log, _model_response_to_chunk,
    _message_to_generate_content_response,
    FunctionChunk, TextChunk, UsageMetadataChunk
)
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from litellm import Message, ChatCompletionAssistantMessage, ChatCompletionMessageToolCall, Function

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
        logger.info(f"ExtendedLiteLlm initialized with model: {model}")

    def _add_cache_control_to_content(self, message: dict) -> None:
        """Add cache_control to message content following LiteLLM documentation format.

        According to LiteLLM docs, cache_control should be on the content objects,
        not on the message itself.
        """
        content = message.get('content')

        if isinstance(content, str):
            # Convert string content to proper format with cache_control
            message['content'] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        elif isinstance(content, list):
            # Content is already a list of objects, add cache_control to the last text object
            for item in reversed(content):
                if isinstance(item, dict) and item.get("type") == "text":
                    item["cache_control"] = {"type": "ephemeral"}
                    break
        # If content is neither string nor list, leave it as is

    def _log_usage_and_costs(self, usage_data: dict, source: str = "") -> None:
        """Log usage and cost analysis for both streaming and non-streaming responses.

        Args:
            usage_data: Dictionary containing usage information
            source: String indicating if this is from streaming or non-streaming
        """
        # Extract token counts - try multiple field name variations
        cache_read_input_tokens = (
            usage_data.get("cacheReadInputTokenCount", 0)
            or usage_data.get("cacheReadInputTokens", 0)
            or usage_data.get("cache_read_input_tokens", 0)
        )
        cache_write_input_tokens = (
            usage_data.get("cacheWriteInputTokenCount", 0)
            or usage_data.get("cacheWriteInputTokens", 0)
            or usage_data.get("cache_write_input_tokens", 0)
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
                        self._add_cache_control_to_content(message)

                # Add cache_control to user and assistant messages as well
                elif role in ['user', 'assistant']:
                    if isinstance(message, dict):
                        # Add cache_control to content instead of message
                        self._add_cache_control_to_content(message)

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
                        self._add_cache_control_to_content(message)

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

        if stream:
            text = ""
            # Track function calls by index
            function_calls = {}  # index -> {name, args, id}
            completion_args["stream"] = True
            aggregated_llm_response = None
            aggregated_llm_response_with_tool_call = None
            usage_metadata = None
            fallback_index = 0
            async for part in await self.llm_client.acompletion(**completion_args):
                for chunk, finish_reason in _model_response_to_chunk(part):
                    if isinstance(chunk, FunctionChunk):
                        index = chunk.index or fallback_index
                        if index not in function_calls:
                            function_calls[index] = {"name": "", "args": "", "id": None}

                        if chunk.name:
                            function_calls[index]["name"] += chunk.name
                        if chunk.args:
                            function_calls[index]["args"] += chunk.args

                            # check if args is completed (workaround for improper chunk
                            # indexing)
                            try:
                                json.loads(function_calls[index]["args"])
                                fallback_index += 1
                            except json.JSONDecodeError:
                                pass

                        function_calls[index]["id"] = (
                            chunk.id or function_calls[index]["id"] or str(index)
                        )
                    elif isinstance(chunk, TextChunk):
                        text += chunk.text
                        yield _message_to_generate_content_response(
                            ChatCompletionAssistantMessage(
                                role="assistant",
                                content=chunk.text,
                            ),
                            is_partial=True,
                        )
                    elif isinstance(chunk, UsageMetadataChunk):
                        usage_metadata = types.GenerateContentResponseUsageMetadata(
                            prompt_token_count=chunk.prompt_tokens,
                            candidates_token_count=chunk.completion_tokens,
                            total_token_count=chunk.total_tokens,
                        )
                        # Log streaming costs immediately when usage metadata is available
                        streaming_usage = {
                            "prompt_tokens": chunk.prompt_tokens,
                            "completion_tokens": chunk.completion_tokens,
                            "total_tokens": chunk.total_tokens,
                        }
                        self._log_usage_and_costs(streaming_usage, "STREAMING")

                    if (
                        finish_reason == "tool_calls" or finish_reason == "stop"
                    ) and function_calls:
                        tool_calls = []
                        for index, func_data in function_calls.items():
                            if func_data["id"]:
                                tool_calls.append(
                                    ChatCompletionMessageToolCall(
                                        type="function",
                                        id=func_data["id"],
                                        function=Function(
                                            name=func_data["name"],
                                            arguments=func_data["args"],
                                            index=index,
                                        ),
                                    )
                                )
                        aggregated_llm_response_with_tool_call = (
                            _message_to_generate_content_response(
                                ChatCompletionAssistantMessage(
                                    role="assistant",
                                    content=text,
                                    tool_calls=tool_calls,
                                )
                            )
                        )
                        text = ""
                        function_calls.clear()
                    elif finish_reason == "stop" and text:
                        aggregated_llm_response = _message_to_generate_content_response(
                            ChatCompletionAssistantMessage(role="assistant", content=text)
                        )
                        text = ""

            # waiting until streaming ends to yield the llm_response as litellm tends
            # to send chunk that contains usage_metadata after the chunk with
            # finish_reason set to tool_calls or stop.
            if aggregated_llm_response:
                if usage_metadata:
                    aggregated_llm_response.usage_metadata = usage_metadata
                    usage_metadata = None
                yield aggregated_llm_response

            if aggregated_llm_response_with_tool_call:
                if usage_metadata:
                    aggregated_llm_response_with_tool_call.usage_metadata = usage_metadata
                yield aggregated_llm_response_with_tool_call

        else:
            response = await self.llm_client.acompletion(**completion_args)
            # Log non-streaming costs immediately after API call
            if response.get("usage"):
                self._log_usage_and_costs(response["usage"], "NON-STREAMING")
            # Use parent class method directly - no override needed
            from google.adk.models.lite_llm import _model_response_to_generate_content_response
            yield _model_response_to_generate_content_response(response)

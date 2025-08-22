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
from google.adk.models.lite_llm import (
    LiteLlm, _get_completion_inputs, _build_request_log, _model_response_to_chunk,
    _model_response_to_generate_content_response, _message_to_generate_content_response,
    FunctionChunk, TextChunk, UsageMetadataChunk
)
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from litellm import Message, ChatCompletionAssistantMessage, ChatCompletionMessageToolCall, Function
import litellm
import logging
import json

# Enable LiteLLM debug logging
litellm._turn_on_debug()

logger = logging.getLogger(__name__)


class ExtendedLiteLlm(LiteLlm):
    """Extended LiteLlm with automatic prompt caching for Anthropic models.

    This class extends the base LiteLlm to automatically apply prompt caching
    using the appropriate method for each provider:
    - Direct Anthropic API: Uses cache_control on messages
    - Bedrock Claude models: Uses cachePoint objects in content arrays

    Example usage:
    ```python
    # Anthropic Direct API - will apply cache_control automatically
    model = ExtendedLiteLlm(model="anthropic/claude-3-5-sonnet-20241022")

    # Bedrock Claude - will apply cachePoint automatically
    model = ExtendedLiteLlm(model="bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0")

    # OpenAI - works with automatic caching (no changes needed)
    model = ExtendedLiteLlm(model="openai/gpt-4o")

    # Other models - work normally without caching
    model = ExtendedLiteLlm(model="gemini/gemini-1.5-pro")
    ```
    """

    def __init__(self, model: str, **kwargs):
        super().__init__(model=model, **kwargs)
        # Use multiple logging methods to ensure visibility
        print(f"[EXTENDED] ExtendedLiteLlm initialized with model: {model}")
        print(f"[EXTENDED] ExtendedLiteLlm kwargs: {kwargs}")
        logger.info(f"[EXTENDED] ExtendedLiteLlm initialized with model: {model}")
        logger.warning("[EXTENDED] ExtendedLiteLlm INIT - This should always show up!")

        # Force logging to stderr as well
        import sys
        print(f"[EXTENDED-STDERR] ExtendedLiteLlm initialized with model: {model}", file=sys.stderr)

    def _apply_role_conversion_and_caching(self, messages: List[Message]) -> None:  # noqa: C901
        """Convert developer->system for non-OpenAI models and apply caching.

        This prevents LiteLLM's internal role conversion that strips cache_control fields.
        """
        import sys

        print(f"[EXTENDED] _apply_role_conversion_and_caching called! Model: {self.model}")
        print(f"[EXTENDED-STDERR] _apply_role_conversion_and_caching called! Model: {self.model}", file=sys.stderr)
        logger.info(f"[EXTENDED] Processing model: {self.model}")

        model_lower = self.model.lower()

        if "bedrock/" in model_lower and "claude" in model_lower:
            print("[EXTENDED] Applying Bedrock role conversion and caching")

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
                    print(f"[EXTENDED] Converting developer->system and adding cache_control to message {i}")

                    if isinstance(message, dict):
                        message['role'] = 'system'  # Prevent LiteLLM conversion
                        message['cache_control'] = {"type": "ephemeral"}  # Add caching

                    print("[EXTENDED] Applied role conversion and cache_control")
                    break  # Only cache first developer message

        elif "anthropic/" in model_lower and "bedrock/" not in model_lower:
            print("[EXTENDED] Applying Anthropic caching (no role conversion needed)")
            # For direct Anthropic API, developer role is fine, just add cache_control
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

                # Add cache_control to developer messages for direct Anthropic
                if role == 'developer':
                    print(f"[EXTENDED] Adding cache_control to developer message {i}")

                    if isinstance(message, dict):
                        message['cache_control'] = {"type": "ephemeral"}

                    print("[EXTENDED] Applied cache_control to developer message")
                    break  # Only cache first developer message
        else:
            print(f"[EXTENDED] No role conversion or caching needed for: {self.model}")

        # Log the final message structure
        print("[EXTENDED] Final message structure after role conversion:")
        for i, message in enumerate(messages):
            if isinstance(message, dict):
                role = message.get('role')
                has_cache = 'cache_control' in message
                cache_status = "CACHED" if has_cache else "NO_CACHE"
                print(f"[EXTENDED] Message {i}: role={role}, cache_status={cache_status}")
                if has_cache:
                    print(f"[EXTENDED] Message {i} cache_control: {message['cache_control']}")
            else:
                role = getattr(message, 'role', 'unknown')
                print(f"[EXTENDED] Message {i}: role={role}, type={type(message)}")

    async def generate_content_async(  # noqa: C901
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Generates content asynchronously.

        Args:
            llm_request: LlmRequest, the request to send to the LiteLlm model.
            stream: bool = False, whether to do streaming call.

        Yields:
            LlmResponse: The model response.
        """
        import sys
        print(f"[EXTENDED] generate_content_async called for model: {self.model}")
        print("[EXTENDED-STDERR] generate_content_async called", file=sys.stderr)
        logger.warning("[EXTENDED] generate_content_async - This should always show up!")

        self._maybe_append_user_content(llm_request)
        logger.debug(_build_request_log(llm_request))

        # Use parent's _get_completion_inputs (module function, not self method)
        print("[EXTENDED] About to call _get_completion_inputs")
        messages, tools, response_format, generation_params = (
            _get_completion_inputs(llm_request)
        )
        print("[EXTENDED] Completed _get_completion_inputs call")

        # SIMPLE FIX: Convert developer->system for non-OpenAI models to prevent LiteLLM role conversion
        print("[EXTENDED] About to apply role conversion and caching")
        self._apply_role_conversion_and_caching(messages)
        print("[EXTENDED] Completed role conversion and caching")

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
            yield _model_response_to_generate_content_response(response)

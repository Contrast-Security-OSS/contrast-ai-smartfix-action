from typing import Any, AsyncGenerator, List

# Note: These imports work when this file is in your project that uses ADK
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse

from src.utils import log, debug_log


class ExtendedLiteLlm(LiteLlm):
    """
    Extended LiteLlm with prompt caching support.

    This class adds prompt caching capabilities to the Google ADK's LiteLlm implementation.
    It automatically applies caching to system instructions when enabled and supported.

    SUPPORTED PROVIDERS (for prompt caching):
    ✅ OpenAI (openai/) - Automatic caching for 1024+ tokens
    ✅ Azure OpenAI (azure/) - Automatic caching for 1024+ tokens
    ✅ Anthropic (anthropic/) - Manual cache_control required
    ✅ AWS Bedrock (bedrock/) - Depends on specific model

    WORKS WITHOUT CACHING:
    ⚪ Gemini models - Will work normally, just without prompt caching
    ⚪ Other unsupported providers - Will work normally, just without prompt caching

    Example usage:
    ```python
    # Anthropic (manual cache control)
    model_instance = ExtendedLiteLlm(
        model="anthropic/claude-3-5-sonnet-20240620",
        cache_system_instruction=True,
        temperature=0.2
    )

    # OpenAI (automatic caching)
    model_instance = ExtendedLiteLlm(
        model="openai/gpt-4o",
        cache_system_instruction=True,
        temperature=0.2
    )

    # Deepseek (supports caching)
    model_instance = ExtendedLiteLlm(
        model="deepseek/deepseek-chat",
        cache_system_instruction=True,
        temperature=0.2
    )

    # Gemini (works without caching - not supported by LiteLLM)
    model_instance = ExtendedLiteLlm(
        model="gemini-1.5-pro",
        cache_system_instruction=True,  # Will be ignored with warning
        temperature=0.2
    )
    ```

    Attributes:
        cache_system_instruction (bool): Whether to apply caching to system instructions
        cache_control_type (str): Type of cache control ("ephemeral" for Anthropic)
    """

    def __init__(
        self,
        model: str,
        cache_system_instruction: bool = False,
        cache_control_type: str = "ephemeral",
        **kwargs
    ):
        """
        Initialize ExtendedLiteLlm.

        Args:
            model: The model name (e.g., "anthropic/claude-3-5-sonnet-20240620")
            cache_system_instruction: Whether to enable caching for system instructions
            cache_control_type: Type of cache control to use
            **kwargs: Additional arguments passed to LiteLlm
        """
        # Call parent constructor first
        super().__init__(model=model, **kwargs)

        # Store our custom parameters using object.__setattr__ to bypass field validation
        object.__setattr__(self, '_cache_system_instruction', cache_system_instruction)
        object.__setattr__(self, '_cache_control_type', cache_control_type)

        # Log if caching is enabled
        if cache_system_instruction:
            log(f"Prompt caching enabled for {model} with cache_control_type: {cache_control_type}")
            debug_log(f"ExtendedLiteLlm initialized with caching enabled for model: {model}")
            debug_log(f"Model supports caching: {self._supports_caching()}")

    @property
    def cache_system_instruction(self) -> bool:
        """Get the cache system instruction setting."""
        return getattr(self, '_cache_system_instruction', False)

    @property
    def cache_control_type(self) -> str:
        """Get the cache control type setting."""
        return getattr(self, '_cache_control_type', 'ephemeral')

    def _supports_caching(self) -> bool:
        """Check if the current model supports prompt caching.

        Based on official LiteLLM documentation, prompt caching is supported for:
        - OpenAI (openai/)
        - Anthropic API (anthropic/)
        - AWS Bedrock (bedrock/, bedrock/invoke/, bedrock/converse/)
        - Deepseek API (deepseek/)

        NOT supported:
        - Gemini/Vertex AI models
        - Azure OpenAI (not in official supported list)
        - Other providers
        """
        model_lower = self.model.lower()
        supported_prefixes = [
            "anthropic/",
            "openai/",
            "bedrock/",
            "deepseek/"
        ]

        # First check if it's a supported model
        is_supported = any(model_lower.startswith(prefix) for prefix in supported_prefixes)

        if is_supported:
            return True

        # Only if NOT supported, check for specific unsupported patterns and warn
        unsupported_patterns = [
            "gemini",
            "vertex_ai/gemini",
            "azure/",  # Azure OpenAI not officially supported
        ]

        # Log info for unsupported models if caching is requested
        if self.cache_system_instruction:
            for pattern in unsupported_patterns:
                if pattern in model_lower:
                    if "gemini" in pattern:
                        log(
                            f"Prompt caching requested for {self.model}. "
                            f"Gemini models don't support prompt caching in LiteLLM. "
                            f"Model will work normally without caching. "
                            f"Supported providers: OpenAI, Anthropic, Bedrock, Deepseek"
                        )
                    elif "azure" in pattern:
                        log(
                            f"Prompt caching requested for {self.model}. "
                            f"Azure OpenAI prompt caching is not officially supported by LiteLLM. "
                            f"Model will work normally without caching."
                        )
                    return False

            # Generic warning for other unsupported models
            log(
                f"Prompt caching requested for {self.model}. "
                f"This model doesn't support prompt caching in LiteLLM. "
                f"Supported providers: OpenAI, Anthropic, Bedrock, Deepseek"
            )

        return False

    def _apply_cache_control_to_litellm_messages(self, messages: List[Any]) -> None:
        """Apply cache control to LiteLLM messages for Anthropic-style providers."""
        debug_log("[CACHE] === CACHE CONTROL APPLICATION START ===")
        debug_log(f"[CACHE] Adding cache control to {len(messages)} LiteLLM messages")

        if not self._is_anthropic_model():
            debug_log(f"[CACHE] Model {self.model} doesn't need cache control (OpenAI auto-caches 1024+ tokens)")
            return

        # Cache the first developer/system message which contains the stable instructions
        # This is the approach that previously got cache hits
        cache_applied = False
        for i, message in enumerate(messages):
            role, content = self._extract_message_parts(message)
            debug_log(f"[CACHE] Message {i}: role='{role}', content_length={len(str(content)) if content else 'None'}")

            # Apply cache control to developer/system messages (these are typically long and reused)
            if role in ['system', 'developer'] and content is not None:
                debug_log(f"[CACHE] Applying cache control to {role} message at index {i}")
                if self._apply_cache_to_content(message, content):
                    cache_applied = True
                    debug_log(f"[CACHE] [OK] Applied cache control to {role} message")
                    break  # Only cache the first suitable message found
                else:
                    debug_log(f"[CACHE] [!] Failed to apply cache control to {role} message")

        if not cache_applied:
            debug_log("[CACHE] [!] No suitable message found for cache control")

        debug_log("[CACHE] === CACHE CONTROL APPLICATION END ===")

    def _is_anthropic_model(self) -> bool:
        """Check if the model is Anthropic-based."""
        model_lower = self.model.lower()
        is_anthropic_bedrock = model_lower.startswith("bedrock/") and "anthropic" in model_lower
        return model_lower.startswith("anthropic/") or is_anthropic_bedrock

    def _extract_message_parts(self, message: Any) -> tuple:
        """Extract role and content from message (dict or object format)."""
        role = None
        content = None

        if isinstance(message, dict):
            role = message.get('role')
            content = message.get('content')
        elif hasattr(message, 'role'):
            role = getattr(message, 'role', None)
            content = getattr(message, 'content', None)

        return role, content

    def _apply_cache_to_content(self, message: Any, content: Any) -> bool:
        """Apply cache control to message content. Returns True if successful."""
        if isinstance(content, str):
            return self._apply_cache_to_string_content(message, content)
        elif isinstance(content, list) and len(content) > 0:
            return self._apply_cache_to_list_content(content)

        return False

    def _apply_cache_to_string_content(self, message: Any, content: str) -> bool:
        """Apply cache control to string content."""
        new_content = [{
            "type": "text",
            "text": content,
            "cache_control": {"type": self.cache_control_type}
        }]

        if isinstance(message, dict):
            message['content'] = new_content
        else:
            message.content = new_content

        return True

    def _apply_cache_to_list_content(self, content: List[Any]) -> bool:
        """Apply cache control to list content."""
        debug_log(f"Content is already a list with {len(content)} items")

        # Find the last text item and add cache control to it
        for j in range(len(content) - 1, -1, -1):
            content_item = content[j]
            if isinstance(content_item, dict) and content_item.get("type") == "text":
                content_item["cache_control"] = {"type": self.cache_control_type}
                debug_log(f"Added cache control to existing text item at index {j}")
                return True

        # If no text items found, convert the first item if it's a string
        if content and isinstance(content[0], str):
            content[0] = {
                "type": "text",
                "text": content[0],
                "cache_control": {"type": self.cache_control_type}
            }
            debug_log("Converted first string item to text with cache control")
            return True

        return False

    async def _prepare_completion_args(self, llm_request: LlmRequest) -> tuple:
        """Prepare completion arguments by converting ADK request to LiteLLM format."""
        debug_log("[PREPARE] === PREPARE COMPLETION ARGS START ===")
        debug_log(f"[PREPARE] Request has {len(llm_request.contents)} contents")

        from google.adk.models.lite_llm import _get_completion_inputs, _build_request_log
        import logging
        logger = logging.getLogger(__name__)

        # Prepare the request the same way as parent class
        self._maybe_append_user_content(llm_request)
        logger.debug(_build_request_log(llm_request))

        # Convert ADK request to LiteLLM format
        debug_log("[PREPARE] Converting ADK request to LiteLLM format...")
        messages, tools, response_format, generation_params = _get_completion_inputs(llm_request)
        debug_log(f"[PREPARE] Converted to {len(messages)} LiteLLM messages, {len(tools) if tools else 0} tools")

        # Apply cache control to the LiteLLM messages if caching is enabled
        if self.cache_system_instruction and self._supports_caching():
            debug_log("[PREPARE] Applying cache control to converted LiteLLM messages")
            self._apply_cache_control_to_litellm_messages(messages)
        else:
            debug_log(f"[PREPARE] Skipping cache control - enabled: {self.cache_system_instruction}, supported: {self._supports_caching()}")

        # Prepare completion arguments same as parent
        if "functions" in self._additional_args:
            # LiteLLM does not support both tools and functions together.
            debug_log("[PREPARE] Removing tools due to functions in additional_args")
            tools = None

        completion_args = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "response_format": response_format,
        }
        completion_args.update(self._additional_args)

        if generation_params:
            debug_log(f"[PREPARE] Adding generation params: {list(generation_params.keys())}")
            completion_args.update(generation_params)

        debug_log(f"[PREPARE] Final completion args keys: {list(completion_args.keys())}")
        debug_log("[PREPARE] === PREPARE COMPLETION ARGS END ===")
        return completion_args

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """
        Generate content with caching support.

        This method applies cache control to the LiteLLM messages and then delegates
        to the parent class to preserve proper agent loop functionality.
        """
        debug_log("=== GENERATE CONTENT START ===")
        debug_log(f"Model: {self.model}")
        debug_log(f"Stream mode: {stream}")
        debug_log(f"Cache enabled: {self.cache_system_instruction}")

        # If caching is enabled and supported, we need to intercept and modify messages
        if self.cache_system_instruction and self._supports_caching():
            debug_log("[CACHE-INTERCEPT] Intercepting to apply cache control")

            # Step 1: Prepare the completion args to get converted messages
            completion_args = await self._prepare_completion_args(llm_request)

            # Step 2: Now call LiteLLM directly with our cached messages
            # but preserve all the parent class's response handling logic
            async for response in self._call_litellm_with_caching(completion_args, stream):
                yield response
        else:
            debug_log("[NO-CACHE] Delegating to parent class directly")
            # No caching - just use parent implementation
            async for response in super().generate_content_async(llm_request, stream):
                yield response

        debug_log("=== GENERATE CONTENT END ===")

    async def _call_litellm_with_caching(self, completion_args: dict, stream: bool) -> AsyncGenerator[LlmResponse, None]:
        """Call LiteLLM with cached messages, preserving agent loop functionality."""
        if stream:
            async for response in self._handle_cached_streaming(completion_args):
                yield response
        else:
            async for response in self._handle_cached_non_streaming(completion_args):
                yield response

    async def _handle_cached_streaming(self, completion_args: dict) -> AsyncGenerator[LlmResponse, None]:
        """Handle cached streaming responses."""
        debug_log("[CACHED-STREAM] Taking CACHED-STREAMING path")

        # Import necessary components from parent class
        from google.adk.models.lite_llm import _model_response_to_chunk, _message_to_generate_content_response

        # Initialize streaming state
        text = ""
        function_calls = {}  # index -> {name, args, id}
        completion_args["stream"] = True
        usage_metadata = None
        fallback_index = 0

        async for part in await self.llm_client.acompletion(**completion_args):
            # Use parent's chunk processing logic
            for chunk, finish_reason in _model_response_to_chunk(part):
                # Process different chunk types
                if await self._process_streaming_chunk(chunk, function_calls, fallback_index, text):
                    # Text chunk was processed - yield partial response
                    text += chunk.text
                    yield _message_to_generate_content_response(
                        self._create_assistant_message(content=chunk.text),
                        is_partial=True,
                    )
                elif type(chunk).__name__ == "UsageMetadataChunk":
                    usage_metadata = await self._process_usage_chunk(chunk)

                # Handle finish conditions
                if finish_reason in ["tool_calls", "stop"]:
                    final_response = await self._create_final_streaming_response(
                        finish_reason, function_calls, text, usage_metadata
                    )
                    if final_response:
                        yield final_response

        debug_log("[CACHED-STREAM] CACHED-STREAMING complete")

    async def _handle_cached_non_streaming(self, completion_args: dict) -> AsyncGenerator[LlmResponse, None]:
        """Handle cached non-streaming responses."""
        debug_log("[CACHED-NON-STREAM] Taking CACHED-NON-STREAMING path")

        from google.adk.models.lite_llm import _message_to_generate_content_response

        # Non-streaming call
        debug_log("[CACHED-NON-STREAM] Calling llm_client.acompletion...")
        response = await self.llm_client.acompletion(**completion_args)
        debug_log(f"[CACHED-NON-STREAM] Got LiteLLM response: {type(response).__name__}")

        llm_response = _message_to_generate_content_response(response)
        debug_log(f"[CACHED-NON-STREAM] Converted to ADK response: {type(llm_response).__name__}")

        # Log cache information
        await self._log_cache_info(response)

        debug_log("[CACHED-NON-STREAM] Yielding cached non-streaming response")
        yield llm_response
        debug_log("[CACHED-NON-STREAM] CACHED-NON-STREAMING complete")

    def _create_assistant_message(self, content: str, tool_calls=None):
        """Create assistant message compatible with LiteLLM."""
        try:
            from litellm import ChatCompletionAssistantMessage
            return ChatCompletionAssistantMessage(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
            )
        except ImportError:
            # Fallback for different LiteLLM versions
            message = {"role": "assistant", "content": content}
            if tool_calls:
                message["tool_calls"] = tool_calls
            return message

    def _create_tool_call(self, call_data: dict):
        """Create tool call compatible with LiteLLM."""
        try:
            from litellm import ChatCompletionMessageToolCall
            return ChatCompletionMessageToolCall(
                id=call_data["id"],
                function={"name": call_data["name"], "arguments": call_data["args"]},
                type="function",
            )
        except ImportError:
            # Fallback for different LiteLLM versions
            return {
                "id": call_data["id"],
                "function": {"name": call_data["name"], "arguments": call_data["args"]},
                "type": "function",
            }

    async def _process_streaming_chunk(self, chunk, function_calls: dict, fallback_index: int, text: str) -> bool:
        """Process a streaming chunk. Returns True if it's a text chunk."""
        import json

        chunk_type = type(chunk).__name__

        if chunk_type == "FunctionChunk":
            index = getattr(chunk, 'index', None) or fallback_index
            if index not in function_calls:
                function_calls[index] = {"name": "", "args": "", "id": None}

            if hasattr(chunk, 'name') and chunk.name:
                function_calls[index]["name"] += chunk.name
            if hasattr(chunk, 'args') and chunk.args:
                function_calls[index]["args"] += chunk.args

                # check if args is completed (workaround for improper chunk indexing)
                try:
                    json.loads(function_calls[index]["args"])
                    fallback_index += 1
                except json.JSONDecodeError:
                    pass

            function_calls[index]["id"] = (
                getattr(chunk, 'id', None) or function_calls[index]["id"] or str(index)
            )
            return False
        elif chunk_type == "TextChunk":
            return True

        return False

    async def _process_usage_chunk(self, chunk):
        """Process usage metadata chunk."""
        from google.genai import types

        # Log cache information for debugging
        cached_tokens = getattr(chunk, 'cached_tokens', 0)
        if cached_tokens > 0:
            debug_log(f"[OK] Cache hit! Cached tokens: {cached_tokens}")

        return types.GenerateContentResponseUsageMetadata(
            prompt_token_count=chunk.prompt_tokens,
            candidates_token_count=chunk.completion_tokens,
            total_token_count=chunk.total_tokens,
        )

    async def _create_final_streaming_response(self, finish_reason: str, function_calls: dict, text: str, usage_metadata):
        """Create final streaming response based on finish reason."""
        from google.adk.models.lite_llm import _message_to_generate_content_response

        if function_calls and finish_reason == "tool_calls":
            # Convert function calls and yield response
            tool_calls = [
                self._create_tool_call(call_data)
                for call_data in function_calls.values()
                if call_data["name"] and call_data["args"]
            ]

            return _message_to_generate_content_response(
                self._create_assistant_message(
                    content=text,
                    tool_calls=tool_calls,
                ),
                usage_metadata=usage_metadata,
            )
        elif finish_reason == "stop":
            return _message_to_generate_content_response(
                self._create_assistant_message(content=text),
                usage_metadata=usage_metadata,
            )

        return None

    async def _log_cache_info(self, response):
        """Log cache information from LiteLLM response."""
        if hasattr(response, 'usage') and response.usage:
            usage = response.usage
            if hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
                cached_tokens = getattr(usage.prompt_tokens_details, 'cached_tokens', 0)
                if cached_tokens > 0:
                    debug_log(f"[OK] Cache hit! Cached tokens: {cached_tokens}")
                else:
                    debug_log(f"Cache miss - Prompt tokens: {usage.prompt_tokens}")

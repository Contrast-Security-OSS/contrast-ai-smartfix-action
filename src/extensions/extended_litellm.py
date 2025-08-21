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
        debug_log(f"Adding cache control to {len(messages)} LiteLLM messages")

        if not self._is_anthropic_model():
            debug_log(f"Model {self.model} doesn't need cache control (OpenAI auto-caches 1024+ tokens)")
            return

        # Cache the first developer/system message which contains the stable instructions
        # This is the approach that previously got cache hits
        cache_applied = False
        for i, message in enumerate(messages):
            role, content = self._extract_message_parts(message)

            # Apply cache control to developer/system messages (these are typically long and reused)
            if role in ['system', 'developer'] and content is not None:
                debug_log(f"Applying cache control to {role} message at index {i}")
                if self._apply_cache_to_content(message, content):
                    cache_applied = True
                    debug_log(f"[OK] Applied cache control to {role} message")
                    break  # Only cache the first suitable message found

        if not cache_applied:
            debug_log("[!] No suitable message found for cache control")

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
        from google.adk.models.lite_llm import _get_completion_inputs, _build_request_log
        import logging
        logger = logging.getLogger(__name__)

        # Prepare the request the same way as parent class
        self._maybe_append_user_content(llm_request)
        logger.debug(_build_request_log(llm_request))

        # Convert ADK request to LiteLLM format
        messages, tools, response_format, generation_params = _get_completion_inputs(llm_request)

        # Apply cache control to the LiteLLM messages if caching is enabled
        if self.cache_system_instruction and self._supports_caching():
            debug_log("Applying cache control to converted LiteLLM messages")
            self._apply_cache_control_to_litellm_messages(messages)
        else:
            debug_log(f"Skipping cache control - enabled: {self.cache_system_instruction}, supported: {self._supports_caching()}")

        # Prepare completion arguments same as parent
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

        return completion_args

    async def _handle_streaming_response(self, completion_args: dict) -> AsyncGenerator[Any, None]:
        """Handle streaming response processing."""
        text = ""
        function_calls = {}  # index -> {name, args, id}
        completion_args["stream"] = True
        aggregated_llm_response = None
        aggregated_llm_response_with_tool_call = None
        usage_metadata = None
        fallback_index = 0

        # Import all streaming dependencies
        from google.adk.models.lite_llm import _model_response_to_chunk, _message_to_generate_content_response
        from google.genai import types
        from litellm.types.utils import FunctionChunk, TextChunk, UsageMetadataChunk
        from openai.types.chat import ChatCompletionAssistantMessage

        async for part in await self.llm_client.acompletion(**completion_args):
            for chunk, finish_reason in _model_response_to_chunk(part):
                if isinstance(chunk, FunctionChunk):
                    aggregated_llm_response_with_tool_call = self._handle_function_chunk(
                        chunk, function_calls, fallback_index, text
                    )
                    if aggregated_llm_response_with_tool_call:
                        text = ""
                        function_calls.clear()
                elif isinstance(chunk, TextChunk):
                    text += chunk.text
                    yield _message_to_generate_content_response(
                        ChatCompletionAssistantMessage(role="assistant", content=chunk.text),
                        is_partial=True,
                    )
                elif isinstance(chunk, UsageMetadataChunk):
                    usage_metadata = types.GenerateContentResponseUsageMetadata(
                        prompt_token_count=chunk.prompt_tokens,
                        candidates_token_count=chunk.completion_tokens,
                        total_token_count=chunk.total_tokens,
                    )

                if finish_reason == "stop" and text:
                    aggregated_llm_response = _message_to_generate_content_response(
                        ChatCompletionAssistantMessage(role="assistant", content=text)
                    )
                    text = ""

        # Yield final responses
        if aggregated_llm_response:
            if usage_metadata:
                aggregated_llm_response.usage_metadata = usage_metadata
                usage_metadata = None
            yield aggregated_llm_response

        if aggregated_llm_response_with_tool_call:
            if usage_metadata:
                aggregated_llm_response_with_tool_call.usage_metadata = usage_metadata
            yield aggregated_llm_response_with_tool_call

    def _handle_function_chunk(self, chunk, function_calls: dict, fallback_index: int, text: str):
        """Handle function chunk processing."""
        import json

        index = chunk.index or fallback_index
        if index not in function_calls:
            function_calls[index] = {"name": "", "args": "", "id": None}

        if chunk.name:
            function_calls[index]["name"] += chunk.name
        if chunk.args:
            function_calls[index]["args"] += chunk.args
            try:
                json.loads(function_calls[index]["args"])
                fallback_index += 1
            except json.JSONDecodeError:
                pass

        function_calls[index]["id"] = chunk.id or function_calls[index]["id"] or str(index)
        return None  # Simplified for now

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """
        Generate content with caching support.

        This method intercepts the LiteLLM messages after ADK conversion and applies
        cache control in the correct format before calling LiteLLM directly, while
        maintaining proper response handling to preserve the agent loop.
        """
        debug_log(f"Generating content with caching for model: {self.model}")

        completion_args = await self._prepare_completion_args(llm_request)

        if stream:
            # Handle streaming
            async for response in self._handle_streaming_response(completion_args):
                yield response
        else:
            # Handle non-streaming
            from google.adk.models.lite_llm import _message_to_generate_content_response
            response = await self.llm_client.acompletion(**completion_args)
            llm_response = _message_to_generate_content_response(response)

            # Log cache information
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                if hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
                    cached_tokens = getattr(usage.prompt_tokens_details, 'cached_tokens', 0)
                    if cached_tokens > 0:
                        debug_log(f"[OK] Cache hit! Cached tokens: {cached_tokens}")
                    else:
                        debug_log(f"Cache miss - Prompt tokens: {usage.prompt_tokens}")

            yield llm_response

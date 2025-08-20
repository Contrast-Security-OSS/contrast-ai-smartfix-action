from typing import Any, AsyncGenerator, Dict, List

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

        # Check for unsupported providers - only warn, don't fail
        unsupported_patterns = [
            "gemini",
            "vertex_ai/gemini",
            "azure/",  # Azure OpenAI not officially supported
            "claude",  # Direct Claude without anthropic/ prefix
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
                    else:
                        log(
                            f"Prompt caching requested for {self.model}. "
                            f"This model doesn't support prompt caching in LiteLLM. "
                            f"Supported providers: OpenAI, Anthropic, Bedrock, Deepseek"
                        )
                    return False

        return any(model_lower.startswith(prefix) for prefix in supported_prefixes)

    def _apply_cache_control_to_request(self, llm_request: LlmRequest) -> None:
        """Apply cache control directly to the LlmRequest before message conversion."""
        if not self._supports_caching() or not self.cache_system_instruction:
            return

        debug_log(f"Applying cache control to LlmRequest for model: {self.model}")

        # Check if the request has contents (ADK's message format)
        if not hasattr(llm_request, 'contents') or not llm_request.contents:
            debug_log("No contents found in LlmRequest")
            return

        model_lower = self.model.lower()
        is_anthropic_bedrock = model_lower.startswith("bedrock/") and "anthropic" in model_lower

        # Only apply for Anthropic models (direct or Bedrock)
        if not (model_lower.startswith("anthropic/") or is_anthropic_bedrock):
            debug_log(f"Model {self.model} doesn't need cache control modification")
            return

        debug_log(f"Found {len(llm_request.contents)} contents in LlmRequest")

        # Apply cache control to the first suitable content (typically system/developer instructions)
        for i, content in enumerate(llm_request.contents):
            debug_log(f"Processing content {i}: {type(content)}")

            # Check if this content has a role that should be cached
            if hasattr(content, 'role'):
                role = content.role
                debug_log(f"Content {i} has role: {role}")

                if role in ['system', 'developer', 'user']:
                    debug_log(f"Applying cache control to {role} content at index {i}")

                    # Modify the content to include cache control
                    if hasattr(content, 'parts') and content.parts:
                        debug_log(f"Content has {len(content.parts)} parts")

                        # Apply cache control to the last text part
                        for j in range(len(content.parts) - 1, -1, -1):
                            part = content.parts[j]
                            if hasattr(part, 'text') and part.text:
                                debug_log(f"Adding cache_control to text part {j}")

                                # Try to add cache control to the part
                                try:
                                    # This might need to be adapted based on ADK's actual structure
                                    if not hasattr(part, 'cache_control'):
                                        object.__setattr__(part, 'cache_control', {'type': self.cache_control_type})
                                        debug_log(f"[OK] Added cache_control to {role} content part")
                                        return  # Only cache the first suitable content
                                    else:
                                        part.cache_control = {'type': self.cache_control_type}
                                        debug_log(f"[OK] Updated cache_control on {role} content part")
                                        return
                                except Exception as e:
                                    debug_log(f"Failed to add cache_control to part: {e}")

                        debug_log(f"No text parts found in {role} content")
                    else:
                        debug_log(f"Content {i} has no parts attribute")
            else:
                debug_log(f"Content {i} has no role attribute")

        debug_log("No suitable content found for cache control")

    def _add_anthropic_style_cache_control(self, messages: List[Any]) -> None:
        """Add cache_control to messages for Anthropic-style providers."""
        debug_log(f"Adding cache control to {len(messages)} messages")

        cache_applied = False
        for i, message in enumerate(messages):
            role = None
            content = None

            # Extract role and content from either dict or object format
            if isinstance(message, dict):
                role = message.get('role')
                content = message.get('content')
            elif hasattr(message, 'role'):
                role = getattr(message, 'role', None)
                content = getattr(message, 'content', None)

            # Apply cache control to cacheable messages (developer/system priority)
            if role in ['system', 'developer', 'user']:
                debug_log(f"Applying cache control to {role} message at index {i}")

                if content is not None:
                    content_length = len(str(content))
                    debug_log(f"Message content length: {content_length} characters")

                    # Handle different content formats
                    if isinstance(content, str):
                        # Convert string content to list format with cache control
                        new_content = [
                            {
                                "type": "text",
                                "text": content,
                                "cache_control": {"type": self.cache_control_type}
                            }
                        ]

                        # Update the message content
                        if isinstance(message, dict):
                            message['content'] = new_content
                        else:
                            message.content = new_content

                        cache_applied = True
                        debug_log(f"Converted string content ({content_length} chars) to list with cache control")

                    elif isinstance(content, list) and len(content) > 0:
                        debug_log(f"Content is already a list with {len(content)} items")
                        # Find the last text item and add cache control to it
                        for j in range(len(content) - 1, -1, -1):
                            content_item = content[j]
                            if (isinstance(content_item, dict) and content_item.get("type") == "text"):
                                content_item["cache_control"] = {"type": self.cache_control_type}
                                cache_applied = True
                                debug_log(f"Added cache control to existing text item at index {j}")
                                break

                        # If no text items found, convert the first item
                        if not cache_applied and content:
                            first_item = content[0]
                            if isinstance(first_item, str):
                                content[0] = {
                                    "type": "text",
                                    "text": first_item,
                                    "cache_control": {"type": self.cache_control_type}
                                }
                                cache_applied = True
                                debug_log("Converted first string item to text with cache control")

                # Cache the first cacheable message found
                if cache_applied:
                    debug_log(f"[OK] Applied cache control to {role} message")
                    break

        if not cache_applied:
            debug_log("[!] No suitable message found for cache control")

    def _log_cache_application(self, kwargs: Dict[str, Any]) -> None:
        """Log cache control application results."""
        if 'messages' not in kwargs:
            return

        cache_found = False
        for i, msg in enumerate(kwargs['messages']):
            role = msg.get('role') if isinstance(msg, dict) else getattr(msg, 'role', None)
            content = msg.get('content') if isinstance(msg, dict) else getattr(msg, 'content', None)

            if role in ['system', 'developer', 'user'] and isinstance(content, list):
                for j, item in enumerate(content):
                    if isinstance(item, dict) and 'cache_control' in item:
                        debug_log(f"[OK] Cache control applied to {role} message {i}")
                        # Log the exact structure for debugging
                        debug_log(f"Cache control structure: {item.get('cache_control')}")
                        item_type = item.get('type')
                        item_text = str(item.get('text', ''))[:50]
                        item_cache = item.get('cache_control')
                        debug_log(f"Content item structure: {{'type': '{item_type}', 'text': '{item_text}...', 'cache_control': {item_cache}}}")
                        cache_found = True
                        break
                if cache_found:
                    break

        if not cache_found:
            debug_log("[X] No cache control found in messages")

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """
        Generate content with caching support.

        This method applies cache control to the LlmRequest before it gets processed
        into LiteLLM format, which is the correct timing for cache control application.
        """
        debug_log(f"Generating content with caching for model: {self.model}")

        # Apply cache control directly to the LlmRequest BEFORE processing
        if self.cache_system_instruction and self._supports_caching():
            debug_log("Applying cache control to LlmRequest before message conversion")
            self._apply_cache_control_to_request(llm_request)
        else:
            debug_log(f"Skipping cache control - enabled: {self.cache_system_instruction}, supported: {self._supports_caching()}")

        # Now call the parent implementation with the modified request
        async for response in super().generate_content_async(llm_request, stream):
            # Log cache hit information if available
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                if hasattr(usage, 'cached_content_token_count') and usage.cached_content_token_count:
                    debug_log(f"[OK] Cache hit! Cached tokens: {usage.cached_content_token_count}")
                elif hasattr(usage, 'prompt_token_count'):
                    debug_log(f"Cache miss - Prompt tokens: {usage.prompt_token_count}")

            yield response

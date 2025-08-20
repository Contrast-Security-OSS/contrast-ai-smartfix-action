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

    # Azure OpenAI (automatic caching)
    model_instance = ExtendedLiteLlm(
        model="azure/gpt-4o",
        cache_system_instruction=True,
        temperature=0.2
    )

    # Gemini (works without caching)
    model_instance = ExtendedLiteLlm(
        model="gemini-1.5-pro",
        cache_system_instruction=True,  # Will be ignored, but no errors
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

        Based on LiteLLM documentation, prompt caching is supported for:
        - OpenAI (openai/)
        - Azure OpenAI (azure/) - treated like OpenAI
        - Anthropic (anthropic/)
        - AWS Bedrock (bedrock/, bedrock/invoke/, bedrock/converse/)

        NOT supported:
        - Gemini models (but will work without caching)
        - Deepseek (not supported due to policy restrictions)
        """
        model_lower = self.model.lower()
        supported_prefixes = [
            "anthropic/",
            "openai/",
            "azure/",  # Treat Azure OpenAI like regular OpenAI
            "bedrock/"
        ]

        # Check for unsupported providers - only warn, don't fail
        unsupported_patterns = [
            "gemini",
            "vertex_ai/gemini",
            "deepseek"  # Not supported due to policy restrictions
        ]

        # Log info for unsupported models if caching is requested
        if self.cache_system_instruction:
            if any(pattern in model_lower for pattern in unsupported_patterns):
                if "deepseek" in model_lower:
                    log(
                        f"Deepseek model {self.model} is not supported due to policy restrictions. "
                        f"Model will work normally without caching."
                    )
                else:
                    log(
                        f"Prompt caching requested for {self.model}. "
                        f"This model doesn't support prompt caching, but will work normally without it. "
                        f"Caching is available for: OpenAI, Azure OpenAI, Anthropic, AWS Bedrock"
                    )
                return False

        return any(model_lower.startswith(prefix) for prefix in supported_prefixes)

    def _add_cache_control(self, completion_args: Dict[str, Any]) -> None:
        """
        Add cache control to model messages based on provider.

        Different providers have different requirements:
        - Anthropic: Requires cache_control in content objects
        - OpenAI/Azure OpenAI: Automatic caching for 1024+ tokens, no special formatting needed
        - AWS Bedrock: Follows provider-specific format (Anthropic models use cache_control)
        - Deepseek: Works like OpenAI

        This modifies the completion_args in place.
        """
        if not self._supports_caching() or not self.cache_system_instruction:
            return

        messages = completion_args.get("messages", [])
        if not messages:
            return

        model_lower = self.model.lower()

        # For Anthropic models (including Bedrock Anthropic), add cache_control
        is_anthropic_bedrock = model_lower.startswith("bedrock/") and "anthropic" in model_lower
        if model_lower.startswith("anthropic/") or is_anthropic_bedrock:
            debug_log(f"Detected Anthropic model (direct or via Bedrock): {self.model}")
            self._add_anthropic_style_cache_control(messages)
        elif model_lower.startswith(("openai/", "azure/")):
            # OpenAI and Azure OpenAI handle caching automatically for 1024+ tokens
            # No special formatting needed, but log that caching is attempted
            provider = "Azure OpenAI" if model_lower.startswith("azure/") else "OpenAI"
            debug_log(f"{provider} model detected - automatic caching will apply for content with 1024+ tokens")
        elif model_lower.startswith("bedrock/"):
            # For non-Anthropic Bedrock models, check what's supported
            debug_log("Bedrock model detected - cache support depends on specific model")

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

                    elif isinstance(content, list) and len(content) > 0:
                        # Find the last text item and add cache control to it
                        for j in range(len(content) - 1, -1, -1):
                            content_item = content[j]
                            if (isinstance(content_item, dict) and content_item.get("type") == "text"):
                                content_item["cache_control"] = {"type": self.cache_control_type}
                                cache_applied = True
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
                for item in content:
                    if isinstance(item, dict) and 'cache_control' in item:
                        debug_log(f"[OK] Cache control applied to {role} message {i}")
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

        This method intercepts the completion arguments and adds cache control
        before calling the parent implementation.
        """
        debug_log(f"Generating content with caching for model: {self.model}")

        # Store the original acompletion method
        original_acompletion = getattr(self.llm_client, 'acompletion', None)

        async def cached_acompletion(**kwargs):
            """Wrapper that adds caching before calling completion."""
            if self.cache_system_instruction and self._supports_caching():
                debug_log(f"Applying cache control for {self.model}")

                # Apply cache control
                self._add_cache_control(kwargs)

                # Verify cache control was applied
                self._log_cache_application(kwargs)
            else:
                debug_log(f"Skipping cache control - enabled: {self.cache_system_instruction}, supported: {self._supports_caching()}")

            # Call the original method
            if original_acompletion:
                result = await original_acompletion(**kwargs)
                return result
            else:
                raise RuntimeError("acompletion method not available")

        # Set up interception if acompletion method exists
        if original_acompletion:
            self.llm_client.acompletion = cached_acompletion
        else:
            debug_log("[!] Cannot intercept - acompletion method not found")

        try:
            # Call the parent implementation
            async for response in super().generate_content_async(llm_request, stream):
                # Log cache hit information if available
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    usage = response.usage_metadata
                    if hasattr(usage, 'cached_content_token_count') and usage.cached_content_token_count:
                        debug_log(f"[OK] Cache hit! Cached tokens: {usage.cached_content_token_count}")
                    elif hasattr(usage, 'prompt_token_count'):
                        debug_log(f"Cache miss - Prompt tokens: {usage.prompt_token_count}")

                yield response
        finally:
            # Restore the original method
            if original_acompletion:
                self.llm_client.acompletion = original_acompletion

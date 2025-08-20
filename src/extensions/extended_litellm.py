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
        debug_log(f"Adding Anthropic-style cache control to {len(messages)} messages")

        # For Anthropic models, we need to modify the system message
        # According to LiteLLM docs, cache_control should be on the last content item
        cache_applied = False
        for i, message in enumerate(messages):
            if hasattr(message, 'role') and message.role == 'system':
                debug_log(f"Found system message at index {i}")
                if hasattr(message, 'content'):
                    debug_log(f"Message content type: {type(message.content)}")

                    # Handle different content formats
                    if isinstance(message.content, str):
                        debug_log(f"Converting string system content to list with cache control")
                        # Convert string content to list format with cache control on the text item
                        message.content = [
                            {
                                "type": "text",
                                "text": message.content,
                                "cache_control": {"type": self.cache_control_type}
                            }
                        ]
                        cache_applied = True
                        debug_log(f"Applied cache_control to string content: {self.cache_control_type}")
                    elif isinstance(message.content, list) and len(message.content) > 0:
                        debug_log(f"System message content is list with {len(message.content)} items")
                        # Find the last text item and add cache control to it
                        for j in range(len(message.content) - 1, -1, -1):  # Iterate backwards
                            content_item = message.content[j]
                            if (isinstance(content_item, dict) and content_item.get("type") == "text"):
                                debug_log(f"Adding cache_control to last text item at index {j}")
                                content_item["cache_control"] = {"type": self.cache_control_type}
                                cache_applied = True
                                debug_log(f"Applied cache_control to list content item {j}: {self.cache_control_type}")
                                break

                        # If no text items found, convert the whole thing
                        if not cache_applied and message.content:
                            debug_log(f"No text items found, converting first item to text with cache control")
                            first_item = message.content[0]
                            if isinstance(first_item, str):
                                message.content[0] = {
                                    "type": "text",
                                    "text": first_item,
                                    "cache_control": {"type": self.cache_control_type}
                                }
                                cache_applied = True
                                debug_log(f"Converted first string item to text with cache control")

                # Only modify the first system message we find
                if cache_applied:
                    break

        if cache_applied:
            debug_log(f"[OK] Successfully applied cache control to system message")
        else:
            debug_log(f"[!] WARNING: Could not find suitable system message to apply cache control")

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """
        Generate content with caching support.

        This method intercepts the completion arguments and adds cache control
        before calling the parent implementation.
        """
        # Store the original acompletion method
        original_acompletion = self.llm_client.acompletion

        async def cached_acompletion(**kwargs):
            """Wrapper that adds caching before calling completion."""
            debug_log(f">>> cached_acompletion wrapper called for model: {self.model}")
            debug_log(f"cache_system_instruction: {self.cache_system_instruction}")
            debug_log(f"_supports_caching(): {self._supports_caching()}")

            if self.cache_system_instruction and self._supports_caching():
                debug_log(f"[OK] Applying cache control to completion args for model: {self.model}")
                debug_log(f"Completion args keys: {list(kwargs.keys())}")

                if 'messages' in kwargs:
                    debug_log(f"Number of messages: {len(kwargs['messages'])}")
                    for i, msg in enumerate(kwargs['messages']):
                        if hasattr(msg, 'role'):
                            role = getattr(msg, 'role', 'unknown')
                            content = getattr(msg, 'content', None)
                            content_type = type(content)
                            debug_log(f"Message {i}: role={role}, content_type={content_type}")

                            # Log first 100 chars of content for system messages
                            if role == 'system' and content:
                                content_preview = str(content)[:100] + "..." if len(str(content)) > 100 else str(content)
                                debug_log(f"  System message preview: {content_preview}")

                # Apply cache control
                self._add_cache_control(kwargs)

                # Verify cache control was applied
                if 'messages' in kwargs:
                    for i, msg in enumerate(kwargs['messages']):
                        if hasattr(msg, 'role') and getattr(msg, 'role') == 'system':
                            content = getattr(msg, 'content', None)
                            debug_log(f"After cache control - System message {i} content type: {type(content)}")
                            if isinstance(content, list) and len(content) > 0:
                                for j, item in enumerate(content):
                                    if isinstance(item, dict) and 'cache_control' in item:
                                        debug_log(f"  [OK] Found cache_control in content item {j}: {item.get('cache_control')}")
                                    else:
                                        debug_log(f"  [X] No cache_control in content item {j}: {type(item)}")

                debug_log(f"[OK] Applied prompt caching to model call: {self.model}")
            else:
                debug_log(f"[X] Skipping cache control - cache_system_instruction: {self.cache_system_instruction}, supports_caching: {self._supports_caching()}")

            # Call the original method
            debug_log(f">>> Calling original acompletion method")
            result = await original_acompletion(**kwargs)
            debug_log(f"[OK] Original acompletion completed")
            return result

        # Temporarily replace the acompletion method
        self.llm_client.acompletion = cached_acompletion

        try:
            # Call the parent implementation
            async for response in super().generate_content_async(llm_request, stream):
                # Check if we got cached tokens in the response
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    usage = response.usage_metadata
                    if hasattr(usage, 'prompt_tokens_details'):
                        # Log cache hit information if available
                        debug_log(f"Prompt caching stats - Model: {self.model}")

                yield response
        finally:
            # Restore the original method
            self.llm_client.acompletion = original_acompletion

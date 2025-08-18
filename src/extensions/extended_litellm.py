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
        super().__init__(model=model, **kwargs)
        self.cache_system_instruction = cache_system_instruction
        self.cache_control_type = cache_control_type

        # Log if caching is enabled
        if cache_system_instruction:
            log(f"Prompt caching enabled for {model} with cache_control_type: {cache_control_type}")

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
        if model_lower.startswith(("anthropic/", "bedrock/anthropic")):
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
        # For Anthropic models, we need to modify the system/developer message
        for message in messages:
            if hasattr(message, 'role') and message.role in ['system', 'developer']:
                if hasattr(message, 'content'):
                    # Handle different content formats
                    if isinstance(message.content, str):
                        # Convert string content to object format with cache control
                        message.content = [
                            {
                                "type": "text",
                                "text": message.content,
                                "cache_control": {"type": self.cache_control_type}
                            }
                        ]
                    elif isinstance(message.content, list):
                        # Add cache control to the last text item
                        for i, content_item in enumerate(message.content):
                            if (isinstance(content_item, dict)
                                    and content_item.get("type") == "text"
                                    and i == len(message.content) - 1):  # Last text item
                                content_item["cache_control"] = {"type": self.cache_control_type}
                break  # Only modify the first system message

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
            if self.cache_system_instruction and self._supports_caching():
                self._add_cache_control(kwargs)
                debug_log(f"Applied prompt caching to model call: {self.model}")

            return await original_acompletion(**kwargs)

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

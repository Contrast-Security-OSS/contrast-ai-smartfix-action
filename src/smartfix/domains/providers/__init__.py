import litellm
import os
from src.config import get_config
from src.contrast_api import normalize_host

config = get_config()


def setup_contrast_provider():
    """Setup Contrast Bedrock proxy as a custom provider."""

    # Register the model with litellm
    litellm.register_model({
        "contrast/claude-sonnet-4-5": {
            # Model capabilities
            "max_tokens": 8192,
            "max_input_tokens": 200000,
            "max_output_tokens": 8192,

            # Pricing (per token)
            "input_cost_per_token": 0.000003,
            "output_cost_per_token": 0.000015,

            # Prompt caching pricing
            "cache_creation_input_token_cost": 0.00000375,
            "cache_read_input_token_cost": 0.0000003,

            # Provider configuration
            "litellm_provider": "bedrock",  # Use Bedrock provider
            "mode": "chat",

            # Allow parameters not normally supported by bedrock
            "allowed_openai_params": ["temperature", "tools", "stream_options"],

            # Feature support
            "supports_function_calling": True,
            "supports_vision": True,
            "supports_prompt_caching": True,
            "supports_temperature": True,
        }
    })

    # Configure to use Contrast proxy (still uses Anthropic API format)
    os.environ["ANTHROPIC_API_BASE"] = f"https://{normalize_host(config.CONTRAST_HOST)}/api/v4/llm-proxy/organizations/{config.CONTRAST_ORG_ID}"
    os.environ["ANTHROPIC_API_KEY"] = f"{config.CONTRAST_API_KEY}"

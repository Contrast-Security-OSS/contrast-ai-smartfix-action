import litellm
import os
from src.config import get_config

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
            "litellm_provider": "anthropic",  # Use Anthropic provider
            "mode": "chat",

            # Feature support
            "supports_function_calling": True,
            "supports_vision": True,
            "supports_prompt_caching": True,
        }
    })

    # Configure to use Contrast proxy
    os.environ["ANTHROPIC_API_BASE"] = "https://teamserver-scantest.contsec.com/api/v4/llm-proxy/organizations/54d19270-7db5-442c-b4e7-faefac523c1e"  # config.BEDROCK_PROXY_URL
    os.environ["ANTHROPIC_API_KEY"] = "hpuBJysWV5zOR13X3miLoh08ctFa1Eod"  # config.CONTRAST_API_KEY

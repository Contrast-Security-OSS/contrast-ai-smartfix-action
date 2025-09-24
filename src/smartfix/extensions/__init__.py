"""SmartFix LLM Extensions

This package contains enhanced LLM integrations and extensions
that provide advanced functionality like prompt caching, cost tracking,
and multi-provider support.

Key Components:
- SmartFixLiteLlm: Enhanced LiteLLM with prompt caching and cost tracking
- SmartFixLlmAgent: Enhanced LLM agent with advanced capabilities
"""

import warnings

# Suppress specific Pydantic field shadowing warnings from ADK library
# This suppresses warnings about SequentialAgent.config_type shadowing BaseAgent.config_type
warnings.filterwarnings('ignore', message='.*config_type.*shadows.*', category=UserWarning)
warnings.filterwarnings('ignore', message='.*shadows an attribute.*', category=UserWarning)

# Import classes for easy access
try:
    from src.smartfix.extensions.smartfix_litellm import SmartFixLiteLlm  # noqa: F401
    from src.smartfix.extensions.smartfix_llm_agent import SmartFixLlmAgent  # noqa: F401

    __all__ = [
        "SmartFixLiteLlm",
        "SmartFixLlmAgent",
    ]
except ImportError:
    # During development, dependencies may not be available
    __all__ = []

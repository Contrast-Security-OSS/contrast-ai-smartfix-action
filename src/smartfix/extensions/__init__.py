"""SmartFix LLM Extensions

This package contains enhanced LLM integrations and extensions
that provide advanced functionality like prompt caching, cost tracking,
and multi-provider support.

Key Components:
- SmartFixLiteLlm: Enhanced LiteLLM with prompt caching and cost tracking
- SmartFixLlmAgent: Enhanced LLM agent with advanced capabilities
"""

# Import classes for easy access
try:
    from src.smartfix.extensions.smartfix_litellm import SmartFixLiteLlm
    from src.smartfix.extensions.smartfix_llm_agent import SmartFixLlmAgent

    __all__ = [
        "SmartFixLiteLlm",
        "SmartFixLlmAgent",
    ]
except ImportError:
    # During development, dependencies may not be available
    __all__ = []

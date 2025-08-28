# -
# #%L
# Extended LLM Agent
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# This work is a derivative of Google's ADK LlmAgent class, which is
# Copyright 2025 Google LLC and licensed under the Apache License, Version 2.0.
# Original source: https://github.com/google/adk-python
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security's commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#


from __future__ import annotations

from typing import Optional, Any
from typing_extensions import override
from pydantic import Field, model_validator

from google.adk.agents import LlmAgent
from src.utils import debug_log

# Import ExtendedLiteLlm at module level so it's available for model_rebuild()
ExtendedLiteLlm = None
try:
    from .extended_litellm import ExtendedLiteLlm
except ImportError:
    pass


class ExtendedLlmAgent(LlmAgent):
    """Extended LLM Agent that preserves ExtendedLiteLlm statistics across calls.

    This class solves the issue where ExtendedLiteLlm accumulated statistics
    aren't preserved when using the model within a Google ADK Agent. It ensures
    that the same ExtendedLiteLlm instance is used for all LLM calls and provides
    convenient methods to access accumulated statistics.

    Example usage:
    ```python
    from src.extensions.extended_litellm import ExtendedLiteLlm
    from src.extensions.extended_llm_agent import ExtendedLlmAgent

    # Create the extended model
    model = ExtendedLiteLlm(model="bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0")

    # Create the extended agent
    agent = ExtendedLlmAgent(
        name="my-agent",
        model=model,
        instruction="You are a helpful assistant."
    )

    # Run agent tasks...
    result = await agent.run(...)


    # Get statistics as JSON string for programmatic use
    stats_json = agent.gather_accumulated_stats()

    # Reset statistics
    agent.reset_accumulated_stats()
    ```
    """

    original_extended_model: Optional[Any] = Field(
        default=None,
        exclude=True,
        description="Reference to the original ExtendedLiteLlm instance for stats access"
    )

    @model_validator(mode='after')
    def _preserve_extended_model_reference(self):
        """Preserve a reference to the ExtendedLiteLlm instance if provided."""
        # Import here to avoid circular imports
        try:
            from .extended_litellm import ExtendedLiteLlm

            if isinstance(self.model, ExtendedLiteLlm):
                # Store reference to the original instance
                self.original_extended_model = self.model
                debug_log(f"[EXTENDED_AGENT] Preserved reference to ExtendedLiteLlm instance for agent: {self.name}")

        except ImportError:
            # ExtendedLiteLlm not available, ignore
            pass

        return self

    @override
    @property
    def canonical_model(self):
        """Override to ensure we return the original ExtendedLiteLlm instance."""
        # If we have a preserved ExtendedLiteLlm instance, return it
        if self.original_extended_model is not None:
            return self.original_extended_model

        # Otherwise, use the parent's canonical_model
        return super().canonical_model

    def has_extended_model(self) -> bool:
        """Check if this agent is using an ExtendedLiteLlm model."""
        try:
            from .extended_litellm import ExtendedLiteLlm
            return isinstance(self.canonical_model, ExtendedLiteLlm)
        except ImportError:
            return False

    def get_extended_model(self) -> Optional[Any]:
        """Get the ExtendedLiteLlm instance if available."""
        if self.has_extended_model():
            return self.canonical_model
        return None

    def gather_accumulated_stats_dict(self) -> dict:
        """Get accumulated token usage and cost statistics as dictionary.

        This method provides programmatic access to the accumulated statistics
        from the ExtendedLiteLlm instance being used by this agent.

        Returns:
            dict: Dictionary containing accumulated statistics

        Raises:
            ValueError: If the agent is not using an ExtendedLiteLlm model.
        """
        extended_model = self.get_extended_model()
        if extended_model is None:
            raise ValueError(
                f"Agent '{self.name}' is not using an ExtendedLiteLlm model. "
                "Cannot access accumulated statistics. "
                f"Current model type: {type(self.canonical_model).__name__}"
            )

        return extended_model.gather_accumulated_stats_dict()

    def gather_accumulated_stats(self) -> str:
        """Get accumulated token usage and cost statistics as JSON string.

        This method provides programmatic access to the accumulated statistics
        from the ExtendedLiteLlm instance being used by this agent.

        Returns:
            str: JSON formatted string containing accumulated statistics

        Raises:
            ValueError: If the agent is not using an ExtendedLiteLlm model.
        """
        extended_model = self.get_extended_model()
        if extended_model is None:
            raise ValueError(
                f"Agent '{self.name}' is not using an ExtendedLiteLlm model. "
                "Cannot access accumulated statistics. "
                f"Current model type: {type(self.canonical_model).__name__}"
            )

        return extended_model.gather_accumulated_stats()

    def reset_accumulated_stats(self) -> None:
        """Reset accumulated statistics to start fresh.

        Raises:
            ValueError: If the agent is not using an ExtendedLiteLlm model.
        """
        extended_model = self.get_extended_model()
        if extended_model is None:
            raise ValueError(
                f"Agent '{self.name}' is not using an ExtendedLiteLlm model. "
                "Cannot reset accumulated statistics. "
                f"Current model type: {type(self.canonical_model).__name__}"
            )

        debug_log(f"Resetting accumulated statistics for agent: {self.name}")
        extended_model.reset_accumulated_stats()

    def get_accumulated_stats_summary(self) -> dict:
        """Get accumulated statistics as a dictionary for programmatic access.

        Returns:
            dict: Dictionary containing accumulated statistics including:
                - call_count: Number of LLM calls made
                - total_tokens: Total tokens across all types
                - total_cost: Total cost in dollars
                - cache_savings: Total cache savings in dollars
                - cache_savings_percentage: Cache savings as percentage
                - And more detailed breakdowns

        Raises:
            ValueError: If the agent is not using an ExtendedLiteLlm model.
        """
        extended_model = self.get_extended_model()
        if extended_model is None:
            raise ValueError(
                f"Agent '{self.name}' is not using an ExtendedLiteLlm model. "
                "Cannot access accumulated statistics. "
                f"Current model type: {type(self.canonical_model).__name__}"
            )

        acc = extended_model.cost_accumulator

        return {
            'agent_name': self.name,
            'call_count': acc.call_count,
            'total_tokens': acc.total_tokens,
            'total_new_input_tokens': acc.total_new_input_tokens,
            'total_output_tokens': acc.total_output_tokens,
            'total_cache_read_tokens': acc.total_cache_read_tokens,
            'total_cache_write_tokens': acc.total_cache_write_tokens,
            'total_cost': acc.total_cost,
            'total_input_cost': acc.total_input_cost,
            'total_output_cost': acc.total_output_cost,
            'total_new_input_cost': acc.total_new_input_cost,
            'total_cache_read_cost': acc.total_cache_read_cost,
            'total_cache_write_cost': acc.total_cache_write_cost,
            'cache_savings': acc.cache_savings,
            'cache_savings_percentage': acc.cache_savings_percentage,
            'average_cost_per_call': acc.total_cost / acc.call_count if acc.call_count > 0 else 0,
            'average_tokens_per_call': acc.total_tokens / acc.call_count if acc.call_count > 0 else 0,
        }

    def get_model_info(self) -> dict:
        """Get information about the model being used by this agent.

        Returns:
            dict: Dictionary containing model information including:
                - model_name: The model name/identifier
                - model_type: The class name of the model
                - is_extended: Whether it's an ExtendedLiteLlm instance
                - has_stats: Whether accumulated statistics are available
        """
        model = self.canonical_model

        return {
            'agent_name': self.name,
            'model_name': model.model if hasattr(model, 'model') else str(model),
            'model_type': type(model).__name__,
            'is_extended': self.has_extended_model(),
            'has_stats': self.has_extended_model(),
            'model_id': id(model),  # Python object ID for debugging
        }


# Rebuild the model schema after ExtendedLiteLlm is available
# This resolves forward references and ensures Pydantic can fully validate the model
if ExtendedLiteLlm is not None:
    try:
        ExtendedLlmAgent.model_rebuild()
    except Exception:
        # If rebuild fails for any reason, just continue
        # The class will still work, just without perfect type validation
        pass

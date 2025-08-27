# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from typing_extensions import override
from pydantic import Field, model_validator

from google.adk.agents import LlmAgent

if TYPE_CHECKING:
    from .extended_litellm import ExtendedLiteLlm


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

    # Access accumulated statistics
    agent.print_accumulated_stats()
    agent.reset_accumulated_stats()
    ```
    """

    original_extended_model: Optional['ExtendedLiteLlm'] = Field(
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
                print(f"[EXTENDED_AGENT] Preserved reference to ExtendedLiteLlm instance for agent: {self.name}")

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

    def get_extended_model(self) -> Optional['ExtendedLiteLlm']:
        """Get the ExtendedLiteLlm instance if available."""
        if self.has_extended_model():
            return self.canonical_model
        return None

    def print_accumulated_stats(self) -> None:
        """Print accumulated token usage and cost statistics.

        This method provides access to the accumulated statistics from the
        ExtendedLiteLlm instance being used by this agent.

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

        print(f"\n=== STATISTICS FOR AGENT: {self.name} ===")
        extended_model.print_accumulated_stats()

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

        print(f"Resetting accumulated statistics for agent: {self.name}")
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

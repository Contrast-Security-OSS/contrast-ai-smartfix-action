# -
# #%L
# Extended LiteLLM with Prompt Caching
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# This work is a derivative of Google's ADK LiteLlm class, which is
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

from typing import Dict, List, Optional, Tuple
from google.adk.models.lite_llm import LiteLlm, _get_completion_inputs
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from litellm import Message


class ExtendedLiteLlm(LiteLlm):
    """Extended LiteLlm with automatic prompt caching for Anthropic models.

    This class extends the base LiteLlm to automatically apply prompt caching
    to Anthropic models (both direct and via Bedrock). Other models work normally.

    Example usage:
    ```python
    # Anthropic - will apply cache_control automatically
    model = ExtendedLiteLlm(model="anthropic/claude-3-5-sonnet-20241022")

    # Bedrock Anthropic - will apply cache_control automatically
    model = ExtendedLiteLlm(model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0")

    # OpenAI - works with automatic caching (no changes needed)
    model = ExtendedLiteLlm(model="openai/gpt-4o")

    # Other models - work normally without caching
    model = ExtendedLiteLlm(model="gemini/gemini-1.5-pro")
    ```
    """

    def _apply_anthropic_cache_control(self, messages: List[Message]) -> None:
        """Applies cache control to messages for Anthropic models.

        For Anthropic models, we mark the last user message and system instruction
        with cache_control to enable prompt caching.

        Args:
            messages: The list of messages to apply cache control to.
        """
        if not messages:
            return

        # Find the last user message and apply cache control
        for i in range(len(messages) - 1, -1, -1):
            message = messages[i]
            if hasattr(message, 'role') and message.role == 'user':
                # Add cache_control to the message
                if hasattr(message, '__dict__'):
                    message.__dict__['cache_control'] = {"type": "ephemeral"}
                break

        # Apply cache control to system instruction (first message if developer role)
        if messages and hasattr(messages[0], 'role') and messages[0].role == 'developer':
            if hasattr(messages[0], '__dict__'):
                messages[0].__dict__['cache_control'] = {"type": "ephemeral"}

    def _get_completion_inputs(
        self,
        llm_request: LlmRequest
    ) -> Tuple[
        List[Message],
        Optional[List[Dict]],
        Optional[types.SchemaUnion],
        Optional[Dict],
    ]:
        """Override to add prompt caching for Anthropic models."""
        # Get standard inputs from parent class
        messages, tools, response_format, generation_params = _get_completion_inputs(llm_request)

        # Apply caching for Anthropic models (direct or via Bedrock)
        model_lower = self.model.lower()
        if ("anthropic/" in model_lower
                or "claude" in model_lower
                or ("bedrock/" in model_lower and "claude" in model_lower)):
            self._apply_anthropic_cache_control(messages)

        return messages, tools, response_format, generation_params

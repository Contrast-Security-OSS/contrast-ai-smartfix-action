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
import litellm
import logging

# Enable LiteLLM debug logging
litellm._turn_on_debug()

logger = logging.getLogger(__name__)


class ExtendedLiteLlm(LiteLlm):
    """Extended LiteLlm with automatic prompt caching for Anthropic models.

    This class extends the base LiteLlm to automatically apply prompt caching
    using the appropriate method for each provider:
    - Direct Anthropic API: Uses cache_control on messages
    - Bedrock Claude models: Uses cachePoint objects in content arrays

    Example usage:
    ```python
    # Anthropic Direct API - will apply cache_control automatically
    model = ExtendedLiteLlm(model="anthropic/claude-3-5-sonnet-20241022")

    # Bedrock Claude - will apply cachePoint automatically
    model = ExtendedLiteLlm(model="bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0")

    # OpenAI - works with automatic caching (no changes needed)
    model = ExtendedLiteLlm(model="openai/gpt-4o")

    # Other models - work normally without caching
    model = ExtendedLiteLlm(model="gemini/gemini-1.5-pro")
    ```
    """

    def _apply_anthropic_cache_control(self, messages: List[Message]) -> None:
        """Applies cache control to messages for direct Anthropic API models.

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

    def _apply_bedrock_cache_points(self, messages: List[Message]) -> None:
        """Applies Bedrock-style cachePoint objects to message content arrays.

        For Bedrock models, we add cachePoint objects within the content arrays
        to create cache checkpoints.

        Args:
            messages: The list of messages to add cache points to.
        """
        if not messages:
            return

        for message in messages:
            # Add cache point after developer (system) messages
            if hasattr(message, 'role') and message.role == 'developer':
                if hasattr(message, 'content') and isinstance(message.content, str):
                    # Convert string content to array format and add cache point
                    message.content = [
                        {"text": message.content},
                        {"cachePoint": {"type": "default"}}
                    ]

            # Add cache point after first user message
            elif hasattr(message, 'role') and message.role == 'user':
                if hasattr(message, 'content'):
                    if isinstance(message.content, str):
                        message.content = [
                            {"text": message.content},
                            {"cachePoint": {"type": "default"}}
                        ]
                    elif isinstance(message.content, list):
                        # Add cache point at the end of existing content array
                        message.content.append({"cachePoint": {"type": "default"}})
                break  # Only cache first user message

    def _get_completion_inputs(
        self,
        llm_request: LlmRequest
    ) -> Tuple[
        List[Message],
        Optional[List[Dict]],
        Optional[types.SchemaUnion],
        Optional[Dict],
    ]:
        """Override to add prompt caching for Anthropic and Bedrock models."""
        logger.info(f"Processing model: {self.model}")

        # Get standard inputs from parent class
        messages, tools, response_format, generation_params = _get_completion_inputs(llm_request)

        # Apply appropriate caching based on model type
        model_lower = self.model.lower()

        logger.info(f"Model detection: bedrock={('bedrock/' in model_lower)}, claude={('claude' in model_lower)}")

        if "anthropic/" in model_lower and "bedrock/" not in model_lower:
            # Direct Anthropic API - use cache_control
            logger.info("Applying Anthropic cache_control")
            self._apply_anthropic_cache_control(messages)
        elif "bedrock/" in model_lower and "claude" in model_lower:
            # Bedrock Claude models - use cachePoint
            logger.info("Applying Bedrock cachePoint")
            self._apply_bedrock_cache_points(messages)
        else:
            logger.info("No caching applied - model not supported")

        # Log the final messages structure (truncated)
        logger.info(f"Final message count: {len(messages)}")
        for i, msg in enumerate(messages):
            if hasattr(msg, 'role'):
                content_type = type(getattr(msg, 'content', None)).__name__
                logger.info(f"Message {i}: role={msg.role}, content_type={content_type}")

        return messages, tools, response_format, generation_params

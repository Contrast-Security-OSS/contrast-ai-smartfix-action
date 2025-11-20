# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
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

"""
Sub-Agent Executor Module

Handles low-level sub-agent creation, execution, and event processing for Fix and QA agents.
These sub-agents operate under the SmartFixAgent orchestrator.
"""

import asyncio
import datetime
import re
from pathlib import Path
from typing import Optional

from src.config import get_config
from src.utils import debug_log, log, error_exit, tail_string
from src.smartfix.shared.failure_categories import FailureCategory
import src.telemetry_handler as telemetry_handler
from src.smartfix.domains.providers import setup_contrast_provider, CONTRAST_CLAUDE_SONNET_4_5

from .mcp_manager import MCPToolsetManager

# --- ADK Setup (Conditional Import) ---
ADK_AVAILABLE = False

try:
    from google.adk.agents import Agent
    from src.smartfix.extensions.smartfix_litellm import SmartFixLiteLlm
    from src.smartfix.extensions.smartfix_llm_agent import SmartFixLlmAgent
    from google.genai import types as genai_types
    ADK_AVAILABLE = True
except ImportError:
    pass


class SubAgentExecutor:
    """
    Handles low-level sub-agent creation and execution.

    Encapsulates ADK agent lifecycle, event processing, and telemetry collection
    for Fix and QA agents operating under the SmartFixAgent orchestrator.
    """

    def __init__(self, max_events: int = None):
        """
        Initialize sub-agent executor with configuration.

        Args:
            max_events: Maximum events per agent execution (defaults to config value)
        """
        self.config = get_config()
        self.max_events = max_events or self.config.MAX_EVENTS_PER_AGENT
        self.mcp_manager = MCPToolsetManager()

    async def create_agent(
        self,
        target_folder: Path,
        remediation_id: str,
        session_id: str,
        agent_type: str = "fix",
        system_prompt: Optional[str] = None
    ) -> Optional[Agent]:
        """
        Create an ADK Agent (either 'fix' or 'qa').

        Args:
            target_folder: Path to the folder for filesystem access
            remediation_id: Remediation ID for error tracking
            session_id: Session ID for Contrast LLM tracking
            agent_type: Type of agent ("fix" or "qa")
            system_prompt: System prompt for agent instructions

        Returns:
            Agent: Configured ADK agent instance

        Raises:
            SystemExit: On agent creation failure
        """
        # Get MCP tools using the manager
        mcp_tools = await self.mcp_manager.get_tools(target_folder, remediation_id)
        if not mcp_tools:
            log(f"Error: No MCP tools available for the {agent_type} agent. Cannot proceed.", is_error=True)
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        # Validate system prompt
        if not system_prompt:
            log(f"Error: No system prompt available for {agent_type} agent")
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        agent_instruction = system_prompt
        agent_name = f"contrast_{agent_type}_agent"
        debug_log(f"Using API-provided system prompt for {agent_type} agent")

        # Create the agent
        try:
            # Check if we should use Contrast LLM with custom headers
            if hasattr(self.config, 'USE_CONTRAST_LLM') and self.config.USE_CONTRAST_LLM:
                setup_contrast_provider()
                model_instance = SmartFixLiteLlm(
                    model=CONTRAST_CLAUDE_SONNET_4_5,
                    temperature=0.2,
                    stream_options={"include_usage": True},
                    system=system_prompt,  # Use standard system parameter
                    extra_headers={
                        "Api-Key": f"{self.config.CONTRAST_API_KEY}",
                        "Authorization": f"{self.config.CONTRAST_AUTHORIZATION_KEY}",
                        "x-contrast-llm-session-id": f"{session_id}"
                    }
                )
                debug_log(f"Creating {agent_type} agent ({agent_name}) with model contrast_llm")
            else:
                model_instance = SmartFixLiteLlm(
                    model=self.config.AGENT_MODEL,
                    temperature=0.2,  # Set low temperature for more deterministic output
                    # seed=42, # The random seed for reproducibility
                    # (not supported by bedrock/anthropic atm - call throws error)
                    stream_options={"include_usage": True}
                )
                debug_log(f"Creating {agent_type} agent ({agent_name}) with model {self.config.AGENT_MODEL}")

            root_agent = SmartFixLlmAgent(
                model=model_instance,
                name=agent_name,
                instruction=agent_instruction,
                tools=[mcp_tools],
            )
            debug_log(f"Created {agent_type} agent ({agent_name})")
            return root_agent
        except Exception as e:
            log(f"Error creating ADK {agent_type} Agent: {e}", is_error=True)
            if "bedrock" in str(e).lower() or "aws" in str(e).lower():
                log("Hint: Ensure AWS credentials and Bedrock model ID are correct.", is_error=True)
            error_exit(remediation_id, FailureCategory.INVALID_LLM_CONFIG.value)

    async def execute_agent(
        self,
        runner,
        agent,
        session,
        user_query: str,
        remediation_id: str,
        agent_type: str = "fix"
    ) -> str:
        """
        Execute the agent with the given query and return the final response.

        Processes agent events, handles tool calls, collects telemetry, and
        manages event limits.

        Args:
            runner: ADK Runner instance
            agent: ADK Agent instance
            session: ADK Session instance
            user_query: User query/prompt for the agent
            remediation_id: Remediation ID for error tracking
            agent_type: Type of agent ("fix" or "qa")

        Returns:
            str: Final response from the agent
        """
        agent_event_actions = []
        start_time = datetime.datetime.now()

        # Validate prerequisites
        session_id, user_id = await self._validate_prerequisites(remediation_id, runner, session, agent_type)

        log(f"Running AI {agent_type.upper()} agent to analyze vulnerability and apply fix...")

        # Initialize tracking variables
        event_count = 0
        final_response = "AI agent did not provide a final summary."

        # Create the async event stream
        events_async = await self._create_event_stream(runner, session_id, user_id, user_query, remediation_id)

        agent_run_result = "ERROR"
        # Initialize with a properly structured object
        agent_event_telemetry = {
            "llmAction": {
                "summary": "Starting agent execution"
            },
            "toolCalls": []
        }
        agent_tool_calls_telemetry = []

        try:
            async for event in events_async:
                event_count += 1

                # Process the event and get updated state
                event_response, should_break = await self._process_event(
                    event, event_count, agent_type, agent_tool_calls_telemetry
                )

                if event_response:
                    final_response = event_response

                # Handle agent messages and telemetry
                if event.content and event_response and event_response != final_response:
                    if agent_event_telemetry is not None:
                        # Directly assign toolCalls rather than appending
                        agent_event_telemetry["toolCalls"] = agent_tool_calls_telemetry
                        agent_event_actions.append(agent_event_telemetry)
                        agent_event_telemetry = {
                            "llmAction": {
                                "summary": event_response
                            },
                            "toolCalls": []
                        }
                        agent_tool_calls_telemetry = []

                # Check if we should break due to event limit
                if should_break:
                    # First clean up the event stream gracefully
                    try:
                        await self._cleanup_event_stream(events_async)
                    except Exception:
                        pass  # Ignore any cleanup errors

                    # Set result and let the function complete normally instead of throwing exception
                    agent_run_result = "EXCEEDED_EVENTS"
                    break  # Exit the event loop

            agent_run_result = "SUCCESS"
        except Exception as e:
            # Handle the exception and determine if execution should continue
            should_continue = await self._handle_exception(e, events_async, remediation_id)
            if not should_continue:
                return final_response
        finally:
            # Ensure we clean up the event stream
            await self._cleanup_event_stream(events_async)

            debug_log(f"Closing MCP server connections for {agent_type.upper()} agent...")
            log(f"{agent_type.upper()} agent run finished.")

            # Get accumulated statistics for telemetry
            total_tokens, total_cost = self._collect_statistics(agent)

            # Directly assign toolCalls rather than appending, to avoid nested arrays
            agent_event_telemetry["toolCalls"] = agent_tool_calls_telemetry
            agent_event_actions.append(agent_event_telemetry)
            duration_ms = (datetime.datetime.now() - start_time).total_seconds() * 1000
            agent_event_payload = {
                "startTime": start_time.isoformat() + "Z",
                "durationMs": duration_ms,
                "agentType": agent_type.upper(),
                "result": agent_run_result,
                "actions": agent_event_actions,
                "totalTokens": total_tokens,
                "totalCost": total_cost
            }
            telemetry_handler.add_agent_event(agent_event_payload)

        return final_response

    async def _validate_prerequisites(self, remediation_id: str, runner, session, agent_type: str) -> tuple:
        """Validate that all prerequisites for agent execution are met."""
        if not ADK_AVAILABLE or not runner or not session:
            log("AI Agent execution skipped: ADK libraries not available or runner/session invalid.")
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        if not hasattr(genai_types, 'Content') or not hasattr(genai_types, 'Part'):
            log("AI Agent execution skipped: google.genai types Content/Part not available.")
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        session_id = getattr(session, 'id', None)
        user_id = getattr(session, 'user_id', None)
        if not session_id or not user_id:
            log("AI Agent execution skipped: Session object is invalid or missing required attributes (id, user_id).")
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        return session_id, user_id

    async def _create_event_stream(self, runner, session_id: str, user_id: str, user_query: str, remediation_id: str):
        """Create the async event stream for agent execution."""
        content = genai_types.Content(role='user', parts=[genai_types.Part(text=user_query)])

        try:
            events_async = runner.run_async(
                session_id=session_id,
                user_id=user_id,
                new_message=content
            )
            return events_async
        except Exception as e:
            log(f"Failed to create agent event stream: {e}", is_error=True)
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    async def _process_event(self, event, event_count: int, agent_type: str, agent_tool_calls_telemetry: list) -> tuple:
        """Process a single agent event and return updated state."""
        debug_log(f"\n\nAGENT EVENT #{event_count} ({agent_type.upper()}):")

        # Check if we've exceeded the event limit
        if event_count > self.max_events:
            log(
                f"\n⚠️ Reached maximum event limit of {self.max_events} for {agent_type.upper()} agent. "
                f"Stopping agent execution early."
            )
            final_response = (
                f"\n\n⚠️ Note: Agent execution was terminated early after reaching the maximum limit "
                f"of {self.max_events} events. The solution may be incomplete."
            )
            return final_response, True

        # Process agent content/message
        final_response = None
        content_response = self._process_content(event, agent_type)
        if content_response:
            final_response = content_response

        # Process function calls and responses
        self._process_function_calls(event, agent_type, agent_tool_calls_telemetry)
        self._process_function_responses(event, agent_type, agent_tool_calls_telemetry)

        return final_response, False

    def _process_content(self, event, agent_type: str) -> Optional[str]:
        """Process agent content/message from event."""
        if not event.content:
            return None

        message_text = ""
        if hasattr(event.content, "text"):
            message_text = event.content.text or ""
        elif hasattr(event.content, "parts") and event.content.parts and hasattr(event.content.parts[0], "text"):
            message_text = event.content.parts[0].text or ""

        if message_text:
            log(f"\n*** {agent_type.upper()} Agent Message: \033[1;36m {message_text} \033[0m")
            return message_text

        return None

    def _process_function_calls(self, event, agent_type: str, agent_tool_calls_telemetry: list):
        """Process function calls from event."""
        calls = event.get_function_calls()
        if calls:
            for call in calls:
                args_str = str(call.args)
                log(f"\n::group::  {agent_type.upper()} Agent calling tool {call.name}...")
                log(f"  Tool Call: {call.name}, Args: {args_str}")
                log("\n::endgroup::")
                agent_tool_calls_telemetry.append({
                    "tool": call.name,
                    "result": "CALLING",
                })

    def _process_function_responses(self, event, agent_type: str, agent_tool_calls_telemetry: list):
        """Process function responses from event."""
        responses = event.get_function_responses()
        if responses:
            for response in responses:
                result_str = str(response.response)
                log(f"\n::group::  Response from tool {response.name} for {agent_type.upper()} Agent...")
                log(f"  Tool Result: {response.name} -> {result_str}")
                log("\n::endgroup::")

                tool_call_status = "UNKNOWN"
                # First try regex to find isError=True or isError=False pattern
                is_error_match = re.search(r'isError\s*=\s*(True|False)', result_str)
                if is_error_match:
                    is_error_value = is_error_match.group(1)
                    if is_error_value == "False":
                        tool_call_status = "SUCCESS"
                    else:
                        tool_call_status = "FAILURE"

                agent_tool_calls_telemetry.append({
                    "tool": response.name,
                    "result": tool_call_status,
                })

    async def _cleanup_event_stream(self, events_async, timeout=5.0):
        """
        Safely clean up an async event stream.

        Handles timeout and asyncio/anyio errors gracefully without logging warnings.

        Args:
            events_async: The async event stream to close
            timeout: Timeout in seconds for the close operation
        """
        if not events_async:
            return

        # We don't log any warnings here anymore as we're now filtering these at the logger level
        # Just silently handle all exceptions that occur during cleanup
        try:
            # Wrap the aclose in a shield to prevent cancellation issues
            try:
                # Use shield to prevent this task from being cancelled by other tasks
                close_task = asyncio.shield(asyncio.create_task(events_async.aclose()))
                await asyncio.wait_for(close_task, timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError, RuntimeError, GeneratorExit):
                # Silently ignore all expected errors during cleanup
                pass
        except Exception:
            # Catch-all for any other exceptions - just suppress them
            pass

    async def _handle_exception(self, e: Exception, events_async, remediation_id: str) -> bool:
        """
        Handle exceptions during agent execution.

        Returns:
            bool: True if execution should continue, False otherwise
        """
        error_message = str(e)
        is_asyncio_error = any(pattern in error_message for pattern in [
            "cancel scope", "different task", "CancelledError",
            "GeneratorExit", "BaseExceptionGroup", "TaskGroup"
        ])

        if is_asyncio_error:
            # For asyncio-related errors, log at debug level and don't consider it a failure
            debug_log(f"Ignoring expected asyncio error during agent execution: {tail_string(error_message, 100)}...")
        else:
            # Check for Contrast LLM Access Denied error
            if (hasattr(self.config, 'USE_CONTRAST_LLM')
                    and self.config.USE_CONTRAST_LLM
                    and ("AnthropicError" in error_message or "anthropic" in error_message.lower())
                    and "Access Denied" in error_message):

                # Output cleaner error message in red text for Contrast LLM access issues
                red_text = ("\n\033[31mContrast LLM access denied. Please ensure that the "
                            "Contrast LLM Early Access feature is enabled for your "
                            "organization. Contact your Contrast representative or Customer "
                            "Success Manager to enable Early Access.\033[0m\n")
                log(red_text, is_error=True)
            else:
                # For other errors, log normally
                log(f"Error during agent execution: {error_message}", is_error=True)

        # Always attempt cleanup
        await self._cleanup_event_stream(events_async, timeout=3.0)

        # Only exit with an error for non-asyncio errors
        if not is_asyncio_error:
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        return is_asyncio_error

    def _collect_statistics(self, agent) -> tuple:
        """
        Collect telemetry statistics from agent.

        Returns:
            tuple: (total_tokens, total_cost)
        """
        try:
            stats_data = agent.gather_accumulated_stats_dict()
            debug_log(agent.gather_accumulated_stats())  # Log the JSON formatted version

            # Extract telemetry values directly from the dictionary
            total_tokens = stats_data.get("token_usage", {}).get("total_tokens", 0)
            raw_total_cost = stats_data.get("cost_analysis", {}).get("total_cost", 0.0)

            # Remove "$" prefix if present and convert to float
            if isinstance(raw_total_cost, str) and raw_total_cost.startswith("$"):
                total_cost = float(raw_total_cost[1:])
            elif isinstance(raw_total_cost, str):
                total_cost = float(raw_total_cost)
            else:
                total_cost = raw_total_cost

            return total_tokens, total_cost
        except (ValueError, KeyError, AttributeError) as e:
            # Fallback values if stats retrieval fails
            debug_log(f"Could not retrieve statistics: {e}")
            return 0, 0.0

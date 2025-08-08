#-
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security’s commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

import logging
import warnings

import asyncio
import sys
import platform

# Explicitly import Windows-specific event loop policy to ensure proper subprocess support
if platform.system() == 'Windows':
    from asyncio import WindowsProactorEventLoopPolicy
from pathlib import Path
from typing import Optional, List
import re
import traceback

# Import configurations and utilities
from src.config import get_config
from src.utils import debug_log, log, error_exit
from src.contrast_api import FailureCategory
import src.telemetry_handler as telemetry_handler
import datetime # For timestamps
import traceback # For error logging

config = get_config()

# --- ADK Setup (Conditional Import) ---
ADK_AVAILABLE = False

try:
    from google.adk.agents import Agent
    from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters, StdioConnectionParams
    from google.genai import types as genai_types
    ADK_AVAILABLE = True
    debug_log("ADK libraries loaded successfully.")
except ImportError as e:
    # No traceback import here, use the one at the top of the file
    log(f"FATAL: ADK libraries import failed. AI agent functionality will be disabled.", is_error=True)
    log(f"Specific Error: {e}", is_error=True)
    log("Traceback:", is_error=True)
    # Use telemetry_handler directly for logging traceback if utils.log is not fully available
    telemetry_handler.add_log_message(traceback.format_exc())
    print(traceback.format_exc(), file=sys.stderr)
    # Check if we're running in a test environment
    if not config.testing:  
        sys.exit(1)  # Only exit in production, not in tests

warnings.filterwarnings('ignore', category=UserWarning)
library_logger = logging.getLogger("google_adk.google.adk.tools.base_authenticated_tool")
library_logger.setLevel(logging.ERROR)

async def get_mcp_tools(target_folder: Path, remediation_id: str) -> MCPToolset:
    """Connects to MCP servers (Filesystem)"""
    debug_log("Attempting to connect to MCP servers...")
    target_folder_str = str(target_folder)

    # Filesystem MCP Server
    try:
        debug_log("Connecting to MCP Filesystem server...")
            
        fs_tools = MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command='npx',
                    args=[
                        '-y',  # Arguments for the command
                        '@modelcontextprotocol/server-filesystem@2025.7.1',
                        target_folder_str,
                    ],
                ),
                timeout=50,
            )
        )

        debug_log("Getting tools list from Filesystem MCP server...")
        # Use a longer timeout on Windows
        timeout_seconds = 30.0 if platform.system() == 'Windows' else 10.0
        debug_log(f"Using {timeout_seconds} second timeout for get_tools")
        
        # Wrap the get_tools call in wait_for to apply a timeout
        tools_list = await asyncio.wait_for(fs_tools.get_tools(), timeout=timeout_seconds)
        
        debug_log(f"Connected to Filesystem MCP server, got {len(tools_list)} tools")
        for tool in tools_list:
            if hasattr(tool, 'name'):
                debug_log(f"  - Filesystem Tool: {tool.name}")
            else:
                debug_log(f"  - Filesystem Tool: (Name attribute missing)")
            
    except NameError as ne:
        log(f"FATAL: Error initializing MCP Filesystem server (likely ADK setup issue): {ne}", is_error=True)
        log("No filesystem tools available - cannot make code changes.", is_error=True)
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
    except Exception as e:
        log(f"FATAL: Failed to connect to Filesystem MCP server: {str(e)}", is_error=True)
        # Get better error information when possible
        if hasattr(e, '__traceback__'):
            log(f"Error details: {traceback.format_exc()}", is_error=True)
        log("No filesystem tools available - cannot make code changes.", is_error=True)
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    debug_log(f"Total tools from all MCP servers: {len(tools_list)}")
    return fs_tools

async def create_agent(target_folder: Path, remediation_id: str, agent_type: str = "fix", system_prompt: Optional[str] = None) -> Optional[Agent]:
    """Creates an ADK Agent (either 'fix' or 'qa')."""
    mcp_tools = await get_mcp_tools(target_folder, remediation_id)
    if not mcp_tools:
        log(f"Error: No MCP tools available for the {agent_type} agent. Cannot proceed.", is_error=True)
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    if system_prompt:
        agent_instruction = system_prompt
        debug_log(f"Using API-provided system prompt for {agent_type} agent")
    else:
        log(f"Error: No system prompt available for {agent_type} agent")
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
    agent_name = f"contrast_{agent_type}_agent"

    try:
        model_instance = LiteLlm(
            model=config.AGENT_MODEL,
            temperature=0.1,  # Set low temperature for more deterministic output
            #seed=42,  # The random seed for reproducibility
            stream_options={"include_usage": True}
        )
        root_agent = Agent(
            model=model_instance,
            name=agent_name,
            instruction=agent_instruction,
            tools=[mcp_tools],
        )
        debug_log(f"Created {agent_type} agent ({agent_name}) with model {config.AGENT_MODEL}")
        return root_agent
    except Exception as e:
        log(f"Error creating ADK {agent_type} Agent: {e}", is_error=True)
        if "bedrock" in str(e).lower() or "aws" in str(e).lower():
            log("Hint: Ensure AWS credentials and Bedrock model ID are correct.", is_error=True)
        error_exit(remediation_id, FailureCategory.INVALID_LLM_CONFIG.value)

async def process_agent_run(runner, session, user_query, remediation_id: str, agent_type: str = None) -> str:
    """Runs the agent, allowing it to use tools, and returns the final text response."""
    agent_event_actions = []
    start_time = datetime.datetime.now()

    if not ADK_AVAILABLE or not runner or not session:
        log("AI Agent execution skipped: ADK libraries not available or runner/session invalid.")
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    if not hasattr(genai_types, 'Content') or not hasattr(genai_types, 'Part'):
        log("AI Agent execution skipped: google.genai types Content/Part not available.")
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    content = genai_types.Content(role='user', parts=[genai_types.Part(text=user_query)])
    log(f"Running AI {agent_type.upper()} agent to analyze vulnerability and apply fix...")
    session_id = getattr(session, 'id', None)
    user_id = getattr(session, 'user_id', None)
    if not session_id or not user_id:
        log("AI Agent execution skipped: Session object is invalid or missing required attributes (id, user_id).")
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    event_count = 0
    total_tokens = 0
    prompt_tokens = 0
    output_tokens = 0
    final_response = "AI agent did not provide a final summary."
    max_events_limit = config.MAX_EVENTS_PER_AGENT
    events_async = None

    # Create the async generator
    try:
        events_async = runner.run_async(
            session_id=session_id,
            user_id=user_id,
            new_message=content
        )
    except Exception as e:
        log(f"Failed to create agent event stream: {e}", is_error=True)
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

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
            debug_log(f"\n\nAGENT EVENT #{event_count} ({agent_type.upper()}):")
            
            # Check if we've exceeded the event limit
            if event_count > max_events_limit:
                log(f"\n⚠️ Reached maximum event limit of {max_events_limit} for {agent_type.upper()} agent. Stopping agent execution early.")
                final_response += f"\n\n⚠️ Note: Agent execution was terminated early after reaching the maximum limit of {max_events_limit} events. The solution may be incomplete."
                
                # First clean up the event stream gracefully
                try:
                    await _cleanup_event_stream(events_async)
                except Exception:
                    pass  # Ignore any cleanup errors
                    
                # Set result and let the function complete normally instead of throwing exception
                agent_run_result = "EXCEEDED_EVENTS"
                break  # Exit the event loop

            
            # Track total tokens from event usage metadata if available
            if event.usage_metadata is not None:
                debug_log(f"Event usage metadata for this message: {event.usage_metadata}")
                if hasattr(event.usage_metadata, "total_token_count"):
                    total_tokens = event.usage_metadata.total_token_count
                if hasattr(event.usage_metadata, "prompt_token_count"):
                    prompt_tokens = event.usage_metadata.prompt_token_count
                if total_tokens > 0 and prompt_tokens > 0:
                    output_tokens = total_tokens - prompt_tokens
            
            if event.content:
                message_text = ""
                if hasattr(event.content, "text"):
                    message_text = event.content.text or ""
                elif hasattr(event.content, "parts") and event.content.parts and hasattr(event.content.parts[0], "text"):
                    message_text = event.content.parts[0].text or ""

                if message_text:
                    log(f"\n*** {agent_type.upper()} Agent Message: \033[1;36m {message_text} \033[0m")
                    log(f"Tokens statistics. prompt tokens: {prompt_tokens}, output tokens {output_tokens}, total tokens: {total_tokens}")
                    final_response = message_text
                    if agent_event_telemetry is not None:
                        # Directly assign toolCalls rather than appending
                        agent_event_telemetry["toolCalls"] = agent_tool_calls_telemetry
                        agent_event_actions.append(agent_event_telemetry)
                        agent_event_telemetry = {
                            "llmAction": {
                                "summary": message_text
                            },
                            "toolCalls": []
                        }
                        agent_tool_calls_telemetry = []

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
        agent_run_result = "SUCCESS"
    except Exception as e:
        # Filter out noisy error messages related to asyncio cleanup
        error_message = str(e)
        is_asyncio_error = any(pattern in error_message for pattern in [
            "cancel scope", "different task", "CancelledError", 
            "GeneratorExit", "BaseExceptionGroup", "TaskGroup"
        ])
        
        if is_asyncio_error:
            # For asyncio-related errors, log at debug level and don't consider it a failure
            debug_log(f"Ignoring expected asyncio error during agent execution: {error_message[:100]}...")
        else:
            # For other errors, log normally
            log(f"Error during agent execution: {error_message}", is_error=True)
            
        # Always attempt cleanup
        await _cleanup_event_stream(events_async, timeout=3.0)
        
        # Only exit with an error for non-asyncio errors
        if not is_asyncio_error:
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
    finally:
        # Ensure we clean up the event stream
        await _cleanup_event_stream(events_async)
                
        debug_log(f"Closing MCP server connections for {agent_type.upper()} agent...")
        log(f"{agent_type.upper()} agent run finished.")

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
            "totalTokens": total_tokens,  # Use the tracked token count from latest event
            "totalCost": 0.0  # Placeholder still as cost calculation would need more info
        }
        telemetry_handler.add_agent_event(agent_event_payload)

    return final_response

async def _cleanup_event_stream(events_async, timeout=5.0):
    """
    Helper function to safely clean up an async event stream.
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

def _run_agent_in_event_loop(coroutine_func, *args, **kwargs):
    """
    Wrapper function to run an async coroutine in a controlled event loop.
    Handles proper setup and cleanup of the event loop and tasks.
    
    Args:
        coroutine_func: The async function to run
        *args, **kwargs: Arguments to pass to the coroutine function
        
    Returns:
        The result returned by the coroutine
    """
    result = None
    
    # Platform-specific setup
    is_windows = platform.system() == 'Windows'
    
    # On Windows, we must use the WindowsProactorEventLoopPolicy
    # The SelectorEventLoop on Windows doesn't support subprocesses, which are required for MCP
    if is_windows:
        try:
            # Close any existing loop first
            try:
                existing_loop = asyncio.get_event_loop()
                if not existing_loop.is_closed():
                    debug_log("Closing existing event loop")
                    existing_loop.close()
            except RuntimeError:
                pass  # No current loop, that's fine
                
            # Explicitly set the WindowsProactorEventLoopPolicy
            # This ensures subprocesses will work on Windows
            asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
            debug_log("Explicitly set WindowsProactorEventLoopPolicy for subprocess support")
        except Exception as e:
            debug_log(f"Warning: Error handling Windows event loop policy: {e}")
    
    # Create a new event loop for this function call
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # For diagnostic purposes, log information about the loop
    loop_policy_name = type(asyncio.get_event_loop_policy()).__name__
    loop_type_name = type(loop).__name__
    debug_log(f"Created new event loop: {loop_type_name} with policy: {loop_policy_name}")
    
    # On Windows, verify we're using the correct event loop type for subprocess support
    if is_windows:
        if 'Proactor' not in loop_type_name:
            log(f"WARNING: Current event loop {loop_type_name} is not a ProactorEventLoop, subprocesses may not work!", is_error=True)
            log(f"Current event loop policy: {loop_policy_name}", is_error=True)
    
    # More detailed logging for Windows environments
    if is_windows:
        # Check if we have a ProactorEventLoop which is required for subprocess support on Windows
        is_proactor = loop_type_name == 'ProactorEventLoop' or 'Proactor' in loop_type_name
        debug_log(f"Windows event loop is ProactorEventLoop: {is_proactor} (required for subprocess support)")
    
    try:
        # Create and run the task
        task = loop.create_task(coroutine_func(*args, **kwargs))
        result = loop.run_until_complete(task)
    except Exception as e:
        # Cancel the task if there was an error
        if 'task' in locals() and not task.done():
            task.cancel()
            # Give it a chance to complete cancellation
            try:
                loop.run_until_complete(task)
            except (asyncio.CancelledError, Exception):
                pass
        raise e  # Re-raise the exception        
    finally:
        # Clean up any remaining tasks
        pending = asyncio.all_tasks(loop)
        if pending:
            # Cancel all pending tasks
            for task in pending:
                if not task.done():
                    task.cancel()
            
            # Give tasks a chance to terminate
            try:
                # Use a timeout to avoid hanging
                wait_task = asyncio.wait(pending, timeout=2.0, return_when=asyncio.ALL_COMPLETED)
                loop.run_until_complete(wait_task)
            except (asyncio.CancelledError, Exception):
                pass
        
        # Shut down asyncgens and close the loop properly
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        
        # Close the loop
        try:
            loop.close()
        except Exception:
            pass
    
    return result

def run_ai_fix_agent(repo_root: Path, fix_system_prompt: str, fix_user_prompt: str, remediation_id: str) -> str:
    """Synchronously runs the AI agent to analyze and apply a fix using API-provided prompts."""

    # Process the fix user prompt to handle placeholders and optional SecurityTest removal
    processed_user_prompt = process_fix_user_prompt(fix_user_prompt)
    
    # Use the API-provided prompts instead of hardcoded template
    debug_log("Using API-provided fix prompts")
    debug_log(f"Fix System Prompt Length: {len(fix_system_prompt)} chars")
    debug_log(f"Fix User Prompt Length: {len(processed_user_prompt)} chars")

    log("\n--- Preparing to run AI Agent to Apply Fix ---")
    debug_log(f"Repo Root for Agent Tools: {repo_root}")
    debug_log(f"Skip Writing Security Test: {config.SKIP_WRITING_SECURITY_TEST}")

    try:
        # Use the wrapper function to run the agent in a controlled event loop
        agent_summary_str = _run_agent_in_event_loop(
            _run_agent_internal_with_prompts,
            'fix', 
            repo_root, 
            processed_user_prompt, 
            fix_system_prompt, 
            remediation_id
        )
        
        log("--- AI Agent Fix Attempt Completed ---")
        debug_log("\n--- Full Agent Summary ---")
        debug_log(agent_summary_str)
        debug_log("--------------------------")
        
        # Check if the agent was unable to use filesystem tools
        if "No MCP tools available" in agent_summary_str or "Proceeding without filesystem tools" in agent_summary_str:
            log(f"Error during AI fix agent execution: No filesystem tools were available. The agent cannot make changes to files.")
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

        # Attempt to extract analytics data for telemetry
        analytics_match = re.search(r"<analytics>(.*?)</analytics>", agent_summary_str, re.DOTALL)
        if analytics_match:
            analytics_content = analytics_match.group(1).strip() # Get content within <analytics> tags
            debug_log(f"Analytics content found:\\n{analytics_content}")

            # Extract Confidence_Score
            confidence_score_line_match = re.search(r"Confidence_Score:\s*(.*)", analytics_content)
            if confidence_score_line_match:
                confidence_str = confidence_score_line_match.group(1).strip()
                if confidence_str: # Update telemetry if a non-empty string was found
                    telemetry_handler.update_telemetry("resultInfo.confidence", confidence_str)
            else:
                debug_log("Confidence_Score not found in analytics or is empty.")

            # Extract Programming_Language
            prog_lang_match = re.search(r"Programming_Language:\s*(.*)", analytics_content)
            if prog_lang_match:
                programming_language_str = prog_lang_match.group(1).strip()
                if programming_language_str:
                    telemetry_handler.update_telemetry("appInfo.programmingLanguage", programming_language_str)
            else:
                debug_log("Programming_Language not found in analytics.")

            # Extract Technical_Stack
            tech_stack_match = re.search(r"Technical_Stack:\s*(.*)", analytics_content)
            if tech_stack_match:
                technical_stack_str = tech_stack_match.group(1).strip()
                if technical_stack_str:
                    telemetry_handler.update_telemetry("appInfo.technicalStackInfo", technical_stack_str)
            else:
                debug_log("Technical_Stack not found in analytics.")

            # Extract Frameworks
            frameworks_match = re.search(r"Frameworks:\s*(.*)", analytics_content)
            if frameworks_match:
                frameworks_raw_str = frameworks_match.group(1).strip()
                if frameworks_raw_str: # Ensure it's not an empty string
                    # Split by comma, strip whitespace from each item, and filter out any empty strings
                    frameworks_list = [fw.strip() for fw in frameworks_raw_str.split(',') if fw.strip()]
                    if frameworks_list: # Check if the list is not empty after processing
                        telemetry_handler.update_telemetry("appInfo.frameworksAndLibraries", frameworks_list)
            else:
                debug_log("Frameworks not found in analytics.")
        else:
            debug_log("Warning: <analytics> tags not found in agent response.")

        # Attempt to extract content from <pr_body> tags
        pr_body_match = re.search(r"<pr_body>(.*?)</pr_body>", agent_summary_str, re.DOTALL)
        if pr_body_match:
            extracted_pr_body = pr_body_match.group(1).strip()
            debug_log("\n--- Extracted PR Body ---")
            debug_log(extracted_pr_body)
            debug_log("-------------------------")
            return extracted_pr_body
        else:
            debug_log("Warning: <pr_body> tags not found in agent response. Using full summary for PR body.")
            return agent_summary_str # Return the full summary if tags are not found
            
    except Exception as e:
        log(f"Error running AI fix agent: {e}", is_error=True)
        failure_code = FailureCategory.AGENT_FAILURE.value
        if "litellm." in str(e).lower():
            failure_code = FailureCategory.INVALID_LLM_CONFIG.value
        # Cleanup any changes made and revert to base branch (no branch name yet)
        error_exit(remediation_id, failure_code)

def run_qa_agent(build_output: str, changed_files: List[str], build_command: str, repo_root: Path, remediation_id: str, qa_history: Optional[List[str]] = None, qa_system_prompt: Optional[str] = None, qa_user_prompt: Optional[str] = None) -> str:
    """
    Synchronously runs the QA AI agent to fix build/test errors using API-provided prompts.

    Args:
        build_output: The output from the build command.
        changed_files: A list of files that were changed by the fix agent.
        build_command: The build command that was run.
        repo_root: The root directory of the repository.
        formatting_command: The formatting command to use if a formatting error is detected.
        qa_history: List of summaries from previous QA attempts.
        qa_system_prompt: The QA system prompt from API (optional, uses template if not provided).
        qa_user_prompt: The QA user prompt from API (optional, uses template if not provided).

    Returns:
        A tuple containing:
        - str: The summary message from the agent.
        - Optional[str]: The command requested by the agent to be run, if any.
    """
    log("\n--- Preparing to run QA Agent to Fix Build/Test Errors ---")
    debug_log(f"Repo Root for QA Agent Tools: {repo_root}")
    debug_log(f"Build Command Used: {build_command}")
    debug_log(f"Files Changed by Fix Agent: {changed_files}")
    debug_log(f"Build Output Provided (truncated):\n---\n{build_output[-1000:]}...\n---")
    
    # Format QA history if available
    qa_history_section = ""
    if qa_history and len(qa_history) > 0:
        qa_history_section = "\nQA History from previous attempts:\n"
        for i, summary in enumerate(qa_history):
            qa_history_section += f"Attempt {i+1}: {summary}\n"
        debug_log(f"Including QA History with {len(qa_history)} previous attempts")

    # Use API-provided prompts if available, otherwise fall back to template-based approach
    if qa_system_prompt and qa_user_prompt:
        debug_log("Using API-provided QA prompts")
        # Process the QA user prompt to replace placeholders
        qa_query = process_qa_user_prompt(qa_user_prompt, changed_files, build_output, qa_history_section)
    else:
        log(f"Error: No prompts available for QA agent")
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    qa_summary = f"Error during QA agent execution: Unknown error" # Default error

    try:
        # Use the wrapper function to run the agent in a controlled event loop
        qa_summary = _run_agent_in_event_loop(
            _run_agent_internal_with_prompts,
            'qa', 
            repo_root, 
            qa_query, 
            qa_system_prompt, 
            remediation_id
        )
        
        log("--- QA Agent Fix Attempt Completed ---")
        debug_log("\n--- Raw QA Agent Summary ---")
        debug_log(qa_summary)
        debug_log("--------------------------")

        return qa_summary

    except Exception as e:
        log(f"Error running QA agent: {e}", is_error=True)
        failure_code = FailureCategory.AGENT_FAILURE.value
        if "litellm." in str(e).lower():
            failure_code = FailureCategory.INVALID_LLM_CONFIG.value
        error_exit(remediation_id, failure_code)

def process_qa_user_prompt(qa_user_prompt: str, changed_files: List[str], build_output: str, qa_history_section: str) -> str:
    """
    Process the QA user prompt by replacing placeholders.
    
    Args:
        qa_user_prompt: The raw QA user prompt from API
        changed_files: List of files that were changed by the fix agent
        build_output: The build command output
        qa_history_section: Formatted QA history from previous attempts
        
    Returns:
        str: The processed QA user prompt with placeholders replaced
    """
    # Replace placeholders
    processed_prompt = qa_user_prompt.replace("{changed_files}", ', '.join(changed_files))
    processed_prompt = processed_prompt.replace("{build_output}", build_output)
    processed_prompt = processed_prompt.replace("{qa_history_section}", qa_history_section)
    
    return processed_prompt

def process_fix_user_prompt(fix_user_prompt: str) -> str:
    """
    Process the fix user prompt by handling SecurityTest removal.
    
    Args:
        fix_user_prompt: The raw fix user prompt from API
        vuln_uuid: The vulnerability UUID for placeholder replacement
        
    Returns:
        Processed fix user prompt
    """
    # Replace {vuln_uuid} placeholder
    processed_prompt = fix_user_prompt
    if config.SKIP_WRITING_SECURITY_TEST:
        start_str = "4. Where feasible,"
        end_str = "   - **CRITICAL: When mocking"
        replacement_text = f"""
4. Where feasible, add or update tests to verify the fix.
    - **Use the 'Original HTTP Request' provided above as a basis for creating realistic mocked input data or request parameters within your test case.** Adapt the request details (method, path, headers, body) as needed for the test framework (e.g., MockMvc in Spring).
"""

        start_index = processed_prompt.find(start_str)
        end_index = processed_prompt.find(end_str)

        if start_index == -1 or end_index == -1:
            debug_log(f"Error: SecurityTest substring not found.")
            return processed_prompt

        processed_prompt = (
            processed_prompt[:start_index] + replacement_text + processed_prompt[end_index:]
        )
    
    return processed_prompt

async def _run_agent_internal_with_prompts(agent_type: str, repo_root: Path, query: str, system_prompt: str, remediation_id: str) -> str:
    """Internal helper to run either fix or QA agent with API-provided prompts. Returns summary."""
    debug_log(f"Using Agent Model ID: {config.AGENT_MODEL}")
    
    # Set the correct event loop policy for Windows
    # This is crucial for the MCP filesystem server connections to work on Windows
    if platform.system() == 'Windows':
        try:
            # First ensure there's no active event loop that might conflict
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    debug_log("Closing existing event loop before setting policy")
                    loop.close()
            except RuntimeError:
                pass  # No event loop, which is fine
            
            # IMPORTANT: On Windows, we MUST use the ProactorEventLoop
            # SelectorEventLoop doesn't support subprocesses on Windows
            # Explicitly set the WindowsProactorEventLoopPolicy to ensure subprocess support
            asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
            debug_log("Explicitly set WindowsProactorEventLoopPolicy for subprocess support")
                
            # Create a fresh event loop with the WindowsProactorEventLoopPolicy
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            debug_log(f"Created and set new event loop with Windows default policy: {type(loop).__name__}")
        except Exception as e:
            debug_log(f"Warning: Error setting Windows event loop policy: {e}")
            debug_log("Will continue with default event loop policy")

    # Configure logging to suppress asyncio and anyio errors that typically occur during cleanup
    import logging
    
    # Suppress anyio error logging
    anyio_logger = logging.getLogger("anyio")
    anyio_logger.setLevel(logging.CRITICAL)  # Using CRITICAL instead of ERROR for stricter filtering
    
    # Suppress MCP client/stdio error logging
    mcp_logger = logging.getLogger("mcp.client.stdio")
    mcp_logger.setLevel(logging.CRITICAL)
    
    # Silence the task exception was never retrieved warnings
    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.setLevel(logging.CRITICAL)
    
    # Add a comprehensive filter to specifically ignore common cancel scope and cleanup errors
    class AsyncioCleanupFilter(logging.Filter):
        def filter(self, record):
            message = record.getMessage()
            # Filter out common cleanup errors
            if any(pattern in message for pattern in [
                "exit cancel scope in a different task",
                "Task exception was never retrieved",
                "unhandled errors in a TaskGroup",
                "GeneratorExit",
                "CancelledError",
                "asyncio.exceptions",
                "BaseExceptionGroup"
            ]):
                return False
            return True
    
    # Apply the filter to multiple loggers
    cleanup_filter = AsyncioCleanupFilter()
    anyio_logger.addFilter(cleanup_filter)
    asyncio_logger.addFilter(cleanup_filter)
    if mcp_logger:
        mcp_logger.addFilter(cleanup_filter)

    if not ADK_AVAILABLE:
        log(f"FATAL: {agent_type.capitalize()} Agent execution skipped: ADK libraries not available (import failed).")
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    session = None
    runner = None
    
    try:
        session_service = InMemorySessionService()
        artifacts_service = InMemoryArtifactService()
        app_name = f'contrast_{agent_type}_app'
        session = await session_service.create_session(state={}, app_name=app_name, user_id=f'github_action_{agent_type}')
    except Exception as e:
        # Handle any errors in session creation
        log(f"FATAL: Failed to create {agent_type.capitalize()} agent session: {e}", is_error=True)
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
    
    agent = await create_agent(repo_root, remediation_id, agent_type=agent_type, system_prompt=system_prompt)
    if not agent:
        log(f"AI Agent creation failed ({agent_type} agent). Possible reasons: MCP server connection issue, missing prompts, model configuration error, or internal ADK problem.")
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    runner = Runner(
        app_name=app_name,
        agent=agent,
        artifact_service=artifacts_service,
        session_service=session_service,
    )

    # Pass the full model ID (though not used for cost calculation anymore, kept for consistency if needed elsewhere)
    summary = await process_agent_run(runner, session, query, remediation_id, agent_type)
    
    return summary

# This patch is now handled in src/asyncio_win_patch.py and called from main.py
if platform.system() == "Windows":
    _original_loop_check_closed = asyncio.BaseEventLoop._check_closed
    
    def _patched_loop_check_closed(self):
        try:
            _original_loop_check_closed(self)
        except RuntimeError as e:
             if "Event loop is closed" in str(e):
                 return #ignore this error
             raise
        asyncio.BaseEventLoop._check_closed = _patched_loop_check_closed

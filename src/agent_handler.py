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

import asyncio
import sys
from pathlib import Path
from typing import Optional, Tuple, List
from contextlib import AsyncExitStack
import re
import json

# Import configurations and utilities
import config
from utils import debug_log, log, error_exit # Updated import
from contrast_api import FailureCategory
import telemetry_handler # Import for telemetry
import datetime # For timestamps
import traceback # For error logging

# --- ADK Setup (Conditional Import) ---
ADK_AVAILABLE = False
try:
    from google.adk.agents import Agent
    from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
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
    sys.exit(1) # Exit if ADK is not available

async def get_mcp_tools(target_folder: Path, remediation_id: str) -> Tuple[List, AsyncExitStack]:
    """Connects to MCP servers (Filesystem)"""
    debug_log("Attempting to connect to MCP servers...")
    exit_stack = AsyncExitStack()
    all_tools = []
    target_folder_str = str(target_folder)

    # Filesystem MCP Server
    try:
        debug_log("Connecting to MCP Filesystem server...")
        fs_tools, fs_exit_stack = await MCPToolset(
            connection_params=StdioConnectionParameters(
                command='npx',
                args=["-y", "@modelcontextprotocol/server-filesystem@2025.1.14", target_folder_str],
            )
        )

        await exit_stack.enter_async_context(fs_exit_stack)
        all_tools.extend(fs_tools)
        debug_log(f"Connected to Filesystem MCP server, got {len(fs_tools)} tools")
        for tool in fs_tools:
            if hasattr(tool, 'name'):
                debug_log(f"  - Filesystem Tool: {tool.name}")
            else:
                debug_log(f"  - Filesystem Tool: (Name attribute missing)")
    except NameError as ne:
        log(f"FATAL: Error initializing MCP Filesystem server (likely ADK setup issue): {ne}", is_error=True)
        log("No filesystem tools available - cannot make code changes.", is_error=True)
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
    except Exception as e:
        log(f"FATAL: Failed to connect to Filesystem MCP server: {e}", is_error=True)
        log("No filesystem tools available - cannot make code changes.", is_error=True)
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    debug_log(f"Total tools from all MCP servers: {len(all_tools)}")
    return all_tools, exit_stack

async def create_agent(target_folder: Path, remediation_id: str, agent_type: str = "fix", system_prompt: Optional[str] = None) -> Tuple[Optional[Agent], AsyncExitStack]:
    """Creates an ADK Agent (either 'fix' or 'qa')."""
    mcp_tools, exit_stack = await get_mcp_tools(target_folder, remediation_id)
    if not mcp_tools:
        log(f"Error: No MCP tools available for the {agent_type} agent. Cannot proceed.", is_error=True)
        await exit_stack.aclose()
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    if system_prompt:
        agent_instruction = system_prompt
        debug_log(f"Using API-provided system prompt for {agent_type} agent")
    else:
        log(f"Error: No system prompt available for {agent_type} agent")
        await exit_stack.aclose()
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
    agent_name = f"contrast_{agent_type}_agent"

    try:
        model_instance = LiteLlm(model=config.AGENT_MODEL, stream_options={"include_usage": True})
        root_agent = Agent(
            model=model_instance,
            name=agent_name,
            instruction=agent_instruction,
            tools=mcp_tools,
        )
        debug_log(f"Created {agent_type} agent ({agent_name}) with model {config.AGENT_MODEL}")
        return root_agent, exit_stack
    except Exception as e:
        log(f"Error creating ADK {agent_type} Agent: {e}", is_error=True)
        if "bedrock" in str(e).lower() or "aws" in str(e).lower():
            log("Hint: Ensure AWS credentials and Bedrock model ID are correct.", is_error=True)
        await exit_stack.aclose()
        error_exit(remediation_id, FailureCategory.INVALID_LLM_CONFIG.value)

async def process_agent_run(runner, session, exit_stack, user_query, remediation_id: str, agent_type: str = None) -> str:
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
    final_response = "AI agent did not provide a final summary."
    max_events_limit = config.MAX_EVENTS_PER_AGENT

    # Create the async generator
    events_async = runner.run_async(
        session_id=session_id,
        user_id=user_id,
        new_message=content
    )

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
                await events_async.aclose()
                # Throw exception to fully abort processing
                error_exit(remediation_id, FailureCategory.EXCEEDED_AGENT_EVENTS.value)

            # Detailed debug logging of the event object
            debug_log(f"\n===== EVENT OBJECT ANALYSIS =====")
            debug_log(f"Event type: {type(event).__name__}")
            debug_log(f"Event dir: {dir(event)}")
            
            # Log all attributes of the event object
            for attr in dir(event):
                if not attr.startswith('_') and not callable(getattr(event, attr)):
                    try:
                        attr_value = getattr(event, attr)
                        debug_log(f"event.{attr}: {type(attr_value).__name__} = {attr_value}")
                        
                        # If it's content, dive deeper
                        if attr == "content" and attr_value:
                            debug_log(f"  content type: {type(attr_value).__name__}")
                            debug_log(f"  content dir: {dir(attr_value)}")
                            
                            # Check for text attribute
                            if hasattr(attr_value, "text"):
                                debug_log(f"  content.text: {attr_value.text}")
                            
                            # Check for parts attribute
                            if hasattr(attr_value, "parts"):
                                debug_log(f"  content.parts: {attr_value.parts}")
                                if attr_value.parts:
                                    for i, part in enumerate(attr_value.parts):
                                        debug_log(f"    part[{i}] type: {type(part).__name__}")
                                        debug_log(f"    part[{i}] dir: {dir(part)}")
                                        if hasattr(part, "text"):
                                            debug_log(f"    part[{i}].text: {part.text}")
                    except Exception as e:
                        debug_log(f"Error getting attribute {attr}: {e}")
            
            # Try to find raw inputs and outputs for token counting
            try:
                if hasattr(event, '_raw_inputs'):
                    debug_log(f"event._raw_inputs: {event._raw_inputs}")
                if hasattr(event, '_raw_outputs'):
                    debug_log(f"event._raw_outputs: {event._raw_outputs}")
                if hasattr(event, 'raw'):
                    debug_log(f"event.raw: {event.raw}")
            except Exception as e:
                debug_log(f"Error accessing raw data: {e}")
            
            debug_log(f"===== END EVENT ANALYSIS =====\n")
            
            if event.content:
                message_text = ""
                if hasattr(event.content, "text"):
                    message_text = event.content.text or ""
                elif hasattr(event.content, "parts") and event.content.parts and hasattr(event.content.parts[0], "text"):
                    message_text = event.content.parts[0].text or ""

                if message_text:
                    log(f"\n*** {agent_type.upper()} Agent Message: \033[1;36m {message_text} \033[0m")
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
    finally:
        debug_log(f"Closing MCP server connections for {agent_type.upper()} agent...")
        await exit_stack.aclose()
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
            # totalTokens and totalCost might be harder to get accurately without deeper ADK integration or assumptions
            "totalTokens": 0, # Placeholder
            "totalCost": 0.0  # Placeholder
        }
        telemetry_handler.add_agent_event(agent_event_payload)

    return final_response

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
        agent_summary_str = asyncio.run(_run_agent_internal_with_prompts('fix', repo_root, processed_user_prompt, fix_system_prompt, remediation_id))
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
            debug_log("\\n--- Extracted PR Body ---")
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
        # Run the agent internally, using API prompts if available
        qa_summary = asyncio.run(_run_agent_internal_with_prompts('qa', repo_root, qa_query, qa_system_prompt, remediation_id))
        
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

    if not ADK_AVAILABLE:
        log(f"FATAL: {agent_type.capitalize()} Agent execution skipped: ADK libraries not available (import failed).")
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    try:
        session_service = InMemorySessionService()
        artifacts_service = InMemoryArtifactService()
        app_name = f'contrast_{agent_type}_app'
        session = await session_service.create_session(state={}, app_name=app_name, user_id=f'github_action_{agent_type}')
    except Exception as e:
        # Handle any errors in session creation
        log(f"FATAL: Failed to create {agent_type.capitalize()} agent session: {e}", is_error=True)
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
    
    agent, exit_stack = await create_agent(repo_root, remediation_id, agent_type=agent_type, system_prompt=system_prompt)
    if not agent:
        await exit_stack.aclose()
        log(f"AI Agent creation failed ({agent_type} agent). Possible reasons: MCP server connection issue, missing prompts, model configuration error, or internal ADK problem.")
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    runner = Runner(
        app_name=app_name,
        agent=agent,
        artifact_service=artifacts_service,
        session_service=session_service,
    )

    # Pass the full model ID (though not used for cost calculation anymore, kept for consistency if needed elsewhere)
    summary = await process_agent_run(runner, session, exit_stack, query, remediation_id, agent_type)

    return summary

# %%

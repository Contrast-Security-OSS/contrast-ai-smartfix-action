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
import logging

# Import configurations and utilities
import config
from utils import debug_print, run_command

def cleanup_branch(branch_name=None):
    """
    Cleans up by reverting changes and deleting the feature branch if it exists.
    
    Args:
        branch_name: The name of the branch to delete. If None, no branch deletion is performed.
    """
    print(f"\n--- Cleaning up after agent error ---")
    run_command(["git", "reset", "--hard"], check=False)
    
    # If a branch name is provided, switch back to base branch and delete the feature branch
    if branch_name:
        run_command(["git", "checkout", config.BASE_BRANCH], check=False)
        run_command(["git", "branch", "-D", branch_name], check=False)
    
    print("--- Cleanup completed ---")

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
    from google.protobuf.json_format import MessageToJson
    ADK_AVAILABLE = True
    debug_print("ADK libraries loaded successfully.")
except ImportError as e:
    import traceback
    print(f"FATAL: ADK libraries import failed. AI agent functionality will be disabled.", file=sys.stderr)
    print(f"Specific Error: {e}", file=sys.stderr)
    print("Traceback:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1) # Exit if ADK is not available

async def get_mcp_tools(target_folder: Path) -> Tuple[List, AsyncExitStack]:
    """Connects to MCP servers (Filesystem)"""
    debug_print("Attempting to connect to MCP servers...")
    exit_stack = AsyncExitStack()
    all_tools = []
    target_folder_str = str(target_folder)

    # Filesystem MCP Server
    try:
        debug_print("Connecting to MCP Filesystem server...")
        fs_tools, fs_exit_stack = await MCPToolset.from_server(
            connection_params=StdioServerParameters(
                command='npx',
                args=["-y", "@modelcontextprotocol/server-filesystem@2025.1.14", target_folder_str],
            )
        )

        await exit_stack.enter_async_context(fs_exit_stack)
        all_tools.extend(fs_tools)
        debug_print(f"Connected to Filesystem MCP server, got {len(fs_tools)} tools")
        for tool in fs_tools:
            if hasattr(tool, 'name'):
                debug_print(f"  - Filesystem Tool: {tool.name}")
            else:
                debug_print(f"  - Filesystem Tool: (Name attribute missing)")
    except NameError as ne:
         print(f"FATAL: Error initializing MCP Filesystem server (likely ADK setup issue): {ne}", file=sys.stderr)
         print("No filesystem tools available - cannot make code changes.", file=sys.stderr)
         sys.exit(1)
    except Exception as e:
        print(f"FATAL: Failed to connect to Filesystem MCP server: {e}", file=sys.stderr)
        print("No filesystem tools available - cannot make code changes.", file=sys.stderr)
        sys.exit(1)

    debug_print(f"Total tools from all MCP servers: {len(all_tools)}")
    return all_tools, exit_stack

async def create_agent(target_folder: Path, agent_type: str = "fix", system_prompt: Optional[str] = None) -> Tuple[Optional[Agent], AsyncExitStack]:
    """Creates an ADK Agent (either 'fix' or 'qa')."""
    mcp_tools, exit_stack = await get_mcp_tools(target_folder)
    if not mcp_tools:
        print(f"Error: No MCP tools available for the {agent_type} agent. Cannot proceed.", file=sys.stderr)
        await exit_stack.aclose()
        sys.exit(1)

    if system_prompt:
        agent_instruction = system_prompt
        debug_print(f"Using API-provided system prompt for {agent_type} agent")
    else:
        print(f"Error: No system prompt available for {agent_type} agent")
        await exit_stack.aclose()
        sys.exit(1)
    agent_name = f"contrast_{agent_type}_agent"

    try:
        model_instance = LiteLlm(model=config.AGENT_MODEL)
        root_agent = Agent(
            model=model_instance,
            name=agent_name,
            instruction=agent_instruction,
            tools=mcp_tools,
        )
        debug_print(f"Created {agent_type} agent ({agent_name}) with model {config.AGENT_MODEL}")
        return root_agent, exit_stack
    except Exception as e:
        print(f"Error creating ADK {agent_type} Agent: {e}", file=sys.stderr)
        if "bedrock" in str(e).lower() or "aws" in str(e).lower():
            print("Hint: Ensure AWS credentials and Bedrock model ID are correct.", file=sys.stderr)
        await exit_stack.aclose()
        sys.exit(1)

async def process_agent_run(runner, session, exit_stack, user_query: str, full_model_id: str) -> str: # <<< MODIFIED return type
    """Runs the agent, allowing it to use tools, and returns the final text response."""
    if not ADK_AVAILABLE or not runner or not session:
        print("AI Agent execution skipped: ADK libraries not available or runner/session invalid.")
        sys.exit(1)

    if not hasattr(genai_types, 'Content') or not hasattr(genai_types, 'Part'):
        print("AI Agent execution skipped: google.genai types Content/Part not available.")
        sys.exit(1)

    content = genai_types.Content(role='user', parts=[genai_types.Part(text=user_query)])
    print("Running AI agent to analyze vulnerability and apply fix...", flush=True)
    session_id = getattr(session, 'id', None)
    user_id = getattr(session, 'user_id', None)
    if not session_id or not user_id:
        print("AI Agent execution skipped: Session object is invalid or missing required attributes (id, user_id).")
        sys.exit(1)

    events_async = runner.run_async(
        session_id=session_id,
        user_id=user_id,
        new_message=content
    )

    event_count = 0
    final_response = "AI agent did not provide a final summary."

    try:
        async for event in events_async:
            event_count += 1
            debug_print(f"\n\nAGENT EVENT #{event_count}:", flush=True)

            if event.content:
                message_text = ""
                if hasattr(event.content, "text"):
                    message_text = event.content.text or ""
                elif hasattr(event.content, "parts") and event.content.parts and hasattr(event.content.parts[0], "text"):
                    message_text = event.content.parts[0].text or ""

                if message_text:
                    print(f"\n*** Agent Message: \033[1;36m {message_text} \033[0m", flush=True)
                    final_response = message_text

            calls = event.get_function_calls()
            if calls:
                for call in calls:
                    args_str = str(call.args)
                    print(f"\n::group::  Calling tool {call.name}...", flush=True)
                    print(f"  Tool Call: {call.name}, Args: {args_str}", flush=True)
                    print("\n::endgroup::", flush=True)
            responses = event.get_function_responses()
            if responses:
                 for response in responses:
                    result_str = str(response.response)
                    print(f"\n::group::  Response from tool {response.name}...", flush=True)
                    print(f"  Tool Result: {response.name} -> {result_str}", flush=True)
                    print("\n::endgroup::", flush=True)

    finally:
        debug_print("Closing MCP server connections...", flush=True)
        await exit_stack.aclose()
        print("Agent run finished.", flush=True)

    # Return the final response
    return final_response

def run_ai_fix_agent(vuln_uuid: str, repo_root: Path, fix_system_prompt: str, fix_user_prompt: str) -> str:
    """Synchronously runs the AI agent to analyze and apply a fix using API-provided prompts."""

    # Process the fix user prompt to handle placeholders and optional SecurityTest removal
    processed_user_prompt = process_fix_user_prompt(fix_user_prompt, vuln_uuid)
    
    # Use the API-provided prompts instead of hardcoded template
    debug_print("Using API-provided fix prompts")
    debug_print(f"Fix System Prompt Length: {len(fix_system_prompt)} chars")
    debug_print(f"Fix User Prompt Length: {len(processed_user_prompt)} chars")

    print("\n--- Preparing to run AI Agent to Apply Fix ---")
    debug_print(f"Repo Root for Agent Tools: {repo_root}")
    debug_print(f"Skip Writing Security Test: {config.SKIP_WRITING_SECURITY_TEST}")

    try:
        agent_summary_str = asyncio.run(_run_agent_internal_with_prompts('fix', repo_root, processed_user_prompt, fix_system_prompt))
        print("--- AI Agent Fix Attempt Completed ---")
        debug_print("\n--- Full Agent Summary ---")
        debug_print(agent_summary_str)
        debug_print("--------------------------")
        
        # Check if the agent was unable to use filesystem tools
        if "No MCP tools available" in agent_summary_str or "Proceeding without filesystem tools" in agent_summary_str:
            print(f"Error during AI fix agent execution: No filesystem tools were available. The agent cannot make changes to files.")
            sys.exit(1)

        # Attempt to extract content from <pr_body> tags
        pr_body_match = re.search(r"<pr_body>(.*?)</pr_body>", agent_summary_str, re.DOTALL)
        if pr_body_match:
            extracted_pr_body = pr_body_match.group(1).strip()
            debug_print("\\n--- Extracted PR Body ---")
            debug_print(extracted_pr_body)
            debug_print("-------------------------")
            return extracted_pr_body
        else:
            debug_print("Warning: <pr_body> tags not found in agent response. Using full summary for PR body.")
            return agent_summary_str # Return the full summary if tags are not found
            
    except Exception as e:
        print(f"Error running AI fix agent: {e}", file=sys.stderr)
        # Cleanup any changes made and revert to base branch (no branch name yet)
        cleanup_branch()
        sys.exit(1)

def run_qa_agent(build_output: str, changed_files: List[str], build_command: str, repo_root: Path, formatting_command: Optional[str], qa_history: Optional[List[str]] = None, qa_system_prompt: Optional[str] = None, qa_user_prompt: Optional[str] = None) -> str:
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
    print("\n--- Preparing to run QA Agent to Fix Build/Test Errors ---")
    debug_print(f"Repo Root for QA Agent Tools: {repo_root}")
    debug_print(f"Build Command Used: {build_command}")
    debug_print(f"Files Changed by Fix Agent: {changed_files}")
    debug_print(f"Build Output Provided (truncated):\n---\n{build_output[-1000:]}...\n---")
    
    # Format QA history if available
    qa_history_section = ""
    if qa_history and len(qa_history) > 0:
        qa_history_section = "\nQA History from previous attempts:\n"
        for i, summary in enumerate(qa_history):
            qa_history_section += f"Attempt {i+1}: {summary}\n"
        debug_print(f"Including QA History with {len(qa_history)} previous attempts")

    # Use API-provided prompts if available, otherwise fall back to template-based approach
    if qa_system_prompt and qa_user_prompt:
        debug_print("Using API-provided QA prompts")
        # Process the QA user prompt to replace placeholders
        qa_query = process_qa_user_prompt(qa_user_prompt, changed_files, build_output, qa_history_section)
    else:
        print(f"Error: No prompts available for QA agent")
        sys.exit(1)

    qa_summary = f"Error during QA agent execution: Unknown error" # Default error

    try:
        # Run the agent internally, using API prompts if available
        qa_summary = asyncio.run(_run_agent_internal_with_prompts('qa', repo_root, qa_query, qa_system_prompt))
        
        print("--- QA Agent Fix Attempt Completed ---")
        debug_print("\n--- Raw QA Agent Summary ---")
        debug_print(qa_summary)
        debug_print("--------------------------")

        return qa_summary

    except Exception as e:
        print(f"Error running QA agent: {e}", file=sys.stderr)
        # Need to get the branch name from main.py context - will be handled by main.py
        # We'll just revert uncommitted changes here
        cleanup_branch()
        sys.exit(1)

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

def process_fix_user_prompt(fix_user_prompt: str, vuln_uuid: str) -> str:
    """
    Process the fix user prompt by replacing placeholders and handling SecurityTest removal.
    
    Args:
        fix_user_prompt: The raw fix user prompt from API
        vuln_uuid: The vulnerability UUID for placeholder replacement
        
    Returns:
        Processed fix user prompt
    """
    # Replace {vuln_uuid} placeholder
    processed_prompt = fix_user_prompt.replace("{vuln_uuid}", vuln_uuid)
    
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
            debug_print(f"Error: SecurityTest substring not found.")
            return

        processed_prompt = (
            processed_prompt[:start_index] + replacement_text + processed_prompt[end_index:]
        )
    
    return processed_prompt

async def _run_agent_internal_with_prompts(agent_type: str, repo_root: Path, query: str, system_prompt: str) -> str:
    """Internal helper to run either fix or QA agent with API-provided prompts. Returns summary."""
    full_model_id = config.AGENT_MODEL # Use the full ID from config
    logging.info(f"Using Agent Model ID: {full_model_id}")

    if not ADK_AVAILABLE:
        print(f"FATAL: {agent_type.capitalize()} Agent execution skipped: ADK libraries not available (import failed).")
        sys.exit(1)

    try:
        session_service = InMemorySessionService()
        artifacts_service = InMemoryArtifactService()
        app_name = f'contrast_{agent_type}_app'
        session = session_service.create_session(state={}, app_name=app_name, user_id=f'github_action_{agent_type}')
    except Exception as e:
        # Handle any errors in session creation
        print(f"FATAL: Failed to create {agent_type.capitalize()} agent session: {e}", file=sys.stderr)
        sys.exit(1)
    
    agent, exit_stack = await create_agent(repo_root, agent_type=agent_type, system_prompt=system_prompt)
    if not agent:
        await exit_stack.aclose()
        print(f"AI Agent creation failed ({agent_type} agent). Possible reasons: MCP server connection issue, missing prompts, model configuration error, or internal ADK problem.")
        sys.exit(1)

    runner = Runner(
        app_name=app_name,
        agent=agent,
        artifact_service=artifacts_service,
        session_service=session_service,
    )

    # Pass the full model ID (though not used for cost calculation anymore, kept for consistency if needed elsewhere)
    summary = await process_agent_run(runner, session, exit_stack, query, full_model_id)

    return summary

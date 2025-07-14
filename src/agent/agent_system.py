#-
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

from pathlib import Path
from typing import List, Optional
from src.agent.agent_prompts import AgentPrompts
from src.agent.agent_runner import AgentRunner
from src.utils import log, debug_log, error_exit
from src.api.contrast_api_client import FailureCategory

class AgentSystem:
    """
    Manages the AI agents for vulnerability fixing and quality assurance.
    """
    
    def __init__(self, agent_model, telemetry_handler, max_events_per_agent=120):
        """
        Initialize the agent system with required components.
        
        Args:
            agent_model: The LLM model to use for agents
            telemetry_handler: Handler for telemetry data collection
            max_events_per_agent: Maximum number of events per agent run
        """
        self.agent_model = agent_model
        self.telemetry_handler = telemetry_handler
        self.max_events_per_agent = max_events_per_agent
        self.agent_runner = AgentRunner(telemetry_handler)
    
    def run_fix_agent(
        self, 
        fix_agent: AgentPrompts, 
        remediation_id: str, 
        repo_root: Path, 
        max_events: int, 
        skip_security_test: bool, 
        agent_model: str = None
    ) -> str:
        """
        Runs the fix agent to analyze and fix a vulnerability.
        
        Args:
            fix_agent: The fix agent prompts
            remediation_id: The ID of the remediation
            repo_root: The root directory of the repository
            max_events: Maximum number of events per agent run
            skip_security_test: Whether to skip writing security tests
            agent_model: Optional override for the agent model
            
        Returns:
            str: The fix agent's output summary
            
        Raises:
            SystemExit: If agent execution fails
        """
        # Use the instance model if no override provided
        model = agent_model or self.agent_model
        
        # Forward to the existing implementation
        return self.agent_runner.run_fix_agent(
            fix_agent=fix_agent,
            remediation_id=remediation_id,
            repo_root=repo_root,
            max_events_per_agent=max_events or self.max_events_per_agent,
            skip_writing_security_test=skip_security_test,
            agent_model=model
        )
    
    def run_qa_agent(
        self,
        build_output: str,
        changed_files: List[str],
        build_command: str,
        repo_root: Path,
        max_events_per_agent: int,
        remediation_id: str,
        agent_model: str,
        qa_history: Optional[List[str]] = None,
        qa_system_prompt: Optional[str] = None,
        qa_user_prompt: Optional[str] = None
    ) -> str:
        """
        Runs the QA agent to fix build errors.
        
        Args:
            build_output: The output from the build command
            changed_files: List of files changed by the fix agent
            build_command: The build command to use
            repo_root: The root directory of the repository
            max_events_per_agent: Maximum number of events per agent run
            remediation_id: The ID of the remediation
            agent_model: The LLM model to use
            qa_history: Optional history of previous QA attempts
            qa_system_prompt: Optional system prompt override
            qa_user_prompt: Optional user prompt override
            
        Returns:
            str: The QA agent's output summary
            
        Raises:
            SystemExit: If agent execution fails
        """
        # Forward to the existing implementation
        return self.agent_runner.run_qa_agent(
            build_output=build_output,
            changed_files=changed_files,
            build_command=build_command,
            repo_root=repo_root,
            remediation_id=remediation_id,
            agent_model=agent_model,
            max_events_per_agent=max_events_per_agent or self.max_events_per_agent,
            qa_history=qa_history,
            qa_system_prompt=qa_system_prompt,
            qa_user_prompt=qa_user_prompt
        )
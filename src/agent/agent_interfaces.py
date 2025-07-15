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

"""
Interfaces for agent-related components to facilitate dependency injection
and break circular imports between modules.
"""

from typing import List, Optional, Protocol, runtime_checkable
from pathlib import Path

# Forward reference for type hints
AgentPromptsType = "AgentPrompts"  # Will be resolved at runtime


@runtime_checkable
class AgentRunnerInterface(Protocol):
    """
    Interface for agent runners that can execute fix and QA agents.
    This interface helps break circular dependencies between modules.
    
    Classes that implement this interface must provide both run_fix_agent
    and run_qa_agent methods with compatible signatures.
    """
    
    def run_fix_agent(
        self,
        fix_agent: AgentPromptsType,
        remediation_id: str,
        repo_root: Path,
        max_events: int,
        skip_security_test: bool,
        agent_model: Optional[str] = None
    ) -> str:
        """
        Runs the fix agent to generate code changes.
        
        Args:
            fix_agent: The agent prompts for fix generation
            remediation_id: The ID of the remediation
            repo_root: The root directory of the repository
            max_events: Maximum number of events for the agent
            skip_security_test: Whether to skip security test generation
            agent_model: Optional model override
            
        Returns:
            str: The output of the fix agent
        """
        ...
    
    def run_qa_agent(
        self,
        build_output: str,
        changed_files: List[str],
        build_command: str,
        repo_root: Path,
        remediation_id: str,
        agent_model: str,
        max_events_per_agent: int,
        qa_history: List[str],
        qa_system_prompt: str,
        qa_user_prompt: str
    ) -> str:
        """
        Runs the QA agent to validate and fix build issues.
        
        Args:
            build_output: The output from the build process
            changed_files: List of changed files
            build_command: The build command
            repo_root: Repository root path
            remediation_id: The remediation ID
            agent_model: The model to use for the agent
            max_events_per_agent: Maximum events per agent run
            qa_history: History of previous QA attempts
            qa_system_prompt: System prompt for the QA agent
            qa_user_prompt: User prompt for the QA agent
            
        Returns:
            str: The output of the QA agent
        """
        ...
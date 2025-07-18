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
from typing import Tuple, Optional

from src.utils import log, debug_log, error_exit
from src.api.contrast_api_client import FailureCategory
from src.agent.agent_prompts import AgentPrompts
from src.build.build_qa_manager import BuildQaManager
from src.agent.agent_system import AgentSystem

class AgentManager:
    """
    Main manager for the AI agent workflow.
    Orchestrates the vulnerability remediation process using AI agents.
    
    CRITICAL: The remediate_vulnerability() method signature must be preserved
    exactly for integration testing purposes.
    """
    
    def __init__(self, telemetry_handler, build_qa_manager=None, agent_system=None):
        """
        Initialize the agent manager with required components.
        
        Args:
            telemetry_handler: Handler for telemetry data
            build_qa_manager: Optional BuildQaManager instance (for dependency injection)
            agent_system: Optional AgentSystem instance (for dependency injection)
        """
        debug_log("Initializing AgentManager")
        self.telemetry_handler = telemetry_handler
        
        # Use provided dependencies or create defaults
        self.build_qa_manager = build_qa_manager or BuildQaManager(telemetry_handler)
        self.agent_system = agent_system or AgentSystem(
            agent_model=None,  # Will be provided in remediate_vulnerability
            telemetry_handler=telemetry_handler
        )
        
    def remediate_vulnerability(
        self, 
        fix_agent: AgentPrompts, 
        qa_agent: AgentPrompts, 
        remediation_id: str, 
        build_command: str,
        formatting_command: str,
        repo_root: Path, 
        skip_qa_review: bool, 
        max_qa_attempts_setting: int,
        max_events_per_agent: int,
        skip_writing_security_test: bool,
        agent_model: str
    ) -> Tuple[bool, str]:
        """
        CRITICAL: This method signature must be preserved exactly as is
        for integration testing purposes.
        
        Resolves a vulnerability using the provided agents.
        
        Args:
            fix_agent: The fix agent prompts
            qa_agent: The QA agent prompts
            remediation_id: The ID of the remediation
            build_command: The command to build the application
            formatting_command: The command to format code
            repo_root: The root directory of the repository
            skip_qa_review: Whether to skip QA review
            max_qa_attempts_setting: Maximum number of QA attempts
            max_events_per_agent: Maximum number of events per agent run
            skip_writing_security_test: Whether to skip writing security tests
            agent_model: The AI model to use
            
        Returns:
            Tuple[bool, str]: Success status and result summary
        """
        result = ""
    
        # Ensure the build is not broken before running the fix agent
        log("\n--- Running Build Before Fix ---")
        prefix_build_success, prefix_build_output = self.build_qa_manager.run_build(
            remediation_id, build_command, repo_root
        )
        
        if not prefix_build_success:
            # Analyze build failure and show error summary
            from src.build_output_analyzer import extract_build_errors
            error_analysis = extract_build_errors(prefix_build_output)
            log("\n❌ Build is broken ❌ -- No fix attempted.")
            log(f"Build output:\n{error_analysis}")
            error_exit(remediation_id, FailureCategory.INITIAL_BUILD_FAILURE.value)
        
        # Run the fix agent
        result += self.agent_system.run_fix_agent(
            fix_agent=fix_agent,
            remediation_id=remediation_id,
            repo_root=repo_root,
            max_events=max_events_per_agent,
            skip_security_test=skip_writing_security_test,
            agent_model=agent_model
        )
        
        # Check if the fix agent encountered an error
        if result.startswith("Error during AI fix agent execution:"):
            log("Fix agent encountered an unrecoverable error. Skipping this vulnerability.")
            error_message = result[len("Error during AI fix agent execution:"):].strip()
            log(f"Error details: {error_message}")
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
        
        if skip_qa_review:
            log("Skipping QA Review based on SKIP_QA_REVIEW setting.")
            return True, result
        
        # Create a notify_failure_callback for QA to use
        def notify_failure_callback(remediation_id, failure_category):
            # Use the ContrastApiClient singleton
            try:
                from src.api.contrast_api_client import ContrastApiClient
                contrast_api_client = ContrastApiClient()
                if hasattr(contrast_api_client, 'notify_remediation_failed'):
                    return contrast_api_client.notify_remediation_failed(
                        remediation_id=remediation_id,
                        failure_category=failure_category
                    )
                else:
                    log("ContrastApiClient instance doesn't have notify_remediation_failed method.", is_error=True)
                    return False
            except Exception as e:
                log(f"ContrastApiClient not initialized or error: {e}. Cannot notify remediation failure.", is_error=True)
                return False
        
        # Run the QA process
        qa_success, qa_result = self.build_qa_manager.run_qa_process(
            qa_agent_runner=self.agent_system,
            qa_agent=qa_agent,
            remediation_id=remediation_id,
            build_command=build_command,
            formatting_command=formatting_command,
            repo_root=repo_root,
            max_qa_attempts_setting=max_qa_attempts_setting,
            agent_model=agent_model,
            max_events_per_agent=max_events_per_agent,
            notify_failure_callback=notify_failure_callback
        )
        
        return qa_success, result + qa_result

class AgentManagerFactory:
    """
    Factory for creating AgentManager instances with appropriate dependencies.
    """
    
    @staticmethod
    def create_production_agent_manager(telemetry_handler):
        """
        Creates an AgentManager with real dependencies for production use.
        
        Args:
            telemetry_handler: The telemetry handler to use
            
        Returns:
            AgentManager: A fully configured AgentManager instance
        """
        build_qa_manager = BuildQaManager(telemetry_handler)
        agent_system = AgentSystem(None, telemetry_handler)  # Agent model will be provided later
        return AgentManager(telemetry_handler, build_qa_manager, agent_system)
    
    @staticmethod
    def create_test_agent_manager(telemetry_handler, build_qa_manager=None, agent_system=None):
        """
        Creates an AgentManager with mock dependencies for testing.
        
        Args:
            telemetry_handler: The telemetry handler to use
            build_qa_manager: Optional mock BuildQaManager
            agent_system: Optional mock AgentSystem
            
        Returns:
            AgentManager: An AgentManager instance with injected dependencies
        """
        return AgentManager(telemetry_handler, build_qa_manager, agent_system)
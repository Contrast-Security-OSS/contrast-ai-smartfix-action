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

import sys
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Set
from src.utils import debug_log, log
from src.agent.agent_prompts import AgentPrompts
from src.api.contrast_api_client import FailureCategory

class SmartFixOrchestrator:
    """
    Main orchestrator for the SmartFix workflow.
    Manages the overall process of finding and fixing vulnerabilities.
    """
    
    def __init__(
        self, 
        config, 
        contrast_client, 
        git_handler, 
        agent_manager, 
        telemetry_handler
    ):
        """
        Initialize the SmartFix orchestrator with all dependencies.
        
        Args:
            config: Configuration manager
            contrast_client: Client for Contrast API interactions
            git_handler: Handler for Git operations
            agent_manager: Manager for AI agents
            telemetry_handler: Handler for telemetry data
        """
        self.config = config
        self.contrast_client = contrast_client
        self.git_handler = git_handler
        self.agent_manager = agent_manager
        self.telemetry_handler = telemetry_handler
        
        # Runtime state
        self.start_time = datetime.now()
        self.processed_one = False
        self.max_runtime = timedelta(hours=3)
        self.github_repo_url = f"https://github.com/{config.github_repository}"
        self.skipped_vulns = set()
        self.remediation_id = "unknown"
        
    def process_vulnerabilities(self):
        """
        Main entry point for processing vulnerabilities.
        Orchestrates the entire SmartFix workflow.
        """
        # For Phase 1, most of this will still call legacy code
        self.start_time = datetime.now()
        log("--- Starting Contrast AI SmartFix Script ---")
        debug_log(f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Initial Setup
        self.git_handler.configure_git_user()
        
        # Check Open PR Limit
        log("\n::group::--- Checking Open PR Limit ---")
        label_prefix_to_check = "contrast-vuln-id:"
        current_open_pr_count = self.git_handler.count_open_prs_with_prefix(label_prefix_to_check)
        if current_open_pr_count >= self.config.max_open_prs:
            log(f"Found {current_open_pr_count} open PR(s) with label prefix '{label_prefix_to_check}'.")
            log(f"This meets or exceeds the configured limit of {self.config.max_open_prs}.")
            log("Exiting script to avoid creating more PRs.")
            sys.exit(0)
        else:
            log(f"Found {current_open_pr_count} open PR(s) with label prefix '{label_prefix_to_check}' (Limit: {self.config.max_open_prs}). Proceeding...")
        log("\n::endgroup::")
        
        # Main Processing Loop
        self._process_vulnerabilities_loop()
        
        # Calculate total runtime
        end_time = datetime.now()
        total_runtime = end_time - self.start_time
        
        if not self.processed_one:
            log("\n--- No vulnerabilities were processed in this run. ---")
        else:
            log("\n--- Finished processing vulnerabilities. At least one vulnerability was successfully processed. ---")
        
        log(f"\n--- Script finished (total runtime: {total_runtime}) ---")
    
    def _process_vulnerabilities_loop(self):
        """
        Main loop for processing vulnerabilities.
        Fetches and processes vulnerabilities until termination conditions are met.
        """
        while True:
            self.telemetry_handler.reset_vuln_specific_telemetry()
            
            # Check if we've exceeded the maximum runtime
            current_time = datetime.now()
            elapsed_time = current_time - self.start_time
            if elapsed_time > self.max_runtime:
                log(f"\n--- Maximum runtime of 3 hours exceeded (actual: {elapsed_time}). Stopping processing. ---")
                remediation_notified = self.contrast_client.notify_remediation_failed(
                    remediation_id=self.remediation_id,
                    failure_category=FailureCategory.EXCEEDED_TIMEOUT.value
                )
                
                if remediation_notified:
                    log(f"Successfully notified Remediation service about exceeded timeout for remediation {self.remediation_id}.")
                else:
                    log(f"Failed to notify Remediation service about exceeded timeout for remediation {self.remediation_id}.", is_warning=True)
                break
            
            # Check if we've reached the max PR limit
            current_open_pr_count = self.git_handler.count_open_prs_with_prefix("contrast-vuln-id:")
            if current_open_pr_count >= self.config.max_open_prs:
                log(f"\n--- Reached max PR limit ({self.config.max_open_prs}). Current open PRs: {current_open_pr_count}. Stopping processing. ---")
                break
            
            # Fetch Next Vulnerability and Prompts from API
            log("\n::group::--- Fetching next vulnerability and prompts from Contrast API ---")
            
            vulnerability_data = self.contrast_client.get_vulnerability_with_prompts(
                self.config.max_open_prs, 
                self.github_repo_url,
                self.config.vulnerability_severities
            )
            log("\n::endgroup::")
            
            if not vulnerability_data:
                log("No more vulnerabilities found to process or API error occurred. Stopping processing.")
                break
            
            # Process the vulnerability
            self._process_single_vulnerability(vulnerability_data)
    
    def _process_single_vulnerability(self, vulnerability_data):
        """
        Process a single vulnerability.
        
        Args:
            vulnerability_data: The vulnerability data from the API
        """
        # Extract vulnerability details and prompts from the response
        vuln_uuid = vulnerability_data['vulnerabilityUuid']
        vuln_title = vulnerability_data['vulnerabilityTitle']
        self.remediation_id = vulnerability_data['remediationId']
        fix_system_prompt = vulnerability_data['fixSystemPrompt']
        fix_user_prompt = vulnerability_data['fixUserPrompt']
        qa_system_prompt = vulnerability_data['qaSystemPrompt']
        qa_user_prompt = vulnerability_data['qaUserPrompt']
        
        # Populate vulnInfo in telemetry
        self.telemetry_handler.update_telemetry("vulnInfo.vulnId", vuln_uuid)
        self.telemetry_handler.update_telemetry("vulnInfo.vulnRule", vulnerability_data['vulnerabilityRuleName'])
        self.telemetry_handler.update_telemetry("additionalAttributes.remediationId", self.remediation_id)
        
        log(f"\n::group::--- Considering Vulnerability: {vuln_title} (UUID: {vuln_uuid}) ---")
        
        # Check for Existing PRs
        label_name, _, _ = self.git_handler.generate_label_details(vuln_uuid)
        pr_status = self.git_handler.check_pr_status_for_label(label_name)
        
        # Changed this logic to check only for OPEN PRs for dev purposes
        if pr_status == "OPEN":
            log(f"Skipping vulnerability {vuln_uuid} as an OPEN PR with label '{label_name}' already exists.")
            log("\n::endgroup::")
            if vuln_uuid in self.skipped_vulns:
                log(f"Already skipped {vuln_uuid} before, breaking loop to avoid infinite loop.")
                return False
            self.skipped_vulns.add(vuln_uuid)
            return True  # Continue to next vulnerability
        else:
            log(f"No existing OPEN or MERGED PR found for vulnerability {vuln_uuid}. Proceeding with fix attempt.")
        log("\n::endgroup::")
        log(f"\n\033[0;33m Selected vuln to fix: {vuln_title} \033[0m")
        
        # Prepare a clean repository state and branch for the fix
        new_branch_name = self.git_handler.get_branch_name(self.remediation_id)
        try:
            self.git_handler.prepare_feature_branch(self.remediation_id)
        except SystemExit:
            log(f"Error preparing feature branch {new_branch_name}. Skipping to next vulnerability.")
            return True  # Continue to next vulnerability
        
        # Run the remediation process
        remediation_success, ai_fix_summary_full = self.agent_manager.remediate_vulnerability(
            fix_agent=AgentPrompts(
                system_prompt=fix_system_prompt,
                user_prompt=AgentPrompts.process_fix_user_prompt(fix_user_prompt, self.config.skip_writing_security_test)
            ),
            qa_agent=AgentPrompts(
                system_prompt=qa_system_prompt,
                user_prompt=qa_user_prompt
            ),
            repo_root=self.config.repo_root,
            skip_qa_review=self.config.skip_qa_review,
            remediation_id=self.remediation_id,
            build_command=self.config.build_command,
            formatting_command=self.config.formatting_command,
            max_qa_attempts_setting=self.config.max_qa_attempts,
            max_events_per_agent=self.config.max_events_per_agent,
            skip_writing_security_test=self.config.skip_writing_security_test,
            agent_model=self.config.agent_model
        )
        
        if not remediation_success:
            self.git_handler.cleanup_branch(new_branch_name)
            self.contrast_client.send_telemetry_data()
            return True  # Move to the next vulnerability
        
        # Git and GitHub Operations
        log("\n--- Proceeding with Git & GitHub Operations ---")
        self.git_handler.stage_changes()
        
        if self.git_handler.check_status():
            commit_message = self.git_handler.generate_commit_message(vuln_title, vuln_uuid)
            self.git_handler.commit_changes(commit_message)
            
            # Create Pull Request
            pr_title = self.git_handler.generate_pr_title(vuln_title)
            
            # Push and Create PR
            self.git_handler.push_branch(new_branch_name)
            
            label_name, label_desc, label_color = self.git_handler.generate_label_details(vuln_uuid)
            label_created = self.git_handler.ensure_label(label_name, label_desc, label_color)
            
            if not label_created:
                log(f"Could not create GitHub label '{label_name}'. PR will be created without a label.", is_warning=True)
                label_name = ""  # Clear label_name to avoid using it in PR creation
            
            pr_title = self.git_handler.generate_pr_title(vuln_title)
            # Create a brief summary for the telemetry aiSummaryReport (limited to 255 chars in DB)
            # Generate an optimized summary using the dedicated function in telemetry_handler
            brief_summary = self.telemetry_handler.create_ai_summary_report(ai_fix_summary_full)
            
            # Update telemetry with our optimized summary
            self.telemetry_handler.update_telemetry("resultInfo.aiSummaryReport", brief_summary)
            
            try:
                # Set a flag to track if we should try the fallback approach
                pr_creation_success = False
                pr_url = ""  # Initialize pr_url
                
                # Try to create the PR using the GitHub CLI
                log("Attempting to create a pull request...")
                pr_url = self.git_handler.create_pr(
                    pr_title, 
                    ai_fix_summary_full, 
                    self.remediation_id, 
                    self.config.base_branch, 
                    label_name
                )
                
                if pr_url:
                    pr_creation_success = True
                    
                    # Extract PR number from PR URL
                    # PR URL format is like: https://github.com/org/repo/pull/123
                    pr_number = None
                    try:
                        # Use a more robust method to extract the PR number
                        pr_match = re.search(r'/pull/(\d+)', pr_url)
                        debug_log(f"Extracting PR number from URL '{pr_url}', match object: {pr_match}")
                        if pr_match:
                            pr_number = int(pr_match.group(1))
                            debug_log(f"Successfully extracted PR number: {pr_number}")
                        else:
                            log(f"Could not find PR number pattern in URL: {pr_url}", is_warning=True)
                    except (ValueError, IndexError, AttributeError) as e:
                        log(f"Could not extract PR number from URL: {pr_url} - Error: {str(e)}")
                    
                    # Notify the Remediation backend service about the PR
                    if pr_number is None:
                        pr_number = 1
                    
                    remediation_notified = self.contrast_client.notify_remediation_pr_opened(
                        remediation_id=self.remediation_id,
                        pr_number=pr_number,
                        pr_url=pr_url
                    )
                    if remediation_notified:
                        log(f"Successfully notified Remediation service about PR for remediation {self.remediation_id}.")
                    else:
                        log(f"Failed to notify Remediation service about PR for remediation {self.remediation_id}.", is_warning=True)
                else:
                    # This case should ideally be handled by create_pr exiting or returning empty
                    log("PR creation did not return a URL. Assuming failure.")
                
                self.telemetry_handler.update_telemetry("resultInfo.prCreated", pr_creation_success)
                
                if not pr_creation_success:
                    log("\n--- PR creation failed ---")
                    self._exit_with_failure(FailureCategory.GENERATE_PR_FAILURE.value)
                
                self.processed_one = True  # Mark that we successfully processed one
                log(f"\n--- Successfully processed vulnerability {vuln_uuid}. Continuing to look for next vulnerability... ---")
            except Exception as e:
                log(f"Error creating PR: {e}")
                log("\n--- PR creation failed ---")
                self._exit_with_failure(FailureCategory.GENERATE_PR_FAILURE.value)
        else:
            log("Skipping commit, push, and PR creation as no changes were detected by the agent.")
            # Clean up the branch if no changes were made
            self.git_handler.cleanup_branch(new_branch_name)
            return True  # Try the next vulnerability
        
        self.contrast_client.send_telemetry_data()
        return True
    
    def _exit_with_failure(self, failure_category):
        """
        Exits the orchestrator with a failure notification.
        
        Args:
            failure_category: The category of the failure
        """
        from src.utils import error_exit
        error_exit(self.remediation_id, failure_category)
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

import sys
import os
import re
import subprocess
from datetime import datetime, timedelta

# Import configurations and utilities
import config
from utils import debug_print, run_command
from qa_handler import run_build_command
from version_check import do_version_check

# Import domain-specific handlers
import contrast_api
import agent_handler
import git_handler
import qa_handler

def main():
    """Main orchestration logic."""

    start_time = datetime.now()
    print("--- Starting Contrast AI SmartFix Script ---")
    debug_print(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # --- Version Check ---
    do_version_check()

    # --- Use Build Command and Max Attempts/PRs from Config ---
    build_command = config.BUILD_COMMAND
    if build_command:
        debug_print(f"Build command specified: {build_command}")
    else:
        print("BUILD_COMMAND not set or empty.")
        sys.exit(1)

    formatting_command = config.FORMATTING_COMMAND
    if formatting_command:
        debug_print(f"Formatting command specified: {formatting_command}")
    else:
        print("FORMATTING_COMMAND not set or empty.")
        sys.exit(1)

    # Use the validated and normalized settings from config module
    # These values are already processed in config.py with appropriate validation and defaults
    max_qa_attempts_setting = config.MAX_QA_ATTEMPTS
    max_open_prs_setting = config.MAX_OPEN_PRS

    # --- Initial Setup ---
    git_handler.configure_git_user()

    # Check Open PR Limit
    print("\n::group::--- Checking Open PR Limit ---")
    label_prefix_to_check = "contrast-vuln-id:"
    current_open_pr_count = git_handler.count_open_prs_with_prefix(label_prefix_to_check)
    if current_open_pr_count >= max_open_prs_setting:
        print(f"Found {current_open_pr_count} open PR(s) with label prefix '{label_prefix_to_check}'.")
        print(f"This meets or exceeds the configured limit of {max_open_prs_setting}.")
        print("Exiting script to avoid creating more PRs.")
        sys.exit(0)
    else:
        print(f"Found {current_open_pr_count} open PR(s) with label prefix '{label_prefix_to_check}' (Limit: {max_open_prs_setting}). Proceeding...")
    print("\n::endgroup::", flush=True)
    # END Check Open PR Limit

    # --- Main Processing Loop ---
    processed_one = False
    max_runtime = timedelta(hours=3)  # Set maximum runtime to 3 hours
    
    # Construct GitHub repository URL (used for each API call)
    github_repo_url = f"https://github.com/{config.GITHUB_REPOSITORY}"
    debug_print(f"GitHub repository URL: {github_repo_url}")
    
    while True:
        # Check if we've exceeded the maximum runtime
        current_time = datetime.now()
        elapsed_time = current_time - start_time
        if elapsed_time > max_runtime:
            print(f"\n--- Maximum runtime of 3 hours exceeded (actual: {elapsed_time}). Stopping processing. ---")
            break
            
        # Check if we've reached the max PR limit
        current_open_pr_count = git_handler.count_open_prs_with_prefix(label_prefix_to_check)
        if current_open_pr_count >= max_open_prs_setting:
            print(f"\n--- Reached max PR limit ({max_open_prs_setting}). Current open PRs: {current_open_pr_count}. Stopping processing. ---")
            break

        # --- Fetch Next Vulnerability and Prompts from New API ---
        print("\n::group::--- Fetching next vulnerability and prompts from Contrast API ---")
        
        vulnerability_data = contrast_api.get_vulnerability_with_prompts(
            config.CONTRAST_HOST, config.CONTRAST_ORG_ID, config.CONTRAST_APP_ID,
            config.CONTRAST_AUTHORIZATION_KEY, config.CONTRAST_API_KEY,
            max_open_prs_setting, github_repo_url, config.VULNERABILITY_SEVERITIES
        )
        print("\n::endgroup::", flush=True)

        if not vulnerability_data:
            print("No more vulnerabilities found to process or API error occurred. Stopping processing.")
            break

        # Extract vulnerability details and prompts from the response
        vuln_uuid = vulnerability_data['vulnerabilityUuid']
        vuln_title = vulnerability_data['vulnerabilityTitle']
        remediation_id = vulnerability_data['remediationId']
        fix_system_prompt = vulnerability_data['fixSystemPrompt']
        fix_user_prompt = vulnerability_data['fixUserPrompt']
        qa_system_prompt = vulnerability_data['qaSystemPrompt']
        qa_user_prompt = vulnerability_data['qaUserPrompt']
        
        print(f"\n::group::--- Considering Vulnerability: {vuln_title} (UUID: {vuln_uuid}) ---")

        # --- Check for Existing PRs ---
        label_name, _, _ = git_handler.generate_label_details(vuln_uuid)
        pr_status = git_handler.check_pr_status_for_label(label_name)

        # Changed this logic to check only for OPEN PRs for dev purposes
        if pr_status == "OPEN":
            print(f"Skipping vulnerability {vuln_uuid} as an OPEN or MERGED PR with label '{label_name}' already exists.")
            print("\n::endgroup::", flush=True)
            continue # Move to the next potential vulnerability
        else:
            print(f"No existing OPEN or MERGED PR found for vulnerability {vuln_uuid}. Proceeding with fix attempt.")

        print("\n::endgroup::", flush=True)

        print(f"\n\033[0;33m Selected vuln to fix: {vuln_title} \033[0m")

        # Prepare a clean repository state and branch for the fix
        new_branch_name = git_handler.generate_branch_name(remediation_id)
        try:
            git_handler.prepare_feature_branch(new_branch_name)
        except SystemExit:
            print(f"Error preparing feature branch {new_branch_name}. Skipping to next vulnerability.")
            continue # Try next vulnerability
        
        # Ensure the build is not broken before running the fix agent
        print("\n--- Running Build Before Fix ---", flush=True)
        prefix_build_success, prefix_build_output = run_build_command(build_command, config.REPO_ROOT)
        if not prefix_build_success:
            print("\n❌ Build is broken ❌ -- No fix attempted.")
            print(f"Cleaning up branch: {new_branch_name}")
            run_command(["git", "checkout", config.BASE_BRANCH], check=False)
            run_command(["git", "branch", "-D", new_branch_name], check=False)
            continue # Try next vulnerability instead of exiting

        # --- Run AI Fix Agent ---
        ai_fix_summary_full = agent_handler.run_ai_fix_agent(
            config.REPO_ROOT, fix_system_prompt, fix_user_prompt
        )
        
        # Check if the fix agent encountered an error
        if ai_fix_summary_full.startswith("Error during AI fix agent execution:"):
            print("Fix agent encountered an unrecoverable error. Skipping this vulnerability.")
            error_message = ai_fix_summary_full[len("Error during AI fix agent execution:"):].strip()
            print(f"Error details: {error_message}")
            sys.exit(1)
            
        # The ai_fix_summary_full variable now directly contains the intended PR body
        # (either extracted from <pr_body> tags by agent_handler or the full agent response).
        # The redundant extraction block previously here has been removed.

        # --- Git and GitHub Operations ---
        print("\n--- Proceeding with Git & GitHub Operations ---", flush=True)
        # Note: Git user config moved to the start of main
        # Branch creation moved before the initial build

        git_handler.stage_changes()

        if git_handler.check_status(): # Only proceed if changes were detected
            commit_message = git_handler.generate_commit_message(vuln_title, vuln_uuid)
            git_handler.commit_changes(commit_message)
            initial_changed_files = git_handler.get_last_commit_changed_files() # Get files changed by fix agent

            # --- QA Loop ---
            if not config.SKIP_QA_REVIEW and build_command:
                debug_print("Proceeding with QA Review as SKIP_QA_REVIEW is false and BUILD_COMMAND is provided.")
                build_success, final_changed_files, used_build_command, qa_summary_log = qa_handler.run_qa_loop(
                    build_command=build_command,
                    repo_root=config.REPO_ROOT,
                    max_qa_attempts=max_qa_attempts_setting,
                    initial_changed_files=initial_changed_files,
                    formatting_command=formatting_command,
                    qa_system_prompt=qa_system_prompt,
                    qa_user_prompt=qa_user_prompt
                )

                qa_section = "\n\n---\n\n## Review \n\n"

                if used_build_command:
                    qa_section += f"*   **Build Run:** Yes (`{used_build_command}`)\n"

                    if build_success:
                        qa_section += "*   **Final Build Status:** Success ✅\n"
                    else:
                        qa_section += "*   **Final Build Status:** Failure ❌\n"
                else: # Build command wasn't run (either not provided or no changes made)
                    qa_section += "*   **Build Run:** No"
                    if not used_build_command:
                        qa_section += " (BUILD_COMMAND not provided)\n"
                    qa_section += "\n*   **Final Build Status:** Skipped\n" # Simplified status
                
                # Skip PR creation if QA was run and the build is failing
                # or if the QA agent encountered an error (detected by checking qa_summary_log entries)
                if (used_build_command and not build_success) or any(s.startswith("Error during QA agent execution:") for s in qa_summary_log):
                    if any(s.startswith("Error during QA agent execution:") for s in qa_summary_log):
                        print("\n--- Skipping PR creation as QA Agent encountered an error ---")
                    else:
                        print("\n--- Skipping PR creation as QA Agent failed to fix build issues ---")
                    
                    print(f"Cleaning up branch: {new_branch_name}")
                    # Use the more robust cleanup method
                    run_command(["git", "checkout", config.BASE_BRANCH], check=False)
                    run_command(["git", "branch", "-D", new_branch_name], check=False)
                    continue # Move to the next vulnerability

            else: # QA is skipped
                qa_section = "" # Ensure qa_section is empty if QA is skipped
                if config.SKIP_QA_REVIEW:
                    print("Skipping QA Review based on SKIP_QA_REVIEW setting.")
                elif not build_command:
                    print("Skipping QA Review as no BUILD_COMMAND was provided.")

            # --- Create Pull Request ---
            pr_title = git_handler.generate_pr_title(vuln_title)
            # Use the result from agent_handler.run_ai_fix_agent directly as the base PR body.
            # agent_handler.run_ai_fix_agent is expected to return the PR body content
            # (extracted from <pr_body> tags) or the full agent summary if extraction fails.
            pr_body_base = ai_fix_summary_full
            debug_print("Using agent's output (processed by agent_handler) as PR body base.")

            # --- Push and Create PR ---
            git_handler.push_branch(new_branch_name) # Push the final commit (original or amended)

            label_name, label_desc, label_color = git_handler.generate_label_details(vuln_uuid)
            label_created = git_handler.ensure_label(label_name, label_desc, label_color)
            
            if not label_created:
                print(f"Warning: Could not create GitHub label '{label_name}'. PR will be created without a label.")
                label_name = ""  # Clear label_name to avoid using it in PR creation

            pr_title = git_handler.generate_pr_title(vuln_title)

            updated_pr_body = pr_body_base + qa_section

            try:
                # Set a flag to track if we should try the fallback approach
                pr_creation_success = False
                pr_url = "" # Initialize pr_url
                
                # Try to create the PR using the GitHub CLI
                print("Attempting to create a pull request...")
                pr_url = git_handler.create_pr(pr_title, updated_pr_body, new_branch_name, config.BASE_BRANCH, label_name)
                
                if pr_url:
                    pr_creation_success = True
                    
                    # Extract PR number from PR URL
                    # PR URL format is like: https://github.com/org/repo/pull/123
                    pr_number = None
                    try:
                        # Use a more robust method to extract the PR number
                        
                        pr_match = re.search(r'/pull/(\d+)', pr_url)
                        debug_print(f"Extracting PR number from URL '{pr_url}', match object: {pr_match}")
                        if pr_match:
                            pr_number = int(pr_match.group(1))
                            debug_print(f"Successfully extracted PR number: {pr_number}")
                        else:
                            print(f"Warning: Could not find PR number pattern in URL: {pr_url}", flush=True)
                    except (ValueError, IndexError, AttributeError) as e:
                        print(f"Warning: Could not extract PR number from URL: {pr_url} - Error: {str(e)}", flush=True)
                    
                    # Notify the Remediation backend service about the PR
                    if pr_number is None:
                        pr_number = 1;

                    remediation_notified = contrast_api.notify_remediation_pr_opened(
                        remediation_id=remediation_id,
                        pr_number=pr_number,
                        pr_url=pr_url,
                        contrast_host=config.CONTRAST_HOST,
                        contrast_org_id=config.CONTRAST_ORG_ID,
                        contrast_app_id=config.CONTRAST_APP_ID,
                        contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                        contrast_api_key=config.CONTRAST_API_KEY
                    )
                    if remediation_notified:
                        print(f"Successfully notified Remediation service about PR for remediation {remediation_id}.", flush=True)
                    else:
                        print(f"Warning: Failed to notify Remediation service about PR for remediation {remediation_id}.", flush=True)
                else:
                    # This case should ideally be handled by create_pr exiting or returning empty
                    # and then the logic below for SKIP_PR_ON_FAILURE would trigger.
                    # However, if create_pr somehow returns without a URL but doesn't cause an exit:
                    print("PR creation did not return a URL. Assuming failure.", flush=True)
                    pr_creation_success = False
                
                if not pr_creation_success:
                    print("\n--- PR creation failed, but changes were pushed to branch ---", flush=True)
                    print(f"Branch name: {new_branch_name}", flush=True)
                    print("Changes can be manually viewed and merged if needed.", flush=True)
                    break;
                
                processed_one = True # Mark that we successfully processed one
                print(f"\n--- Successfully processed vulnerability {vuln_uuid}. Continuing to look for next vulnerability... ---")
            except Exception as e:
                print(f"Error creating PR: {e}")
                print("\n--- PR creation failed, but changes were pushed to branch ---")
                print(f"Branch name: {new_branch_name}")
                print("Changes can be manually viewed and merged if needed.")
                break;
        else:
            print("Skipping commit, push, and PR creation as no changes were detected by the agent.")
            # Clean up the branch if no changes were made
            print(f"Cleaning up unused branch: {new_branch_name}")
            run_command(["git", "checkout", config.BASE_BRANCH], check=False)
            run_command(["git", "branch", "-D", new_branch_name], check=False)
            continue # Try the next vulnerability

    # Calculate total runtime
    end_time = datetime.now()
    total_runtime = end_time - start_time
    
    if not processed_one:
        print("\n--- No vulnerabilities were processed in this run (either none found, all skipped, agent made no changes, or runtime limit exceeded). ---")
    else:
        print("\n--- Finished processing vulnerabilities. At least one vulnerability was successfully processed. ---")

    print(f"\n--- Script finished (total runtime: {total_runtime}) ---")

if __name__ == "__main__":
    main()

# %%

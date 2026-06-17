# -
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

import atexit
import sys
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

# Import configurations and utilities
from src.config import get_config
from src.smartfix.domains.telemetry import otel_provider
from src.smartfix.domains.telemetry import smartfix_metrics
from src.smartfix.shared.coding_agents import CodingAgents
from src.smartfix.shared.constants import CLASSIC, NORTHSTAR_ONLY
from src.smartfix.shared.exceptions import TokenBalanceExhaustedError
from src.utils import debug_log, log, error_exit
from src.smartfix.domains.telemetry import telemetry_handler
from src.version_check import do_version_check
from src.smartfix.domains.workflow.session_handler import handle_session_result, generate_qa_section
from src.smartfix.domains.workflow.build_runner import run_build_command
from src.smartfix.shared.failure_categories import FailureCategory

# Import domain-specific handlers
from src import contrast_api
from src.smartfix.domains.scm.git_operations import GitOperations
from src.github.github_operations import GitHubOperations
from src.smartfix.domains.scm.codeowners import get_reviewers_for_files

# Import domain models
from src.smartfix.domains.vulnerability.context import RemediationContext, PromptConfiguration, BuildConfiguration, RepositoryConfiguration
from src.smartfix.domains.vulnerability.models import Vulnerability

from src.smartfix.domains.agents.smartfix_agent import SmartFixAgent
from src.smartfix.domains.agents.asyncio_workarounds import apply_asyncio_workarounds, cleanup_event_loop
from src.github.external_coding_agent import ExternalCodingAgent
from src.smartfix.domains.workflow.pr_reconciliation import reconcile_open_remediations

config = get_config()
telemetry_handler.initialize_telemetry()

# Create SCM operations instances
git_ops = GitOperations()
github_ops = GitHubOperations()

apply_asyncio_workarounds()


def _extract_finding_ids(vulnerability_data: dict, fallback_remediation_id: str) -> tuple:
    """Extract and validate vuln_uuid, mode, issue_id, and primary_id from API response data."""
    vuln_uuid = vulnerability_data['vulnerabilityUuid']
    mode = vulnerability_data.get('mode', CLASSIC)
    issue_id = vulnerability_data.get('issueId')
    if mode == NORTHSTAR_ONLY and not issue_id:
        debug_log(f"NORTHSTAR_ONLY finding missing issueId; vuln_uuid={vuln_uuid}, remediationId={vulnerability_data.get('remediationId', 'unknown')}")
        error_exit(vulnerability_data.get('remediationId', fallback_remediation_id), FailureCategory.GENERAL_FAILURE.value)
    primary_id = issue_id if mode == NORTHSTAR_ONLY else vuln_uuid
    return vuln_uuid, mode, issue_id, primary_id


def main():
    """Entry point: initialise OTel, start root span, then run the implementation."""
    otel_provider.initialize_otel(config)
    atexit.register(otel_provider.shutdown_otel)

    # Use lists so _main_impl can mutate them and the finally block sees the
    # correct value even when _main_impl exits via error_exit()/sys.exit().
    vuln_count = [0]
    # Only counts PRs created by the SmartFix-internal agent.  External-agent
    # runs (Copilot, Claude Code) create their PR asynchronously after the
    # GitHub Issue is filed, so they are not reflected here.
    prs_created_count = [0]
    try:
        with otel_provider.start_span("smartfix-run") as run_span:
            run_span.set_attribute("session.id", config.GITHUB_RUN_ID)
            try:
                _main_impl(vuln_count, prs_created_count)
            finally:
                run_span.set_attribute("contrast.smartfix.vulnerabilities_total", vuln_count[0])
                run_span.set_attribute("contrast.smartfix.prs_created_total", prs_created_count[0])
    finally:
        otel_provider.shutdown_otel()


def _main_impl(vuln_count: list[int], prs_created_count: list[int]) -> None:  # noqa: C901
    """Main orchestration logic."""

    start_time = datetime.now()
    log("--- Starting Contrast AI SmartFix Script ---")

    # --- Validate app IDs ---
    if not config.CONTRAST_APP_ID and not config.CONTRAST_APP_IDS:
        log("Error: SmartFix could not find a Contrast application ID for this repository. "
            "Make sure this repository is instrumented by the Contrast Agent so that it "
            "has IAST findings in Contrast, then set one of the following inputs in your "
            "SmartFix workflow step:\n"
            "  contrast_app_id: '<your-app-id>'          # single application\n"
            "  contrast_app_ids: '[\"id-1\", \"id-2\"]'      # monorepo with multiple applications",
            is_error=True)
        sys.exit(1)

    debug_log(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # --- Version Check ---
    do_version_check()

    # --- Create Configuration Objects ---
    build_config = BuildConfiguration.from_config(config)
    repo_config = RepositoryConfiguration.from_config(config)

    debug_log(f"Build command: {build_config.build_command}")
    debug_log(f"Formatting command: {build_config.formatting_command}")
    debug_log(f"Repository path: {repo_config.repo_path}")

    # Use the validated and normalized settings from config module
    # These values are already processed in config.py with appropriate validation and defaults
    max_open_prs_setting = config.MAX_OPEN_PRS

    # --- Initial Build Validation ---
    # If the user explicitly configured a build command, verify it works on the
    # clean repo before spending LLM credits on vulnerability fixes
    if build_config.user_build_command:
        log("\n::group::--- Validating configured build command ---")
        log(f"Running initial build: {build_config.user_build_command}")
        build_success, build_output = run_build_command(
            build_config.user_build_command, repo_config.repo_path, "initial-build-check"
        )
        if not build_success:
            log("Initial build failed. The configured BUILD_COMMAND does not succeed on the "
                "clean repository. Please verify the command and fix any build issues before "
                "running SmartFix.", is_error=True)
            debug_log(f"Build output:\n{build_output}")
            log("\n::endgroup::")
            # No remediation ID exists yet — exit directly without notifying the backend.
            sys.exit(1)
        log("Initial build succeeded. Proceeding with vulnerability processing.")
        log("\n::endgroup::")

    # --- Initial Setup ---
    git_ops.configure_git_user()

    # --- Reconcile Orphaned Open Remediations ---
    log("\n::group::--- Reconciling open remediations against GitHub ---")
    reconcile_open_remediations(config, github_ops)
    log("\n::endgroup::")

    # Check Open PR Limit
    log("\n::group::--- Checking Open PR Limit ---")
    label_prefix_to_check = ("contrast-vuln-id:", "contrast-issue-id:")
    current_open_pr_count = github_ops.count_open_prs_with_prefix(label_prefix_to_check, "unknown")
    if current_open_pr_count >= max_open_prs_setting:
        log(f"Found {current_open_pr_count} open PR(s) with label prefix '{', '.join(label_prefix_to_check)}'.")
        log(f"This meets or exceeds the configured limit of {max_open_prs_setting}.")
        log("Exiting script to avoid creating more PRs.")
        sys.exit(0)
    else:
        log(f"Found {current_open_pr_count} open PR(s) with label prefix '{', '.join(label_prefix_to_check)}' (Limit: {max_open_prs_setting}). Proceeding...")
    log("\n::endgroup::")
    # END Check Open PR Limit

    # --- Main Processing Loop ---
    processed_one = False
    max_runtime = timedelta(hours=3)  # Set maximum runtime to 3 hours

    # Construct GitHub repository URL (used for each API call)
    parsed = urlparse(config.GITHUB_SERVER_URL)
    github_host = parsed.netloc
    github_repo_url = f"{github_host}/{config.GITHUB_REPOSITORY}"
    debug_log(f"GitHub repository URL: {github_repo_url}")
    skipped_vulns = set()  # TS-39904
    remediation_id = "unknown"
    previous_primary_id = None  # Track previous primary identifier to detect duplicates
    discovered_build_cmd = None   # Build command found by agent at runtime; carried forward across iterations
    discovered_format_cmd = None  # Format command found by agent at runtime; carried forward across iterations

    while True:
        telemetry_handler.reset_vuln_specific_telemetry()
        smartfix_metrics.reset_vuln_token_accumulator()
        # Check if we've exceeded the maximum runtime
        current_time = datetime.now()
        elapsed_time = current_time - start_time
        if elapsed_time > max_runtime:
            log(f"\n--- Maximum runtime of 3 hours exceeded (actual: {elapsed_time}). Stopping processing. ---")
            remediation_notified = contrast_api.notify_remediation_failed_org(
                remediation_id=remediation_id,
                failure_category=FailureCategory.EXCEEDED_TIMEOUT.value,
                contrast_host=config.CONTRAST_HOST,
                contrast_org_id=config.CONTRAST_ORG_ID,
                contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                contrast_api_key=config.CONTRAST_API_KEY
            )

            if remediation_notified:
                log(f"Successfully notified Remediation service about exceeded timeout for remediation {remediation_id}.")
            else:
                log(f"Failed to notify Remediation service about exceeded timeout for remediation {remediation_id}.", is_warning=True)
            break

        # Check if we've reached the max PR limit
        current_open_pr_count = github_ops.count_open_prs_with_prefix(label_prefix_to_check, remediation_id)
        if current_open_pr_count >= max_open_prs_setting:
            log(f"\n--- Reached max PR limit ({max_open_prs_setting}). Current open PRs: {current_open_pr_count}. Stopping processing. ---")
            break

        # --- Fetch Next Vulnerability Data from API ---
        if config.CODING_AGENT == CodingAgents.SMARTFIX.name:
            # For SMARTFIX, get vulnerability with prompts
            log("\n::group::--- Fetching next vulnerability and prompts from Contrast API ---")
            vulnerability_data = contrast_api.get_org_prompt_details(
                config.CONTRAST_HOST, config.CONTRAST_ORG_ID, config.CONTRAST_APP_IDS,
                config.CONTRAST_AUTHORIZATION_KEY, config.CONTRAST_API_KEY,
                max_open_prs_setting, github_repo_url, config.VULNERABILITY_SEVERITIES,
            )
            log("\n::endgroup::")

            if not vulnerability_data:
                log("No more vulnerabilities found to process. Stopping processing.")
                break

            skipped_app_ids = vulnerability_data.get('skippedAppIds', [])
            if skipped_app_ids:
                log(f"Warning: {len(skipped_app_ids)} app(s) were inaccessible and skipped: {skipped_app_ids}", is_warning=True)

            # Extract vulnerability details and prompts from the response
            vuln_uuid, mode, issue_id, primary_id = _extract_finding_ids(vulnerability_data, remediation_id)

            # Check if this is the same primary identifier as the previous iteration
            if primary_id == previous_primary_id:
                if primary_id in skipped_vulns:
                    log(f"Finding {primary_id} was re-served after being handled. Breaking loop to avoid infinite processing.")
                    break
                log(f"Error: Backend provided the same primary identifier ({primary_id}) as the previous iteration. This indicates a backend error.", is_warning=True)
                error_exit(remediation_id, FailureCategory.GENERAL_FAILURE.value)

            vuln_title = vulnerability_data['vulnerabilityTitle']
            remediation_id = vulnerability_data['remediationId']
            session_id = vulnerability_data.get('sessionId')
            vuln_language = vulnerability_data.get('language')

            # Validate and create prompt configuration for SmartFix agent
            try:
                PromptConfiguration.validate_raw_prompts_data(vulnerability_data)
                prompts = PromptConfiguration.for_smartfix_agent(
                    fix_system_prompt=vulnerability_data['fixSystemPrompt'],
                    fix_user_prompt=vulnerability_data['fixUserPrompt'],
                    skip_writing_security_test=config.SKIP_WRITING_SECURITY_TEST,
                )
            except ValueError as e:
                log(f"Error: Invalid prompts from backend: {e}", is_error=True)
                error_exit(remediation_id, FailureCategory.GENERAL_FAILURE.value)
        else:
            # For external coding agents (GITHUB_COPILOT/CLAUDE_CODE), get vulnerability details
            log("\n::group::--- Fetching next vulnerability details from Contrast API ---")
            vulnerability_data = contrast_api.get_org_remediation_details(
                config.CONTRAST_HOST, config.CONTRAST_ORG_ID, config.CONTRAST_APP_IDS,
                config.CONTRAST_AUTHORIZATION_KEY, config.CONTRAST_API_KEY,
                github_repo_url, max_open_prs_setting, config.VULNERABILITY_SEVERITIES,
            )
            log("\n::endgroup::")

            if not vulnerability_data:
                log("No more vulnerabilities found to process. Stopping processing.")
                break

            skipped_app_ids = vulnerability_data.get('skippedAppIds', [])
            if skipped_app_ids:
                log(f"Warning: {len(skipped_app_ids)} app(s) were inaccessible and skipped: {skipped_app_ids}", is_warning=True)

            # Extract vulnerability details from the response (no prompts for external agents)
            vuln_uuid, mode, issue_id, primary_id = _extract_finding_ids(vulnerability_data, remediation_id)

            # Check if this is the same primary identifier as the previous iteration
            if primary_id == previous_primary_id:
                log(f"Error: Backend provided the same primary identifier ({primary_id}) as the previous iteration. This indicates a backend error.", is_warning=True)
                error_exit(remediation_id, FailureCategory.GENERAL_FAILURE.value)

            vuln_title = vulnerability_data['vulnerabilityTitle']
            remediation_id = vulnerability_data['remediationId']
            session_id = None  # External agents don't use Contrast LLM sessions
            vuln_language = vulnerability_data.get('language')

            # No prompts required for external agents
            prompts = PromptConfiguration()

        # Populate vulnInfo in telemetry
        telemetry_handler.update_telemetry("vulnInfo.vulnId", primary_id)
        telemetry_handler.update_telemetry("vulnInfo.vulnRule", vulnerability_data['vulnerabilityRuleName'])
        telemetry_handler.update_telemetry("vulnInfo.northstarMode", mode)
        telemetry_handler.update_telemetry("additionalAttributes.remediationId", remediation_id)

        finding_type = vulnerability_data.get('findingType', 'UNKNOWN')
        severity = vulnerability_data.get('vulnerabilitySeverity') or 'UNKNOWN'
        debug_log(f"Processing {finding_type} finding | id={primary_id} | severity={severity}")

        log(f"\n::group::--- Considering Finding: {vuln_title} (ID: {primary_id}) ---")

        # --- Check for Existing PRs ---
        label_name, _, _ = github_ops.generate_label_details(vuln_uuid, mode=mode, issue_id=issue_id)
        pr_status = github_ops.check_pr_status_for_label(label_name)

        # Changed this logic to check only for OPEN PRs for dev purposes
        if pr_status == "OPEN":
            log(f"Skipping finding {primary_id} as an OPEN PR with label '{label_name}' already exists.")
            log("\n::endgroup::")
            if primary_id in skipped_vulns:
                log(f"Finding {primary_id} was re-suggested after being skipped. "
                    f"This may indicate GitHub returned incorrect PR data. "
                    f"See https://www.githubstatus.com/ for possible incidents. "
                    f"Breaking loop to avoid infinite processing.")
                break
            skipped_vulns.add(primary_id)
            continue
        else:
            log(f"No existing OPEN or MERGED PR found for finding {primary_id}. Proceeding with fix attempt.")
        log("\n::endgroup::")

        # Update tracking variable now that we know we're actually processing this finding
        previous_primary_id = primary_id
        vuln_count[0] += 1

        log(f"\n\033[0;33m Selected vuln to fix: {vuln_title} \033[0m")

        # --- Create Common Remediation Context ---
        vulnerability = Vulnerability.from_api_data(vulnerability_data)

        # --- Operation span: one per vulnerability, child of the smartfix-run root span ---
        _op_fix_applied = False
        _op_files_modified = 0
        _op_pr_created = False
        _op_pr_url = ""
        _op_outcome = "failure"
        _op_fix_start = time.monotonic()

        smartfix_metrics.set_current_rule_name(vulnerability.rule_name)
        with otel_provider.start_span("fix-vulnerability") as op_span:
            op_span.set_attribute("contrast.finding.fingerprint", primary_id)
            op_span.set_attribute("contrast.finding.source", "runtime")
            op_span.set_attribute("contrast.finding.rule_id", vulnerability.rule_name)
            op_span.set_attribute("contrast.smartfix.coding_agent", config.CODING_AGENT.lower())

            try:
                context = RemediationContext(
                    remediation_id=remediation_id,
                    vulnerability=vulnerability,
                    prompts=prompts,
                    build_config=build_config,
                    repo_config=repo_config,
                    skip_writing_security_test=config.SKIP_WRITING_SECURITY_TEST,
                    session_id=session_id,
                    language=vuln_language,
                    mode=mode,
                    issue_id=issue_id,
                )

                # Propagate a build command discovered by a previous agent run so the next
                # agent skips the discovery step.  Only applies when no command was
                # user-configured (user_build_command is the sacred, user-supplied value).
                if discovered_build_cmd and not context.build_config.user_build_command:
                    context.build_config = BuildConfiguration(
                        build_command=discovered_build_cmd,
                        formatting_command=discovered_format_cmd,
                        build_command_source="agent_discovered",
                        format_command_source="agent_discovered" if discovered_format_cmd else "user_configured",
                        user_build_command=None,
                        user_format_command=None,
                    )
                    log(f"Reusing agent-discovered build command from previous run: {discovered_build_cmd}")

                # --- Check if we need to use the external coding agent ---
                if config.CODING_AGENT != CodingAgents.SMARTFIX.name:
                    external_agent = ExternalCodingAgent(config)
                    context.issue_body = external_agent.assemble_issue_body(vulnerability_data)

                    result = external_agent.remediate(context)

                    if result.success:
                        log("\n\n--- External Coding Agent successfully generated fixes ---")
                        processed_one = True
                        contrast_api.send_telemetry_data_org(
                            remediation_id=remediation_id,
                            telemetry_data=telemetry_handler.get_telemetry_data(),
                            contrast_host=config.CONTRAST_HOST,
                            contrast_org_id=config.CONTRAST_ORG_ID,
                            contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                            contrast_api_key=config.CONTRAST_API_KEY
                        )
                    continue  # Skip the built-in SmartFix code and PR creation

                telemetry_handler.update_telemetry("additionalAttributes.codingAgent", "INTERNAL-SMARTFIX")

                # Prepare a clean repository state and branch for the fix
                new_branch_name = git_ops.get_branch_name(remediation_id)
                try:
                    git_ops.prepare_feature_branch(remediation_id)
                except SystemExit:
                    log(f"Error preparing feature branch {new_branch_name}. Skipping to next vulnerability.")
                    continue

                # --- Run SmartFix Agent ---
                smartfix_agent = SmartFixAgent()

                # Run the agent remediation process
                # The agent will run the fix agent loop without doing any git operations
                # All git operations (staging, committing) happen in main.py after remediate() completes
                session = smartfix_agent.remediate(context)

                # Extract results from the session
                session_result = handle_session_result(session)

                if not session_result.should_continue:
                    log(f"Agent failed with reason: {session_result.failure_category}")
                    git_ops.cleanup_branch(new_branch_name)

                    # Map internal failure categories to server-recognized values
                    api_failure_category = session_result.failure_category
                    if api_failure_category == FailureCategory.BUILD_VERIFICATION_FAILED.value:
                        api_failure_category = FailureCategory.AGENT_FAILURE.value

                    contrast_api.notify_remediation_failed_org(
                        remediation_id=remediation_id,
                        failure_category=api_failure_category,
                        contrast_host=config.CONTRAST_HOST,
                        contrast_org_id=config.CONTRAST_ORG_ID,
                        contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                        contrast_api_key=config.CONTRAST_API_KEY
                    )

                    # Build verification failure means the build environment is broken —
                    # continuing to the next vuln would waste LLM spend on the same failure
                    if session_result.failure_category == FailureCategory.BUILD_VERIFICATION_FAILED.value:
                        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

                    continue  # Move to next vulnerability for other failure types

                # Persist the agent-discovered build command for subsequent vulnerability iterations.
                # Only save when there is no user-configured command (user_build_command is sacred).
                if not context.build_config.user_build_command and smartfix_agent._build_state:
                    new_build_cmd = smartfix_agent._build_state.get("build_cmd")
                    new_format_cmd = smartfix_agent._build_state.get("format_cmd")
                    if new_build_cmd and new_build_cmd != discovered_build_cmd:
                        discovered_build_cmd = new_build_cmd
                        discovered_format_cmd = new_format_cmd
                        log(f"Saving agent-discovered build command for future runs: {discovered_build_cmd}")

                ai_fix_summary_full = session_result.ai_fix_summary
                # Prefer the command the agent actually verified over the pre-configured value.
                # When no build command was configured, context.build_config.build_command is None
                # even though the agent may have discovered and verified one at runtime.
                verified_build_cmd = (
                    smartfix_agent._build_state.get("build_cmd")
                    if smartfix_agent._build_state
                    else context.build_config.build_command
                )
                qa_section = generate_qa_section(verified_build_cmd)

                # --- Git and GitHub Operations ---
                # All file changes from the agent (fix + formatting) are uncommitted at this point
                # Stage and commit everything together
                log("\n--- Proceeding with Git & GitHub Operations ---")
                git_ops.stage_changes()
                _op_files_modified = git_ops.get_staged_files_count()

                # Check if there are changes to commit
                if not git_ops.check_status():
                    # No changes detected - agent didn't make any modifications
                    log("No changes detected from agent execution. Notifying backend and skipping PR creation.")
                    _op_outcome = "no_code_changed"
                    git_ops.cleanup_branch(new_branch_name)
                    contrast_api.notify_remediation_failed_org(
                        remediation_id=remediation_id,
                        failure_category=FailureCategory.NO_CODE_CHANGED.value,
                        contrast_host=config.CONTRAST_HOST,
                        contrast_org_id=config.CONTRAST_ORG_ID,
                        contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                        contrast_api_key=config.CONTRAST_API_KEY
                    )
                    processed_one = True
                    continue

                _op_fix_applied = True

                # Commit all changes together (fix + formatting)
                commit_message = git_ops.generate_commit_message(vuln_title, vuln_uuid)
                git_ops.commit_changes(commit_message)
                log("Committed all agent changes.")

                # --- Create Pull Request ---
                pr_title = github_ops.generate_pr_title(vuln_title)
                # Use the result from SmartFix agent remediation as the base PR body.
                # The agent returns the PR body content (extracted from <pr_body> tags)
                # or the full agent summary if extraction fails.
                pr_body_base = ai_fix_summary_full
                debug_log("Using SmartFix agent's output as PR body base.")

                # --- Push and Create PR ---
                git_ops.push_branch(new_branch_name)  # Push the final commit (original or amended)

                label_name, label_desc, label_color = github_ops.generate_label_details(vuln_uuid, mode=mode, issue_id=issue_id)
                label_created = github_ops.ensure_label(label_name, label_desc, label_color)
                if not label_created:
                    log(f"Could not create GitHub label '{label_name}'. PR will be created without a label.", is_warning=True)
                    label_name = ""
                pr_title = github_ops.generate_pr_title(vuln_title)

                updated_pr_body = pr_body_base + qa_section

                # Create a brief summary for the telemetry aiSummaryReport (limited to 255 chars in DB)
                # Generate an optimized summary using the dedicated function in telemetry_handler
                brief_summary = telemetry_handler.create_ai_summary_report(updated_pr_body)

                # Update telemetry with our optimized summary
                telemetry_handler.update_telemetry("resultInfo.aiSummaryReport", brief_summary)

                try:
                    # Set a flag to track if we should try the fallback approach
                    pr_creation_success = False
                    pr_url = ""  # Initialize pr_url

                    # Try to create the PR using the GitHub CLI
                    log("Attempting to create a pull request...")
                    pr_url = github_ops.create_pr(pr_title, updated_pr_body, remediation_id, config.BASE_BRANCH)

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

                        # Add labels to the PR (non-critical — don't fail the run)
                        if pr_number:
                            labels_to_add = [f"smartfix-id:{remediation_id}"]
                            if label_name:
                                labels_to_add.append(label_name)
                            try:
                                github_ops.add_labels_to_pr(pr_number, labels_to_add)
                            except Exception as label_err:
                                log(f"Failed to add label to PR #{pr_number}: {label_err}", is_warning=True)

                        # Assign CODEOWNERS reviewers (non-critical — don't fail the run)
                        if pr_number:
                            try:
                                changed_files = github_ops.get_pr_changed_files(pr_number)
                                reviewers = get_reviewers_for_files(changed_files, config.REPO_ROOT)
                                if reviewers:
                                    github_ops.add_reviewers_to_pr(pr_number, reviewers)
                                else:
                                    debug_log("No CODEOWNERS reviewers found for changed files")
                            except Exception as reviewer_err:
                                log(f"Failed to assign CODEOWNERS reviewers to PR #{pr_number}: {reviewer_err}", is_warning=True)

                        # Notify the Remediation backend service about the PR
                        if pr_number is None:
                            log(f"Could not determine PR number from URL '{pr_url}' — skipping backend notification.", is_warning=True)
                        else:
                            remediation_notified = contrast_api.notify_remediation_pr_opened_org(
                                remediation_id=remediation_id,
                                pr_number=pr_number,
                                pr_url=pr_url,
                                contrast_provided_llm=config.CODING_AGENT == CodingAgents.SMARTFIX.name and config.USE_CONTRAST_LLM,
                                contrast_host=config.CONTRAST_HOST,
                                contrast_org_id=config.CONTRAST_ORG_ID,
                                contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                                contrast_api_key=config.CONTRAST_API_KEY
                            )
                            if remediation_notified:
                                log(f"Successfully notified Remediation service about PR for remediation {remediation_id}.")
                            else:
                                log(f"Failed to notify Remediation service about PR for remediation {remediation_id}.", is_warning=True)
                    else:
                        # This case should ideally be handled by create_pr exiting or returning empty
                        # and then the logic below for SKIP_PR_ON_FAILURE would trigger.
                        # However, if create_pr somehow returns without a URL but doesn't cause an exit:
                        log("PR creation did not return a URL. Assuming failure.")

                    telemetry_handler.update_telemetry("resultInfo.prCreated", pr_creation_success)

                    pr_metric_outcome = "success" if pr_creation_success else "failure"
                    smartfix_metrics.record_pr_attempt(
                        outcome=pr_metric_outcome,
                        rule_name=vulnerability.rule_name,
                        coding_agent=config.CODING_AGENT.lower(),
                        mode=mode,
                    )

                    if not pr_creation_success:
                        log("\n--- PR creation failed ---")
                        _op_outcome = "pr_failed"
                        error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)

                    _op_pr_created = True
                    _op_pr_url = pr_url
                    _op_outcome = "success"
                    prs_created_count[0] += 1

                    processed_one = True  # Mark that we successfully processed one
                    log(f"\n--- Successfully processed vulnerability {vuln_uuid}. Continuing to look for next vulnerability... ---")
                except Exception as e:
                    log(f"Error creating PR: {e}")
                    log("\n--- PR creation failed ---")
                    error_exit(remediation_id, FailureCategory.GENERATE_PR_FAILURE.value)

                contrast_api.send_telemetry_data_org(
                    remediation_id=remediation_id,
                    telemetry_data=telemetry_handler.get_telemetry_data(),
                    contrast_host=config.CONTRAST_HOST,
                    contrast_org_id=config.CONTRAST_ORG_ID,
                    contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                    contrast_api_key=config.CONTRAST_API_KEY
                )

            except TokenBalanceExhaustedError:
                # No notify_remediation_failed_org on this path: HTTP 402 is a
                # clean stop, not a failure. The remediation will be picked up
                # by a later scheduled run when balance is replenished.
                log(
                    "SmartFix token balance exhausted (HTTP 402). Stopping this run; "
                    "subsequent scheduled runs will resume when balance is replenished."
                )
                break
            except BaseException:
                raise
            finally:
                lang = (telemetry_handler.get_telemetry_data().get("appInfo") or {}).get("programmingLanguage")
                if lang:
                    op_span.set_attribute("contrast.finding.language", lang)
                op_span.set_attribute("contrast.finding.severity", vulnerability.severity.value)
                op_span.set_attribute("contrast.smartfix.fix_applied", _op_fix_applied)
                op_span.set_attribute("contrast.smartfix.files_modified", _op_files_modified)
                op_span.set_attribute("contrast.smartfix.pr_created", _op_pr_created)
                if _op_pr_url:
                    op_span.set_attribute("contrast.smartfix.pr_url", _op_pr_url)
                _total_in, _total_out = smartfix_metrics.get_vuln_token_totals()
                op_span.set_attribute("contrast.smartfix.total_input_tokens", _total_in)
                op_span.set_attribute("contrast.smartfix.total_output_tokens", _total_out)
                _severity = vulnerability.severity.value if vulnerability.severity else None
                smartfix_metrics.record_vulnerability_duration(
                    elapsed_s=time.monotonic() - _op_fix_start,
                    outcome=_op_outcome,
                    rule_name=vulnerability.rule_name,
                    language=lang or "unknown",
                    source="runtime",
                    severity=_severity,
                    mode=mode,
                )

    # Calculate total runtime
    end_time = datetime.now()
    total_runtime = end_time - start_time

    if not processed_one:
        log("\n--- No vulnerabilities were processed in this run. ---")
    else:
        log("\n--- Finished processing vulnerabilities. At least one vulnerability was handled in this run. ---")

    log(f"\n--- Script finished (total runtime: {total_runtime}) ---")

    cleanup_event_loop()


if __name__ == "__main__":
    main()

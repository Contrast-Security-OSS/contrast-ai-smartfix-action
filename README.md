# Contrast AI SmartFix \- User Documentation

## Legal Disclaimer

When you use Contrast AI SmartFix, you agree that your code and other data will be submitted to an LLM of your choice.  Both the submission of data to the LLM and the output generated by the LLM will be subject to the terms of service of that LLM.   Use of Contrast AI SmartFix is entirely at your own risk.

## Introduction

Welcome to Contrast AI SmartFix\! SmartFix is an AI-powered agent that automatically generates code fixes for vulnerabilities identified by Contrast Assess. It integrates into your developer workflow via GitHub Actions, creating Pull Requests (PRs) with proposed remediations.

**Key Benefits:**

* **Automated Remediation:** Reduces the manual effort and time required to fix vulnerabilities.  
* **Developer-Focused:** Delivers fixes as PRs directly in your GitHub repository, fitting naturally into existing workflows.  
* **Runtime Context:** Leverages Contrast Assess's runtime analysis (IAST) to provide more accurate and relevant fixes.  

## Getting Started

### Prerequisites

* **Contrast Assess:** You need an active Contrast Assess deployment identifying vulnerabilities in your application.  
* **GitHub:** Your project must be hosted on GitHub and use GitHub Actions.  In the GitHub repository's Settings, enable the Actions > General > Workflow Permissions checkbox for "Allow GitHub Actions to create and approve pull requests".
* **Contrast API Credentials:** You will need your Contrast Host, Organization ID, Application ID, Authorization Key, and API Key.
* **GitHub Token Permissions:** The GitHub token must have `contents: write` and `pull-requests: write` permissions. These permissions must be explicitly set in your workflow file.  Note, SmartFix uses the internal GitHub token for Actions; you do not need to create a Personal Access Token (PAT).
* **LLM Access:** Ensure that you have access to one of our recommended LLMs for use with SmartFix.  If using an AWS Bedrock model, please see Amazon's User Guide on [model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access-modify.html).

### Installation and Configuration

SmartFix is configured as a GitHub Action. Add a workflow file (e.g., `.github/workflows/smartfix.yml`) to your repository following the below example.  A full workflow example is also available at [https://github.com/Contrast-Security-OSS/contrast-ai-smartfix-action/blob/main/contrast-ai-smartfix.yml.template](https://github.com/Contrast-Security-OSS/contrast-ai-smartfix-action/blob/main/contrast-ai-smartfix.yml.template):

```
name: Contrast AI SmartFix

on:
  pull_request:
    types:
      - closed
  schedule:
    - cron: '0 0 * * *' # Runs daily at midnight UTC, adjust as needed
  workflow_dispatch: # Allows manual triggering

permissions:
  contents: write
  pull-requests: write

jobs:
  generate_fixes:
    name: Generate Fixes
    runs-on: ubuntu-latest
    if: github.event_name == 'workflow_dispatch' || github.event_name == 'schedule'
    steps:
      # For Claude via AWS Bedrock, please include an additional setup step for configuring AWS credentials
      # This step can be omitted if using another LLM provider.
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-session-token: ${{ secrets.AWS_SESSION_TOKEN }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          
      - name: Run Contrast AI SmartFix - Generate Fixes Action
        uses: Contrast-Security-OSS/contrast-ai-smartfix-action@v1 # Replace with the latest version
        with:
          # Contrast Configuration
          contrast_host: ${{ vars.CONTRAST_HOST }} # The host name of your Contrast SaaS instance, e.g. 'app.contrastsecurity.com'
          contrast_org_id: ${{ vars.CONTRAST_ORG_ID }} # The UUID of your Contrast organization
          contrast_app_id: ${{ vars.CONTRAST_APP_ID }} # The UUID that is specific to the application in this repository.
          contrast_authorization_key: ${{ secrets.CONTRAST_AUTHORIZATION_KEY }} 
          contrast_api_key: ${{ secrets.CONTRAST_API_KEY }}

          # GitHub Configuration
          github_token: ${{ secrets.GITHUB_TOKEN }} # Necessary for creating PRs.  This is the token GitHub auto-creates for actions and is not a Personal Access Token (PAT).
          base_branch: '${{ github.event.repository.default_branch }}' # This will default to your repo default branch (other common base branches are 'main', 'master' or 'develop')

          # Required Runtime Configuration
          build_command: 'mvn clean install' # Or the build command appropriate for your project.  SmartFix will use this command to ensure that its changes work correctly with your project.

          # LLM Configuration (Bring Your Own LLM)
          # Choose ONE LLM provider and configure its credentials
          # Recommended: Anthropic Claude Sonnet

          # Claude Via Direct Anthropic API
          # agent_model: 'anthropic/claude-3-7-sonnet-20250219' # Check LiteLLM docs for exact model string
          # anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}

          # Claude Via AWS Bedrock
          # Setup AWS credentials in the earlier "Configure AWS Credentials" step.
          agent_model: 'bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0' # Example for Claude Sonnet on Bedrock

          # Experimental: Google Gemini Pro
          # agent_model: 'gemini/gemini-2.5-pro-preview-05-06' # Check LiteLLM docs for exact model string
          # gemini_api_key: ${{ secrets.GEMINI_API_KEY }}

          # Other Optional Inputs (see action.yml for defaults and more options)
          # formatting_command: 'mvn spotless:apply' # Or the command appropriate for your project to correct the formatting of SmartFix's changes.  This ensures that SmartFix follows your coding standards.
          # max_open_prs: 5 # This is the maximum limit for the number of PRs that SmartFix will have open at single time

  handle_pr_merge:
    name: Handle PR Merge
    runs-on: ubuntu-latest
    if: github.event.pull_request.merged == true && contains(github.event.pull_request.head.ref, 'smartfix/remediation-')
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Notify Contrast on PR Merge
        uses: Contrast-Security-OSS/contrast-ai-smartfix-action@v1 # Replace with the latest version
        with:
          run_task: merge 
          # --- GitHub Token ---
          github_token: ${{ secrets.GITHUB_TOKEN }}
          # --- Contrast API Credentials ---
          contrast_host: ${{ vars.CONTRAST_HOST }}
          contrast_org_id: ${{ vars.CONTRAST_ORG_ID }}
          contrast_app_id: ${{ vars.CONTRAST_APP_ID }}
          contrast_authorization_key: ${{ secrets.CONTRAST_AUTHORIZATION_KEY }}
          contrast_api_key: ${{ secrets.CONTRAST_API_KEY }}
        env: 
          GITHUB_EVENT_PATH: ${{ github.event_path }}
  
  handle_pr_closed:
    name: Handle PR Close
    runs-on: ubuntu-latest
    if: github.event.pull_request.merged == false && contains(github.event.pull_request.head.ref, 'smartfix/remediation-')
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Notify Contrast on PR Closed
        uses: Contrast-Security-OSS/contrast-ai-smartfix-action@v1 # Replace with the latest version
        with:
          run_task: closed
          # --- GitHub Token ---
          github_token: ${{ secrets.GITHUB_TOKEN }}
          # --- Contrast API Credentials ---
          contrast_host: ${{ vars.CONTRAST_HOST }}
          contrast_org_id: ${{ vars.CONTRAST_ORG_ID }}
          contrast_app_id: ${{ vars.CONTRAST_APP_ID }}
          contrast_authorization_key: ${{ secrets.CONTRAST_AUTHORIZATION_KEY }}
          contrast_api_key: ${{ secrets.CONTRAST_API_KEY }}
        env: 
          GITHUB_EVENT_PATH: ${{ github.event_path }}
```

**Important:**

* Store all sensitive values (API keys, tokens) as GitHub Secrets in your repository or Github organization settings.  
* Replace `v1` with the specific version of the SmartFix GitHub Action you intend to use.  
* The `contrast_app_id` must correspond to the Contrast Application ID for the code in the repository where this action runs.  To find the app ID, visit the application page in the Contrast web UI, then use the last UUID in the URL (immediately after `/applications/`) as the app ID value.
* The `build_command` configured for `generate_fixes` job must be an appropriate build command for your project and is required for the proper functioning of SmartFix.  A `build_command` that runs your project's unit tests would be doubly useful as it would enable SmartFix to attempt to correct any changes that break your project's tests.  Please remember to do any additional setup for your `build_command` (such as library installation) in the `generate_fixes` job as a new step preceeding the `Run Contrast AI SmartFix - Generate Fixes Action` step.  For details about the libraries that come pre-installed with Github's Ubuntu runner, please visit https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md.  For details about GitHub's Windows runner, please visit https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md.
* The optional `formatting_command` will be run after SmartFix makes code changes to resolve the vulnerability and prior to any subsequent `build_command` invocations.  We recommend supplying a `formatting_command` to fix code style issues in your project as it is an easy way to correct a common class of build-breaking problems.
* **Suggestion:** Setup an API-only service user named “Contrast AI SmartFix” in your Organization Settings in your Contrast SaaS instance.  At a minimum, it should have the “View Organization” permission and “Edit Application” permission for this application.  This service user’s `contrast_authorization_key` value and the Organization’s `contrast_api_key` value should be used in the workflow.

### Supported LLMs (Bring Your Own LLM \- BYOLLM)

For the Early Access release, SmartFix uses a "Bring Your Own LLM" (BYOLLM) model. You provide the credentials for your preferred LLM provider.

* **Recommended:** **Anthropic Claude Sonnet (e.g., Claude 3.7 Sonnet via AWS Bedrock or direct Anthropic API)**. This model has been extensively tested.  
  * Option 1 - Direct Anthropic API:
    * Set `agent_model` to the appropriate model string for Anthropic (e.g. `anthropic/claude-3-7-sonnet-20250219`).
    * Provide your `anthropic_api_key`.
  * Option 2 - AWS Bedrock:
    * Set `agent_model` to the appropriate model string (e.g., `bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0`).  
    * In order for the action to an AWS Bedrock LLM, you need to provide AWS credentials. We recommend using [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) to configure your credentials for a job.  

* **Experimental:** **Google Gemini Pro (e.g., Gemini 2.5 Pro)**. Preliminary testing shows good results.  
  * Set `agent_model` to the appropriate model string (e.g., `gemini/gemini-2.5-pro-preview-05-06`).  
  * Provide your `gemini_api_key`.  
* **Not Recommended:** OpenAI GPT models (e.g., gpt-4, gpt-4.1, o1, o3, etc) are **not recommended** at this time, as they have shown issues following instructions within the SmartFix agent.

Refer to the `action.yml` file within the SmartFix GitHub Action repository and LiteLLM documentation for specific `agent_model` strings and required credentials for other models/providers.  The LiteLLM documentation can be found at https://docs.litellm.ai/docs/providers/.

### Agent Model values

Here are several recommended `agent_model` values:

* `bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0`
* `anthropic/claude-3-7-sonnet-20250219`
* `gemini/gemini-2.5-pro-preview-05-06`

### Supported Languages

* **Java, .NET, Go, Python, Node:** Java applications have received the most testing so far, but we have also had good results for .NET, Go, Python, and Node projects.
* **Other Languages:** While it might work for other languages (such as Ruby, and PHP), comprehensive testing is in progress. Use with caution for non-Java projects.

### Supported GitHub Runners

* **Ubuntu, Windows:** The Windows and Ubuntu GitHub runners have both been tested and work well for the SmartFix action.
* **MacOS, and Self-hosted:** No matter the runner you choose, please ensure that your `smartfix.yml` workflow file installs the necessary tools and sets up any PATH or other environmental variables so that your project's build and formatting commands can run as planned.  

Note: the SmartFix action's setup steps rely on the bash shell.  Please ensure that your self-hosted runner has a bash shell available and on the PATH.  For Windows runners, SmartFix will use the Git Bash shell.

### Supported Vulnerabilities

SmartFix focuses on remediating:

* **CRITICAL** and **HIGH** severity vulnerabilities identified by Contrast Assess.  
* **Exclusions:**  
  * Cross-Site Request Forgery (CSRF) is currently excluded due to the complexity of fixes often requiring API changes.  
  * Other specific vulnerability types may be excluded based on ongoing testing by Contrast Labs.

## How it Works

1. **Scheduled Trigger:** The GitHub Action runs on a defined schedule (e.g., daily) or can be manually triggered.  
2. **Configuration Validation:** The action validates your Contrast credentials and other configuration values to ensure they are valid.  
3. **Vulnerability Request:** The SmartFix agent in the action calls the Contrast backend API to request a vulnerability to fix.  
4. **Prioritization:** The backend API prioritizes eligible vulnerabilities based on severity.  
5. **LLM Interaction:** The agent uses your configured LLM (BYOLLM) to:  
   * Access the relevant code in your repository.  
   * Analyze the vulnerability and surrounding code.  
   * Generate a code fix.  
6. **Pull Request Generation:** The agent creates a Pull Request (PR) against your specified `base_branch` (e.g., `main`).  
   * **PR Title:** Clear and descriptive.  
   * **PR Description:** Explains the vulnerability, links to the Contrast Assess trace, outlines the fix strategy, and prompts for feedback if the PR is rejected.  
7. **Status Update:** The agent notifies the backend API about the PR creation as well as when the PR is either closed or merged.  
8. **Looping:** Once SmartFix has finished attempting to fix a vulnerability without an exception, it will request another vulnerability to resolve from the Contrast backend.  It will continue looping in this manner until it reaches one of its ending condition states, detailed below.
9. **Throttling:** The `max_open_prs` input (default: 5\) limits the number of concurrent open PRs SmartFix will create to avoid overwhelming developers.
10. **Ending Conditions:** SmartFix has several conditions that will make it stop a workflow run:
   * If the Contrast backend reports to SmartFix that there are no more vulnerabilities of the specified severity levels to fix, SmartFix will end its workflow run.
   * If SmartFix sees that it has reached the configured `max_open_prs` number of concurrently open SmartFix PRs, it will end its workflow run.
   * If SmartFix has reached its internal time limit of 3 hours of processing time for some reason, it will stop the workflow run instead of requesting a new vulnerability to resolve.
   * If SmartFix encounters an exception of some kind, it will stop the workflow run.
11. **Exceptions:** Sometimes things go wrong.  When SmartFix cannot generate a fix for the vulnerability, it will log the reason why, try to clean up the Github feature branches that have been made for that vulnerability, and exit the workflow early.
12. **Guardrails:** SmartFix has several configurable and internal guardrails:
   * *Time limit* - SmartFix has an internal time limit of 3 hours.  If it goes over 3 hours of processing time, it will not request another vulnerability to resolve.
   * `max_open_prs` - SmartFix offers this configurable value to control the maximum number concurrently open SmartFix PRs
   * `max_qa_attempts` - Once SmartFix creates a fix for a vulnerability, it will attempt to resolve any problems building the modified code.  `max_qa_attempts` controls how many iterations of the build-adjust-repeat loop that SmartFix will attempt.  `max_qa_attempts` has a default of 6, but has an internal hard-limit of 10.
   * `max_events_per_agent` - During the processing of a single vulnerability, SmartFix will use several AI agents.  Each agent operates as a sequence of events where an event may be some kind of data processing or tool usage.  `max_events_per_agent` is the maximum number of events each agent may use and provides a safeguard against runaway agent processing.  Its default value is 120, it has an internal hard-minimum of 10, and a hard-maximum of 500.

## Key Features

* **Bring Your Own LLM (BYOLLM):** Flexibility to use your preferred LLM provider and model.  
* **Configurable PR Throttling:** Control the volume of automated PRs using `max_open_prs`.  
* **Build Command Integration:** You must provide a `build_command` to allow the agent to ensure changes can build. Ideally, this command will run the tests as well so the agent can ensure it doesn't break existing tests.  
* **Code Formatting:** If your build requires formatting, you can provide a `formatting_command` to ensure generated code adheres to your project's style. This will be run before attempting to run the build.  
* **Debug Mode:** Enable `debug_mode: 'true'` for verbose logging in the GitHub Action output.

## Configuration Inputs

The following are key inputs for the GitHub Action. Refer to the `action.yml` in the SmartFix GitHub Action repository for a complete list and default values.

| Input | Description | Required | Default |
| :---- | :---- | :---- | :---- |
| `github_token` | GitHub token for PR operations. | Yes |  |
| `base_branch` | Base branch for PRs. | No | `${{ github.event.repository.default_branch }}` |
| `contrast_host` | Contrast Security API host. | Yes |  |
| `contrast_org_id` | Contrast Organization ID. | Yes |  |
| `contrast_app_id` | Contrast Application ID for the repository. | Yes |  |
| `contrast_authorization_key` | Contrast Authorization Key. | Yes |  |
| `contrast_api_key` | Contrast API Key. | Yes |  |
| `agent_model` | LLM model to use (e.g., `bedrock/anthropic.claude-3-sonnet-20240229-v1:0`). | No | `bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0` |
| `anthropic_api_key` | Anthropic API key (if using direct Anthropic API). | No |  |
| `gemini_api_key` | Gemini API key (if using Gemini). | No |  |
| `build_command` | Command to build the application (for QA). | Yes, for generating fixes |  |
| `formatting_command` | Command to format code. | No |  |
| `max_open_prs` | Maximum number of open PRs SmartFix can create. | No | `5` |
| `debug_mode` | Enable verbose logging. | No | `false` |
| `skip_qa_review` | Skip the QA review step (not recommended). | No | `false` |
| `skip_writing_security_test` | Skip attempting to write a security test for the fix. | No | `false` |
| `enable_full_telemetry` | Control how much telemetry data is sent back to Contrast. When set to 'true' (default), sends complete log files and build commands. When 'false', sensitive build commands and full logs are omitted. | No | `true` |

## Telemetry

SmartFix collects telemetry data to help improve the service and diagnose issues. This data includes:

* Vulnerability information (IDs and rules)
* Application metadata (programming language, frameworks)
* Configuration settings (sanitized build and formatting commands)
* Result information (PR creation status, files modified)
* Full log output

### Telemetry Configuration

* The telemetry behavior is determined by the `enable_full_telemetry` setting:
  * When `enable_full_telemetry: 'true'` (default): Sends complete logs and all configuration data
  * When `enable_full_telemetry: 'false'`: Omits both log data and sensitive build commands

### Data Handling

* All telemetry data is handled according to Contrast Security's privacy policies.

## Troubleshooting

* **Invalid Credentials:** If the action fails with errors related to Contrast authentication, double-check your `contrast_host`, `contrast_org_id`, `contrast_app_id`, `contrast_authorization_key`, and `contrast_api_key` secrets and ensure they are correctly passed to the action.  
* **LLM Errors:**  
  * Ensure the `agent_model` string is correct for your chosen provider and model.  
  * Verify that the necessary API keys/credentials for your LLM provider (`gemini_api_key`, AWS credentials, etc.) are correctly configured as GitHub Secrets and passed to the action.  
  * Check the GitHub Action logs for specific error messages from the LLM or the SmartFix agent.  
* **PR Creation Failures:**  
  * Ensure the `github_token` has the necessary permissions to create PRs in the repository.  
  * Check for branch protection rules that might prevent PR creation.  
* **No Fixes Generated:**  
  * Confirm there are eligible CRITICAL or HIGH severity vulnerabilities in Contrast Assess for the configured `contrast_app_id`. SmartFix only attempts to fix vulnerabilities that are in the REPORTED state.  
  * Check the `max_open_prs` limit; if the number of PRs SmartFix has created that are still open matches this limit, no new PRs will be created.  
  * Review the GitHub Action logs for messages indicating why vulnerabilities might have been skipped.  
* **Incorrect Fixes:** The AI-generated fixes should **always** be reviewed carefully. If a fix is incorrect or incomplete:  
  * Reject the PR.

## Best Practices & Recommendations

* **Ensure the `build_command` Runs the Tests:** This allows SmartFix to catch and fix any tests that may fail due to its changes. It also allows it to run the security tests it creates, if that option is enabled.  
* **Review PRs Thoroughly:** Always carefully review the code changes proposed by SmartFix before merging.  
* **Monitor Action Runs:** Regularly check the GitHub Action logs for successful runs and any reported issues.  
* **Use Recommended LLMs:** For the best experience, Contrast recommends using the Anthropic Claude Sonnet 3.7 model.

## FAQ

* **Q: Can I use SmartFix if I don't use Contrast Assess?**  
  * A: No, SmartFix relies on vulnerability data from Contrast Assess. In the future we plan to expand to include more.  
* **Q: How often does SmartFix run?**  
  * A: This is determined by the `schedule` trigger in your GitHub Actions workflow file. You can customize it.  
* **Q: What happens if the AI cannot generate a fix?**  
  * A: The agent will log this, and no PR will be created for that specific vulnerability attempt. It will retry on a future run.  
* **Q: Can SmartFix fix multiple vulnerabilities in one PR?**  
  * A: No, for the Early Access release, each PR addresses a single vulnerability.  
* **Q: Will SmartFix add new library dependencies?**  
  * A: Generally, SmartFix aims to use existing libraries and frameworks. We have instructed it not to make major architectural changes or add new dependencies.

---

For further assistance or to provide feedback on SmartFix, please contact your Contrast Security representative.

# Contrast LLM Early Access - SmartFix Integration

## Legal Disclaimer

When you use Contrast AI SmartFix with Contrast LLM, you agree that your code and other data will be submitted to Contrast's managed LLM service. All data processing and AI model usage is governed by your existing Contrast Security service agreement and data processing terms.

## Overview

**Contrast LLM** is a secure, sandboxed, Contrast-hosted LLM that the SmartFix coding agent can use.  It uses your existing Contrast API keys so there is no additional LLM configuration required.

**Important**: Contrast LLM is only available with the SmartFix Coding Agent. It does not work with GitHub Copilot or Claude Code agent integrations, which use their respective external services.

### Key Benefits

- **Minimal LLM Configuration**: Uses existing Contrast API keys. No additional LLM provider configuration required
- **Free During Beta**: Contrast absorbs all LLM costs during early access program
- **Enterprise-Grade Security**: All AI processing occurs within Contrast's secure infrastructure using a sandboxed LLM that doesn't further train on your Contrast data
- **Managed Scaling**: Automatic handling of rate limits, retries, and load balancing
- **Cost Transparency**: Built-in credit tracking and usage monitoring
- **Seamless Integration**: Works out-of-the-box with existing SmartFix workflows

## Early Access Program

Contrast LLM is available as a **free early access beta** to help customers evaluate SmartFix without LLM setup complexity.

### Program Details
- **Cost**: **Free to customers** during beta period
- **Duration**: 6-week evaluation period
- **Credits**: 50 credits per organization to start.  A credit represents an opened PR, i.e. a complete remediation attempt.
- **Support**: Dedicated support throughout the evaluation period

### How to Join
Contact your Contrast representative or Customer Success Manager to:
- Confirm eligibility for the early access program
- Schedule onboarding and setup assistance
- Plan feedback sessions to optimize your experience

### What We Ask
To ensure a successful evaluation, participants are expected to:
- Actively test SmartFix with Contrast LLM during the 6-week period
- Provide feedback on the experience and credit usage patterns
- Participate in brief check-in meetings to address any issues

## Quick Start

To use Contrast LLM with the SmartFix Coding Agent, simply set one configuration parameter in the SmartFix action's YAML file (likely `.github/workflows/smartfix.yml`):

```yaml
- name: Run Contrast AI SmartFix - Generate Fixes Action
  uses: Contrast-Security-OSS/contrast-ai-smartfix-action@v1
  with:
    # Enable Contrast LLM (replaces all BYOLLM configuration)
    use_contrast_llm: true # <--- Set this config value

    # Standard Contrast configuration (unchanged)
    contrast_host: ${{ vars.CONTRAST_HOST }}
    contrast_org_id: ${{ vars.CONTRAST_ORG_ID }}
    contrast_app_id: ${{ vars.CONTRAST_APP_ID }}
    contrast_authorization_key: ${{ secrets.CONTRAST_AUTHORIZATION_KEY }}
    contrast_api_key: ${{ secrets.CONTRAST_API_KEY }}

    # GitHub and build configuration (unchanged)
    github_token: ${{ secrets.GITHUB_TOKEN }}
    build_command: 'mvn clean install'
    # ... other standard settings
```

### Migration from BYOLLM

If you're currently using the SmartFix Coding Agent with BYOLLM configuration, migrating to Contrast LLM requires only these changes to the SmartFix action's YAML file (likely `.github/workflows/smartfix.yml`):

**Remove these BYOLLM parameters:**
- `agent_model`
- `anthropic_api_key`
- `aws_bearer_token_bedrock`
- `aws_region`
- `gemini_api_key`
- Any AWS credential configuration steps

**Add this single parameter:**
- `use_contrast_llm: true`

### Mixed Configuration Support

**Key Point**: The same customer can use both Contrast LLM and BYOLLM simultaneously across different repositories:

- **Repo 1**: Configured with Contrast LLM → consumes credits
- **Repo 2**: Configured with BYOLLM → does NOT consume credits

This flexibility allows customers to gradually migrate or use different configurations based on repository requirements.

## Configuration Reference

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `use_contrast_llm` | Enable Contrast LLM service | `true` |

### Standard Contrast Parameters (Unchanged)

All existing Contrast API parameters remain the same:
- `contrast_host`
- `contrast_org_id`
- `contrast_app_id`
- `contrast_authorization_key`
- `contrast_api_key`

## Complete Workflow Example

```yaml
name: Contrast AI SmartFix (Contrast LLM)

on:
  pull_request:
    types: [closed]
  schedule:
    - cron: '0 0 * * *' # Daily at midnight UTC
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write
  issues: write

jobs:
  generate_fixes:
    name: Generate Fixes
    runs-on: ubuntu-latest
    if: github.event_name == 'workflow_dispatch' || github.event_name == 'schedule'
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Run Contrast AI SmartFix - Generate Fixes Action
        uses: Contrast-Security-OSS/contrast-ai-smartfix-action@v1
        with:
          # --- Contrast LLM Configuration ---
          use_contrast_llm: true

          # --- Standard Configuration ---
          max_open_prs: 5
          base_branch: main
          build_command: 'mvn clean test'
          max_qa_attempts: 6
          vulnerability_severities: '["CRITICAL","HIGH","MEDIUM"]'
          formatting_command: 'mvn spotless:apply'

          # --- GitHub Token ---
          github_token: ${{ secrets.GITHUB_TOKEN }}

          # --- Contrast API Credentials ---
          contrast_host: ${{ vars.CONTRAST_HOST }}
          contrast_org_id: ${{ vars.CONTRAST_ORG_ID }}
          contrast_app_id: ${{ vars.CONTRAST_APP_ID }}
          contrast_authorization_key: ${{ secrets.CONTRAST_AUTHORIZATION_KEY }}
          contrast_api_key: ${{ secrets.CONTRAST_API_KEY }}

          # --- Optional Configuration ---
          skip_writing_security_test: false
          debug_mode: ${{ vars.DEBUG_MODE || 'false' }}

  # PR handling jobs remain unchanged
  handle_pr_merge:
    name: Handle PR Merge
    runs-on: ubuntu-latest
    if: github.event.pull_request.merged == true && contains(join(github.event.pull_request.labels.*.name), 'contrast-vuln-id:VULN-')
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Notify Contrast on PR Merge
        uses: Contrast-Security-OSS/contrast-ai-smartfix-action@v1
        with:
          run_task: merge
          github_token: ${{ secrets.GITHUB_TOKEN }}
          contrast_host: ${{ vars.CONTRAST_HOST }}
          contrast_org_id: ${{ vars.CONTRAST_ORG_ID }}
          contrast_app_id: ${{ vars.CONTRAST_APP_ID }}
          contrast_authorization_key: ${{ secrets.CONTRAST_AUTHORIZATION_KEY }}
          contrast_api_key: ${{ secrets.CONTRAST_API_KEY }}
          skip_comments: ${{ vars.SKIP_COMMENTS || 'false' }}
          debug_mode: ${{ vars.DEBUG_MODE || 'false' }}
        env:
          GITHUB_EVENT_PATH: ${{ github.event_path }}

  handle_pr_closed:
    name: Handle PR Close
    runs-on: ubuntu-latest
    if: github.event.pull_request.merged == false && contains(join(github.event.pull_request.labels.*.name), 'contrast-vuln-id:VULN-')
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Notify Contrast on PR Closed
        uses: Contrast-Security-OSS/contrast-ai-smartfix-action@v1
        with:
          run_task: closed
          github_token: ${{ secrets.GITHUB_TOKEN }}
          contrast_host: ${{ vars.CONTRAST_HOST }}
          contrast_org_id: ${{ vars.CONTRAST_ORG_ID }}
          contrast_app_id: ${{ vars.CONTRAST_APP_ID }}
          contrast_authorization_key: ${{ secrets.CONTRAST_AUTHORIZATION_KEY }}
          contrast_api_key: ${{ secrets.CONTRAST_API_KEY }}
        env:
          GITHUB_EVENT_PATH: ${{ github.event_path }}
```

## Technical Architecture

### Supported Models
The service currently provides access to:
- **Anthropic Claude Sonnet 4.5**

### Data Security
- All code and vulnerability data remains within Contrast's secure infrastructure
- No data is shared with external LLM providers
- Processing occurs in SOC 2 Type II compliant environments
- Data is encrypted in transit and at rest

## Comparison: Contrast LLM vs BYOLLM

| Feature | Contrast LLM | BYOLLM |
|---------|--------------|---------|
| **Setup Complexity** | Single parameter | Multiple API keys, credentials |
| **Model Management** | Managed by Contrast | Customer managed |
| **Cost Tracking** | Built-in credit system | Customer's cloud billing |
| **Security** | Contrast infrastructure | Customer's cloud security |
| **Rate Limits** | Managed automatically | Customer configured |
| **Model Updates** | Automatic | Manual migration required |
| **Support** | Contrast support | Customer self-service |

## Troubleshooting

### Common Issues

**1. Credit Exhaustion**
```
Credits have been exhausted. Contact your CSM to request additional credits.
```
**Solution**: Contact your Customer Success Manager to request additional credits during the beta program.

**2. Service Unavailable**
```
Error: Contrast LLM service temporarily unavailable
```
**Solution**: The service will automatically retry. For persistent issues, check Contrast status page.

**3. Configuration Conflicts**
```
Warning: Both use_contrast_llm and agent_model specified
```
**Solution**: Remove BYOLLM parameters when using `use_contrast_llm: true`.

### Debug Information

Enable detailed logging with:
```yaml
debug_mode: true
```

This provides:
- Credit consumption details per PR generation
- Credit remaining after each operation
- Warning logs when credits are low (5 or fewer remaining)
- Error logs when credits exhausted
- Cost tracking per PR generation
- LLM proxy communication logs
- Model selection information
- Performance metrics

### Usage Tracking

Credit usage and SmartFix activity is automatically logged for your visibility:
- Credit consumption per PR generation
- Credit remaining after each operation
- Logs when credits are low / exhausted
- All activity visible in SmartFix debug logs

### Support

For Contrast LLM Early Access support:
1. **Technical Issues**: Include debug logs and workflow configuration
2. **Credit/Usage Questions**: Contact your Customer Success Manager
3. **Feature Requests**: Submit via normal Contrast support channels

## Migration Guide

### From Existing BYOLLM Configuration

**Step 1**: Backup your current workflow file

**Step 2**: Remove BYOLLM configuration
```yaml
# REMOVE these lines:
# agent_model: 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
# anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
# aws_bearer_token_bedrock: ${{ secrets.AWS_BEARER_TOKEN_BEDROCK }}
# aws_region: ${{ vars.AWS_REGION }}

# REMOVE this step entirely:
# - name: Configure AWS Credentials
#   uses: aws-actions/configure-aws-credentials@v4
#   with: ...
```

**Step 3**: Add Contrast LLM configuration
```yaml
# ADD this line:
use_contrast_llm: true
```

**Step 4**: Test with a single vulnerability to verify functionality

### Rollback Plan

To revert to BYOLLM, simply:
1. Set `use_contrast_llm: false`
2. Restore your original LLM provider configuration
3. Re-add any removed credential configuration steps

## Important Notes

### Closed PR Behavior
When you close a SmartFix-generated PR, the system may attempt to regenerate a fix for that vulnerability on the next scheduled run. This will consume additional credits.

To avoid unintended credit usage:
- Only close PRs you don't want SmartFix to retry
- Contact support if you need to permanently exclude specific vulnerabilities
- Monitor your credit usage if you frequently close PRs

We're actively working on enhanced controls for this behavior based on beta feedback.

## Early Access Limitations

- **Model Selection**: Limited to Contrast-managed models (currently Anthropic Claude Sonnet 4.5)
- **Custom Prompting**: Standard SmartFix prompts only
- **Regional Availability**: Initially available in US regions
- **Credit Limits**: Subject to early access allocation limits (50 credits initially)
- **Customer Limit**: Maximum 10 customers in beta program
- **Duration**: 6-week evaluation period per customer

## Data Usage and Privacy

During the early access beta, Contrast collects usage analytics to improve the service:
- Credit usage patterns to optimize allocation
- PR success rates to improve fix quality
- Vulnerability types and languages to enhance model performance
- General usage patterns to refine the user experience

All data collection follows your existing Contrast Security data processing agreement. No code content is used for training external models.

## Feedback and Support


Contact your Customer Success Manager or Contrast representative for beta program participation and feedback scheduling.

---

For complete SmartFix documentation, see the [SmartFix Coding Agent Guide](smartfix_coding_agent.md).
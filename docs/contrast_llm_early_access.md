# Contrast LLM Early Access - SmartFix Integration

## Legal Disclaimer

When you use Contrast AI SmartFix with Contrast LLM, you agree that your code and other data will be submitted to Contrast's managed LLM service. All data processing and AI model usage is governed by your existing Contrast Security service agreement and data processing terms.

## Overview

**Contrast LLM** is Contrast Security's managed Large Language Model service that provides seamless AI capabilities for the **SmartFix Coding Agent** without requiring customers to manage their own LLM infrastructure or API keys. This early access feature eliminates the complexity of "Bring Your Own LLM" (BYOLLM) configuration.

**Important**: Contrast LLM is only available with the SmartFix Coding Agent. It does not work with GitHub Copilot or Claude Code agent integrations, which use their respective external services.

### Key Benefits

- **Zero LLM Configuration**: No need to manage API keys, model endpoints, or provider credentials
- **Enterprise-Grade Security**: All AI processing occurs within Contrast's secure infrastructure
- **Managed Scaling**: Automatic handling of rate limits, retries, and load balancing
- **Cost Transparency**: Built-in credit tracking and usage monitoring
- **Seamless Integration**: Works out-of-the-box with existing SmartFix workflows

## Quick Start

To use Contrast LLM with the SmartFix Coding Agent, simply set one configuration parameter:

```yaml
- name: Run Contrast AI SmartFix - Generate Fixes Action
  uses: Contrast-Security-OSS/contrast-ai-smartfix-action@v1
  with:
    # Enable Contrast LLM (replaces all BYOLLM configuration)
    use_contrast_llm: true

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

If you're currently using the SmartFix Coding Agent with BYOLLM configuration, migrating to Contrast LLM requires only these changes:

**Remove these BYOLLM parameters:**
- `agent_model`
- `anthropic_api_key`
- `aws_bearer_token_bedrock`
- `aws_region`
- `gemini_api_key`
- Any AWS credential configuration steps

**Add this single parameter:**
- `use_contrast_llm: true`

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

## Credit Tracking and Usage Monitoring

Contrast LLM includes built-in usage tracking and credit management:

### Automatic Credit Tracking
- Each SmartFix remediation attempt consumes AI credits based on complexity
- Credit usage is automatically tracked per organization and application
- No separate billing or API key management required

### Usage Visibility
- Credit consumption appears in SmartFix telemetry and logs
- Integration with Contrast's existing usage reporting systems
- Per-vulnerability credit costs logged for transparency

### Credit Management
Your Contrast account manager can help configure:
- Credit allocation per organization
- Usage alerts and limits
- Monthly credit replenishment schedules

## Technical Architecture

### LLM Proxy Service
Contrast LLM uses an internal proxy service that:
- Manages authentication and authorization
- Handles model selection and optimization
- Provides automatic retry and error handling
- Ensures data security and privacy compliance

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
Error: LLM credit limit exceeded for organization
```
**Solution**: Contact your Contrast account manager to increase credit allocation.

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
- Credit consumption details
- LLM proxy communication logs
- Model selection information
- Performance metrics

### Support

For Contrast LLM Early Access support:
1. **Technical Issues**: Include debug logs and workflow configuration
2. **Credit/Usage Questions**: Contact your Contrast account manager
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

## Early Access Limitations

- **Model Selection**: Limited to Contrast-managed models
- **Custom Prompting**: Standard SmartFix prompts only
- **Regional Availability**: Initially available in US regions
- **Credit Limits**: Subject to early access allocation limits

## Feedback and Support

This is an early access feature. Please provide feedback on:
- Configuration simplicity
- Performance compared to BYOLLM
- Credit usage patterns
- Integration experience

Contact your Contrast representative or submit feedback through normal support channels.

---

For complete SmartFix documentation, see the [SmartFix Coding Agent Guide](smartfix_coding_agent.md).
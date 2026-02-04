# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Setup and Installation
- Install dependencies: `cd src && pip install -r requirements.txt`
- Install with lock file: `cd src && uv pip sync --system requirements.lock`
- Setup git hooks: `./setup-hooks.sh`

### Testing
- Run all tests: `./test/run_tests.sh`
- Run specific test file: `./test/run_tests.sh test_main.py`
- Run multiple test files: `./test/run_tests.sh test_main.py test_config.py`
- Run with coverage: `./test/run_tests.sh --coverage`
- Skip dependency install: `./test/run_tests.sh --skip-install`

### Linting
- Run linting: `./.git/hooks/pre-push` or `flake8 src/ test/`
- Fix trailing whitespace: `sed -i '' 's/[[:space:]]*$//' path/to/file.py`
- Max line length: 180 characters

## Code Architecture

This repository contains a GitHub Action that automatically generates code fixes for vulnerabilities identified by Contrast Assess. The action creates PRs with AI-generated vulnerability remediations.

### Entry Points

Three entry points based on GitHub event type (determined automatically in `action.yml`):
- `src/main.py`: Main fix generation flow (scheduled/manual triggers)
- `src/merge_handler.py`: Handles SmartFix PR merge events
- `src/closed_handler.py`: Handles SmartFix PR close events

### Domain-Driven Architecture (`src/smartfix/`)

The codebase follows domain-driven design under `src/smartfix/`:

**domains/agents/**: AI agent orchestration
- `smartfix_agent.py`: Main SmartFix agent implementation
- `agent_session.py`: Session management for agent runs
- `coding_agent.py`: Base coding agent abstraction
- `sub_agent_executor.py`: Sub-agent execution (QA, security tests)

**domains/workflow/**: Fix generation workflow
- `session_handler.py`: Processes agent session results, determines success/failure
- `build_runner.py`: Executes build commands, captures output
- `credit_tracking.py`: Tracks Contrast LLM credit usage
- `formatter.py`: Code formatting operations

**domains/vulnerability/**: Vulnerability data models
- `models.py`: Vulnerability dataclass and related types
- `context.py`: RemediationContext, BuildConfiguration, PromptConfiguration

**domains/scm/**: Source control operations
- `git_operations.py`: Git commands (branch, commit, push)
- `scm_operations.py`: SCM abstraction layer

**extensions/**: LLM integrations
- `smartfix_litellm.py`: LiteLLM integration for BYOLLM
- `smartfix_llm_agent.py`: Contrast LLM-specific agent

**shared/**: Shared enums and constants
- `coding_agents.py`: CodingAgents enum (SMARTFIX, GITHUB_COPILOT, CLAUDE_CODE)
- `llm_providers.py`: LLM provider constants
- `failure_categories.py`: FailureCategory enum for telemetry

### GitHub Integration (`src/github/`)

- `github_operations.py`: PR creation, branch management via GitHub API
- `external_coding_agent.py`: Integration with Copilot/Claude Code via GitHub Issues
- `agent_factory.py`: Factory for creating appropriate coding agent

### Core Modules (`src/`)

- `config.py`: Centralized configuration from environment variables
- `contrast_api.py`: Contrast Security API client (fetch vulnerabilities, send telemetry)
- `utils.py`: Logging utilities (`log`, `debug_log`, `error_exit`)
- `telemetry_handler.py`: OpenTelemetry instrumentation

### Workflow Summary

1. Fetch vulnerabilities from Contrast Assess API
2. Filter by severity and existing PRs
3. For each vulnerability:
   - Create feature branch
   - Run SmartFix agent (or delegate to Copilot/Claude Code)
   - Execute build command to validate fix
   - Run QA sub-agent for review
   - Create PR with fix details
4. Notify Contrast backend of PR status changes

## Development Principles

From `.github/copilot-instructions.md`:
- **Test-First**: Write tests before production code
- **YAGNI**: Don't build for imaginary future requirements
- **Complete Refactoring**: When touching code, update ALL callers
- **Clean Up**: Delete unused code, no duplicate files

## Process Notes

When starting work on a Jira ticket or bead linked to one, create a branch prefixed with the ticket ID first (e.g., `AIML-123-fix-description`). All commits should include the Jira ticket number.

## Jira

All tickets for this codebase go in the AIML project with the SmartFix component.

- Cloud ID: `35f55002-5211-4f07-ae86-25b46703fe59`
- Project: `AIML`
- Component: `{"components": [{"id": "18725"}]}` (SmartFix)

## Beads

When creating a bead for a Jira ticket:
- Prefix the title with the Jira issue ID (e.g., "AIML-430 - Fix expired trial handling")
- Set `--external-ref` to the Jira issue ID (e.g., `--external-ref "AIML-430"`)

## Related Codebases

- **aiml-services** (`../aiml-services`): Monorepo containing backend services including `aiml-remediation-api` which this action calls

**Important:** Always consult the aiml-services codebase to verify API behavior. Never assume how endpoints work - check the actual implementation.

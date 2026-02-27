# test/scripts

Scripts for manual and integration testing of `contrast-ai-smartfix-action` feature branches against real repos.

## smartfix-scenario-test.sh

Runs a full SmartFix scenario test against a target repository. Automates the process of pinning a feature branch, triggering a SmartFix run, and reviewing the generated PRs.

### Usage

```bash
./test/scripts/smartfix-scenario-test.sh \
  --branch AIML-493_add-medium-to-default-severities \
  --repo JacobMagesHaskinsContrast/employee-management \
  --workflow contrast-ai-smartfix-aws-smartfix.yml
```

### What it does

1. **Pin branch** — Updates the target repo's workflow file to use the feature branch via the GitHub API (no local checkout required)
2. **Close open SmartFix PRs** — Closes any existing SmartFix PRs (`smartfix/remediation-*`, `copilot/fix-*`, `claude/issue-*`) to ensure a clean run
3. **Wait for settle** — Polls until no workflow runs are active (avoids race conditions from the close events)
4. **Trigger dispatch** — Fires a `workflow_dispatch` event on the target workflow
5. **Poll until complete** — Polls every 30 seconds (up to 25 minutes) and prints the run URL immediately
6. **List new PRs** — Prints titles and URLs of SmartFix PRs opened after the run started
7. **Prompt for cleanup** — Press Enter to close new PRs and restore the workflow file; Ctrl+C to keep them

### Flags

| Flag | Description |
|---|---|
| `--branch` | Feature branch of `contrast-ai-smartfix-action` to test |
| `--repo` | Target test repo in `OWNER/REPO` format |
| `--workflow` | Workflow filename in the target repo |
| `--ref` | Override workflow file path (default: `.github/workflows/<WORKFLOW>`) |
| `--skip-cleanup` | Skip interactive cleanup; write state to `/tmp/smartfix-test-state.json` |

### Requirements

- `gh` CLI authenticated with access to both the `contrast-ai-smartfix-action` repo and the target test repo
- `jq`

---

## /smartfix-scenario-test Claude Code skill

The recommended way to run scenario tests when using Claude Code. Wraps the script above and adds an AI code review of each generated PR between steps 6 and 7.

```
/smartfix-scenario-test --branch BRANCH --repo OWNER/REPO --workflow WORKFLOW_FILE
```

After the run completes, Claude will:
- Read each new PR's description and diff
- Write a one-paragraph verdict on whether the fix addresses the stated vulnerability
- Prompt you to confirm cleanup (close PRs + restore workflow file)

The skill is defined in `.claude/commands/smartfix-scenario-test.md`.

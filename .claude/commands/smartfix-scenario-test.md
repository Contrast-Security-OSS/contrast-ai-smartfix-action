# SmartFix Scenario Test

Run a full SmartFix scenario test against a real test repo, then AI-review each generated PR to verify it addresses the stated vulnerability.

## Usage

```
/smartfix-scenario-test --branch BRANCH --repo OWNER/REPO --workflow WORKFLOW_FILE
```

**Arguments:**
- `--branch` — Feature branch of `contrast-ai-smartfix-action` to test (e.g. `AIML-493_add-medium-to-default-severities`)
- `--repo` — Target test repo in `OWNER/REPO` format (e.g. `JacobMagesHaskinsContrast/employee-management`)
- `--workflow` — Workflow filename in the target repo (e.g. `contrast-ai-smartfix-aws-smartfix.yml`)

## What This Skill Does

1. **Runs automation (steps 1–6)** via `test/scripts/smartfix-scenario-test.sh --skip-cleanup`, which:
   - Pins the test repo's workflow file to the feature branch
   - Closes any open SmartFix PRs
   - Waits for triggered runs to settle
   - Fires a `workflow_dispatch` trigger
   - Polls until the run completes (up to 25 min)
   - Lists newly generated PRs

2. **AI review** — For each new PR:
   - Reads the PR description (`gh pr view`)
   - Reads the code diff (`gh pr diff`)
   - Outputs a one-paragraph verdict: do the changes address the stated vulnerability?

3. **Cleanup** — Prompts to close the new PRs and restore the workflow file to its original ref.

## Instructions

Parse `$ARGUMENTS` to extract `--branch`, `--repo`, and `--workflow` values. All three are required — if any are missing, print the usage above and stop.

### Step 1: Run the automation script

```bash
./test/scripts/smartfix-scenario-test.sh \
  --branch <BRANCH> \
  --repo <REPO> \
  --workflow <WORKFLOW> \
  --skip-cleanup
```

This will take up to 25 minutes. Print output as it streams. When the script exits, continue to step 2.

### Step 2: Read state

```bash
cat /tmp/smartfix-test-state.json
```

This gives you: `repo`, `original_ref`, `workflow_path`, `branch`, `pr_numbers` (JSON array).

### Step 3: AI review each PR

For each PR number in `pr_numbers`:

```bash
gh pr view <NUMBER> --repo <REPO> --json title,body,url
gh pr diff <NUMBER> --repo <REPO>
```

Read both outputs, then write a **one-paragraph verdict**:

> **PR #N — [title]**: [URL]
> [One paragraph: Does the diff address the vulnerability described in the PR body? Be specific about what the change does and why it does or does not adequately fix the stated issue.]

If there are no new PRs, note that and explain the run may not have found matching vulnerabilities.

### Step 4: Cleanup

After all verdicts are printed, ask the user:

> "Ready to close the new PRs and restore the workflow file to `@<original_ref>`? (yes/no)"

If yes, run the cleanup:

```bash
# Close each new PR
gh pr close <NUMBER> --repo <REPO> --comment "Closed by /smartfix-scenario-test skill (post-test cleanup)"

# Restore workflow file (fetch current SHA, replace ref, commit back)
FILE_JSON=$(gh api "repos/<REPO>/contents/<WORKFLOW_PATH>")
CURRENT_SHA=$(echo "$FILE_JSON" | jq -r '.sha')
CURRENT_CONTENT=$(echo "$FILE_JSON" | jq -r '.content' | tr -d '\n' | base64 --decode)
RESTORED=$(echo "$CURRENT_CONTENT" | sed "s|uses: Contrast-Security-OSS/contrast-ai-smartfix-action@[A-Za-z0-9_./-]*|uses: Contrast-Security-OSS/contrast-ai-smartfix-action@<ORIGINAL_REF>|g")
RESTORED_B64=$(echo "$RESTORED" | base64 | tr -d '\n')
gh api --method PUT "repos/<REPO>/contents/<WORKFLOW_PATH>" \
  --field message="Restore workflow to @<ORIGINAL_REF>" \
  --field content="$RESTORED_B64" \
  --field sha="$CURRENT_SHA" > /dev/null
echo "✅ Workflow restored to @<ORIGINAL_REF>"
```

If no, confirm the PRs and workflow file are left as-is, and remind the user the workflow is still pinned to `@<BRANCH>`.

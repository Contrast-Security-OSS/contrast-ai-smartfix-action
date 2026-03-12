#!/usr/bin/env bash
# smartfix-scenario-test.sh — Run a SmartFix scenario test against a real repo.
#
# Usage:
#   ./test/scripts/smartfix-scenario-test.sh \
#     --branch AIML-493_add-medium-to-default-severities \
#     --repo JacobMagesHaskinsContrast/employee-management \
#     --workflow contrast-ai-smartfix-aws-smartfix.yml
#
# Steps:
#   1. Pin the workflow file in the target repo to the feature branch
#   2. Close all open SmartFix PRs in the target repo
#   3. Wait for any close-triggered workflow runs to settle
#   4. Trigger the SmartFix workflow via workflow_dispatch
#   5. Poll until the run completes (25-minute timeout)
#   6. Print newly opened PRs (opened after the run started)
#   7. Prompt to close those PRs and restore the workflow file
#
# Flags:
#   --skip-cleanup   Skip step 7 (interactive prompt); write state to
#                    /tmp/smartfix-test-state.json for later cleanup.
#                    Used by the /smartfix-scenario-test Claude Code skill.

set -euo pipefail

# ─── helpers ──────────────────────────────────────────────────────────────────

usage() {
  echo "Usage: $0 --branch BRANCH --repo OWNER/REPO --workflow WORKFLOW_FILE [--skip-cleanup]"
  echo ""
  echo "Options:"
  echo "  --branch        Feature branch of contrast-ai-smartfix-action to test"
  echo "  --repo          Target test repo (e.g. JacobMagesHaskinsContrast/employee-management)"
  echo "  --workflow      Workflow filename in the target repo (e.g. contrast-ai-smartfix.yml)"
  echo "  --ref           Workflow file path in repo (default: .github/workflows/WORKFLOW_FILE)"
  echo "  --skip-cleanup  Skip interactive cleanup; write state to /tmp/smartfix-test-state.json"
  exit 1
}

log()  { echo "$(date '+%H:%M:%S') $*"; }
info() { log "▶ $*"; }
ok()   { log "✅ $*"; }
warn() { log "⚠️  $*"; }

# ─── cleanup function (defined early so it can be called anywhere) ─────────────

ACTION_REPO="Contrast-Security-OSS/contrast-ai-smartfix-action"

do_cleanup() {
  local repo="$1"
  local pr_numbers="$2"
  local original_ref="$3"
  local workflow_path="$4"

  # Close new PRs
  local pr_count
  pr_count=$(echo "$pr_numbers" | jq 'length')
  if [[ "$pr_count" -gt 0 ]]; then
    info "Closing $pr_count new PR(s)..."
    echo "$pr_numbers" | jq -r '.[]' | while read -r pr_num; do
      gh pr close "$pr_num" --repo "$repo" \
        --comment "Closed by smartfix-scenario-test.sh (post-test cleanup)" > /dev/null
      info "  Closed PR #$pr_num"
    done
  fi

  # Restore workflow file to original ref
  info "Restoring workflow file to @$original_ref ..."

  local current_file_json current_sha current_content restored_content restored_b64
  if ! current_file_json=$(gh api "repos/$repo/contents/$workflow_path" 2>&1); then
    warn "Failed to fetch workflow file during cleanup: $current_file_json"
    return 1
  fi
  current_sha=$(echo "$current_file_json" | jq -r '.sha')
  current_content=$(echo "$current_file_json" | jq -r '.content' | tr -d '\n' | base64 --decode)
  restored_content=$(echo "$current_content" \
    | sed "s|uses: $ACTION_REPO@[A-Za-z0-9_./-]*|uses: $ACTION_REPO@$original_ref|g")
  restored_b64=$(echo "$restored_content" | base64 | tr -d '\n')

  local put_response
  if ! put_response=$(gh api --method PUT "repos/$repo/contents/$workflow_path" \
    --field message="Restore workflow to @$original_ref" \
    --field content="$restored_b64" \
    --field sha="$current_sha" 2>&1); then
    warn "Failed to restore workflow file to @$original_ref: $put_response"
    return 1
  fi

  ok "Workflow file restored to @$original_ref"
}

# ─── arg parsing ──────────────────────────────────────────────────────────────

BRANCH=""
REPO=""
WORKFLOW=""
WORKFLOW_PATH=""
SKIP_CLEANUP=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)        BRANCH="$2";         shift 2 ;;
    --repo)          REPO="$2";           shift 2 ;;
    --workflow)      WORKFLOW="$2";       shift 2 ;;
    --ref)           WORKFLOW_PATH="$2";  shift 2 ;;
    --skip-cleanup)  SKIP_CLEANUP=true;   shift   ;;
    -h|--help)       usage ;;
    *)               echo "Unknown option: $1"; usage ;;
  esac
done

[[ -z "$BRANCH" || -z "$REPO" || -z "$WORKFLOW" ]] && usage

if [[ ! "$REPO" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
  echo "Error: --repo must be in OWNER/REPO format (e.g. JacobMagesHaskinsContrast/employee-management)." >&2
  exit 1
fi
if [[ ! "$BRANCH" =~ ^[A-Za-z0-9._/\-]+$ ]]; then
  echo "Error: --branch contains invalid characters. Allowed: letters, digits, '.', '_', '-', '/'." >&2
  exit 1
fi
if [[ ! "$WORKFLOW" =~ ^[A-Za-z0-9._-]+\.y[a]?ml$ ]]; then
  echo "Error: --workflow must be a .yml or .yaml filename (e.g. contrast-ai-smartfix.yml)." >&2
  exit 1
fi

WORKFLOW_PATH="${WORKFLOW_PATH:-.github/workflows/$WORKFLOW}"
CLEANUP_STATE_FILE="/tmp/smartfix-test-state.json"
SETTLE_POLL_SECONDS=15
RUN_POLL_SECONDS=30
TIMEOUT_SECONDS=$((25 * 60))

info "SmartFix Scenario Test"
info "  Branch:   $BRANCH"
info "  Repo:     $REPO"
info "  Workflow: $WORKFLOW_PATH"
[[ "$SKIP_CLEANUP" == "true" ]] && info "  Mode:     --skip-cleanup (AI review mode)"
echo ""

# ─── step 1: pin workflow file to feature branch ──────────────────────────────

info "Step 1: Pinning workflow file to @$BRANCH ..."

if ! FILE_JSON=$(gh api "repos/$REPO/contents/$WORKFLOW_PATH" 2>&1); then
  warn "Failed to fetch workflow file: $FILE_JSON"
  exit 1
fi
FILE_SHA=$(echo "$FILE_JSON" | jq -r '.sha')
ORIGINAL_CONTENT=$(echo "$FILE_JSON" | jq -r '.content' | tr -d '\n' | base64 --decode)

# Extract the original ref from the first occurrence of uses: .../contrast-ai-smartfix-action@REF
ORIGINAL_REF=$(echo "$ORIGINAL_CONTENT" \
  | grep -oE "uses: $ACTION_REPO@[A-Za-z0-9_./-]+" \
  | head -1 \
  | sed "s|uses: $ACTION_REPO@||")

if [[ -z "$ORIGINAL_REF" ]]; then
  warn "No 'uses: $ACTION_REPO@<ref>' found in $WORKFLOW_PATH."
  warn "Ensure the workflow references the action. Exiting."
  exit 1
fi

info "  Original ref: @$ORIGINAL_REF"

PINNED_CONTENT=$(echo "$ORIGINAL_CONTENT" \
  | sed "s|uses: $ACTION_REPO@[A-Za-z0-9_./-]*|uses: $ACTION_REPO@$BRANCH|g")
PINNED_CONTENT_B64=$(echo "$PINNED_CONTENT" | base64 | tr -d '\n')

PIN_RESPONSE=""
if ! PIN_RESPONSE=$(gh api --method PUT "repos/$REPO/contents/$WORKFLOW_PATH" \
  --field message="Pin to branch $BRANCH" \
  --field content="$PINNED_CONTENT_B64" \
  --field sha="$FILE_SHA" 2>&1); then
  warn "Failed to pin workflow file to @$BRANCH: $PIN_RESPONSE"
  exit 1
fi

ok "Workflow file pinned to @$BRANCH (was @$ORIGINAL_REF)"

# ─── step 2: close open smartfix prs ──────────────────────────────────────────

info "Step 2: Closing open SmartFix PRs in $REPO ..."

SMARTFIX_BRANCH_RE="^(smartfix/remediation-|copilot/fix-|claude/issue-)"

OPEN_PRS=$(gh pr list \
  --repo "$REPO" \
  --state open \
  --limit 100 \
  --json number,title,headRefName \
  --jq ".[] | select(.headRefName | test(\"$SMARTFIX_BRANCH_RE\")) | \"\(.number)\t\(.title)\"" 2>/dev/null || true)

if [[ -z "$OPEN_PRS" ]]; then
  ok "No open SmartFix PRs found."
else
  while IFS=$'\t' read -r pr_num pr_title; do
    info "  Closing PR #$pr_num: $pr_title"
    gh pr close "$pr_num" --repo "$REPO" \
      --comment "Closed by smartfix-scenario-test.sh (pre-test cleanup)" > /dev/null
  done <<< "$OPEN_PRS"
  ok "Open SmartFix PRs closed."
fi

# ─── step 3: wait for close-triggered runs to settle ─────────────────────────

info "Step 3: Waiting for triggered workflow runs to settle ..."

wait_for_runs_to_settle() {
  local deadline=$(( $(date +%s) + 120 ))
  while true; do
    local active
    active=$(gh run list --repo "$REPO" --limit 20 \
      --json status \
      --jq '[.[] | select(.status == "queued" or .status == "in_progress" or .status == "waiting" or .status == "requested" or .status == "pending")] | length' \
      2>/dev/null || echo "0")

    if [[ "$active" -eq 0 ]]; then
      ok "No active workflow runs."
      return
    fi

    if [[ $(date +%s) -ge $deadline ]]; then
      warn "Timed out waiting for runs to settle ($active still active). Continuing anyway."
      return
    fi

    info "  $active active run(s), waiting ${SETTLE_POLL_SECONDS}s..."
    sleep "$SETTLE_POLL_SECONDS"
  done
}

wait_for_runs_to_settle

# ─── step 4: trigger workflow dispatch ───────────────────────────────────────

info "Step 4: Triggering workflow dispatch ..."

RUN_STARTED_AT=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

gh workflow run "$WORKFLOW" --repo "$REPO" > /dev/null
ok "Workflow dispatched at $RUN_STARTED_AT"

sleep 5  # Give GitHub a moment to register the run

# ─── step 5: poll until complete ─────────────────────────────────────────────

info "Step 5: Polling for run completion (timeout: $((TIMEOUT_SECONDS / 60)) min) ..."

DEADLINE=$(( $(date +%s) + TIMEOUT_SECONDS ))
RUN_ID=""
RUN_URL=""

# Wait for the newly dispatched run to appear — filter by creation timestamp to
# avoid picking up a concurrent run that predates the dispatch.
for _i in $(seq 1 10); do
  LATEST=$(gh run list --repo "$REPO" --workflow "$WORKFLOW" --limit 5 \
    --json databaseId,status,url,createdAt \
    --jq "[.[] | select(.createdAt >= \"$RUN_STARTED_AT\")] | .[0]" \
    2>/dev/null || echo "null")

  if [[ "$LATEST" != "null" && -n "$LATEST" ]]; then
    RUN_ID=$(echo "$LATEST" | jq -r '.databaseId')
    RUN_URL=$(echo "$LATEST" | jq -r '.url')
    break
  fi
  sleep 5
done

if [[ -z "$RUN_ID" ]]; then
  warn "Could not detect new workflow run. Check GitHub Actions manually."
  exit 1
fi

echo ""
info "Run URL: $RUN_URL"
echo ""

while true; do
  STATUS_RAW=$(gh run view "$RUN_ID" --repo "$REPO" --json status,conclusion \
    --jq '"\(.status)/\(.conclusion)"' 2>/dev/null || echo "unknown/unknown")

  RUN_STATUS="${STATUS_RAW%/*}"
  RUN_CONCLUSION="${STATUS_RAW#*/}"

  case "$RUN_STATUS" in
    completed)
      echo ""
      if [[ "$RUN_CONCLUSION" == "success" ]]; then
        ok "Run completed with conclusion: $RUN_CONCLUSION"
      else
        warn "Run completed with conclusion: $RUN_CONCLUSION"
      fi
      break
      ;;
    queued|in_progress|waiting|requested|pending)
      info "  Status: $RUN_STATUS — waiting ${RUN_POLL_SECONDS}s..."
      ;;
    *)
      warn "Unknown status: $RUN_STATUS. Continuing to poll..."
      ;;
  esac

  if [[ $(date +%s) -ge $DEADLINE ]]; then
    echo ""
    warn "Timed out waiting for run to complete. Run URL: $RUN_URL"
    exit 1
  fi

  sleep "$RUN_POLL_SECONDS"
done

# ─── step 6: list new prs ─────────────────────────────────────────────────────

info "Step 6: Fetching PRs opened after $RUN_STARTED_AT ..."
echo ""

NEW_PRS_DISPLAY=$(gh pr list \
  --repo "$REPO" \
  --state open \
  --limit 100 \
  --json number,title,url,createdAt,headRefName \
  --jq ".[] | select((.headRefName | test(\"$SMARTFIX_BRANCH_RE\")) and (.createdAt >= \"$RUN_STARTED_AT\")) | \"  PR #\(.number): \(.title)\n  URL: \(.url)\n\"" \
  2>/dev/null || true)

NEW_PR_NUMBERS=$(gh pr list \
  --repo "$REPO" \
  --state open \
  --limit 100 \
  --json number,createdAt,headRefName \
  --jq "[.[] | select((.headRefName | test(\"$SMARTFIX_BRANCH_RE\")) and (.createdAt >= \"$RUN_STARTED_AT\")) | .number]" \
  2>/dev/null || echo "[]")

if [[ -z "$NEW_PRS_DISPLAY" ]]; then
  warn "No new SmartFix PRs found. The run may not have generated any fixes."
else
  echo "New SmartFix PRs:"
  echo "$NEW_PRS_DISPLAY"
fi

# ─── step 7: cleanup ──────────────────────────────────────────────────────────

# Always write state file (for skill wrapper or manual recovery)
jq -n \
  --arg repo "$REPO" \
  --arg original_ref "$ORIGINAL_REF" \
  --arg workflow_path "$WORKFLOW_PATH" \
  --arg branch "$BRANCH" \
  --argjson pr_numbers "$NEW_PR_NUMBERS" \
  '{repo: $repo, original_ref: $original_ref, workflow_path: $workflow_path, branch: $branch, pr_numbers: $pr_numbers}' \
  > "$CLEANUP_STATE_FILE"

if [[ "$SKIP_CLEANUP" == "true" ]]; then
  echo ""
  info "Step 7: Skipping interactive cleanup (--skip-cleanup mode)."
  info "  State written to $CLEANUP_STATE_FILE"
  echo ""
  ok "Steps 1–6 complete."
  exit 0
fi

echo ""
info "Step 7: Cleanup"
echo ""
echo "Press Enter to close new PRs and restore the workflow file to @$ORIGINAL_REF,"
echo "or Ctrl+C to keep everything as-is."
read -r

do_cleanup "$REPO" "$NEW_PR_NUMBERS" "$ORIGINAL_REF" "$WORKFLOW_PATH"
echo ""
ok "Scenario test complete."

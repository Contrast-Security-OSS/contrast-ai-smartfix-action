#!/usr/bin/env bash
# OTel E2E test runner for SmartFix (SS-90)
#
# Starts the grafana/otel-lgtm stack, runs a SmartFix workflow via act with
# the OTLP endpoint injected, then runs verify_spans.py to assert the span
# structure matches the instrumentation spec.
#
# Usage:
#   ./tests/otel/run_otel_test.sh
#   ./tests/otel/run_otel_test.sh --test-repo ~/jacob-dev/employee-management
#   ./tests/otel/run_otel_test.sh --workflow contrast-ai-smartfix-contrast-llm-local.yml
#   ./tests/otel/run_otel_test.sh --verify-only   # skip act, just run verify_spans.py
#
# Requirements:
#   - Docker / Rancher Desktop running
#   - act installed  (brew install act)
#   - python3 in PATH
#   - Test repo has .secrets and .vars files

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SMARTFIX_REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"

# --- Defaults ---
TEST_REPO="${TEST_REPO:-$HOME/jacob-dev/employee-management}"
WORKFLOW="contrast-ai-smartfix-smartfix-instructions-local.yml"
VERIFY_ONLY=false
TEMPO_URL="http://localhost:3200"
LGTM_COMPOSE="$SMARTFIX_REPO/docker-compose.otel.yml"
# SmartFix runs inside Docker via act; it reaches the host via host.docker.internal
OTEL_ENDPOINT_IN_CONTAINER="http://host.docker.internal:4318"
FLUSH_WAIT=8   # seconds to wait for spans to flush after act exits
LOG_FILE="/tmp/smartfix_otel_run.log"

# --- Parse args ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --test-repo)   TEST_REPO="$2";   shift 2 ;;
        --workflow)    WORKFLOW="$2";    shift 2 ;;
        --verify-only) VERIFY_ONLY=true; shift   ;;
        --tempo-url)   TEMPO_URL="$2";   shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

# --- Resolve Docker socket ---
# Rancher Desktop uses a non-standard socket path.
if [[ -z "${DOCKER_HOST:-}" ]]; then
    for sock in \
        "$HOME/.rd/docker.sock" \
        "/var/run/docker.sock" \
        "$HOME/.docker/run/docker.sock"; do
        if [[ -S "$sock" ]]; then
            export DOCKER_HOST="unix://$sock"
            break
        fi
    done
fi

if [[ -z "${DOCKER_HOST:-}" ]]; then
    echo "❌ Could not find Docker socket. Set DOCKER_HOST or start Docker/Rancher Desktop." >&2
    exit 1
fi

echo "Using DOCKER_HOST=$DOCKER_HOST"

# ── Step 1: Start LGTM ────────────────────────────────────────────────────

if [[ "$VERIFY_ONLY" == "false" ]]; then
    echo
    echo "═══ Starting grafana/otel-lgtm stack ═══"
    docker compose -f "$LGTM_COMPOSE" up -d

    echo "Waiting for Grafana to be ready..."
    for i in $(seq 1 30); do
        if curl -sf "http://localhost:3000/api/health" >/dev/null 2>&1; then
            echo "✅ Grafana is ready  (http://localhost:3000)"
            break
        fi
        if [[ "$i" -eq 30 ]]; then
            echo "❌ Grafana not ready after 60s — check: docker compose -f $LGTM_COMPOSE logs" >&2
            exit 1
        fi
        sleep 2
    done

    echo "Waiting for Tempo to be ready..."
    for i in $(seq 1 15); do
        if curl -sf "${TEMPO_URL}/api/search?limit=1" >/dev/null 2>&1; then
            echo "✅ Tempo is ready  ($TEMPO_URL)"
            break
        fi
        if [[ "$i" -eq 15 ]]; then
            echo "❌ Tempo not ready after 30s — check: docker compose -f $LGTM_COMPOSE logs" >&2
            exit 1
        fi
        sleep 2
    done
fi

# ── Step 2: Run SmartFix via act ──────────────────────────────────────────

if [[ "$VERIFY_ONLY" == "false" ]]; then
    echo
    echo "═══ Running SmartFix workflow via act ═══"
    echo "  Test repo:   $TEST_REPO"
    echo "  Workflow:    $WORKFLOW"
    echo "  OTel endpoint (inside container): $OTEL_ENDPOINT_IN_CONTAINER"
    echo "  Log: $LOG_FILE"
    echo

    if [[ ! -f "$TEST_REPO/.secrets" ]]; then
        echo "❌ $TEST_REPO/.secrets not found" >&2
        exit 1
    fi
    if [[ ! -f "$TEST_REPO/.vars" ]]; then
        echo "❌ $TEST_REPO/.vars not found" >&2
        exit 1
    fi

    # Clear cached action to pick up any local changes
    rm -rf ~/.cache/act/Contrast-Security-OSS-contrast-ai-smartfix-action* 2>/dev/null || true

    RUN_START=$(date +%s)

    (
        cd "$TEST_REPO"
        act workflow_dispatch \
            -W ".github/workflows/$WORKFLOW" \
            --secret-file .secrets \
            --var-file .vars \
            --env "OTEL_EXPORTER_OTLP_ENDPOINT=$OTEL_ENDPOINT_IN_CONTAINER" \
            -P ubuntu-latest=catthehacker/ubuntu:act-latest \
            --container-daemon-socket -
    ) 2>&1 | tee "$LOG_FILE"

    ACT_EXIT=${PIPESTATUS[0]}

    echo
    if [[ "$ACT_EXIT" -ne 0 ]]; then
        echo "⚠️  act exited with code $ACT_EXIT (SmartFix may have partially succeeded — proceeding to span check)"
    else
        echo "✅ act finished successfully"
    fi

    echo "Waiting ${FLUSH_WAIT}s for spans to flush to Tempo..."
    sleep "$FLUSH_WAIT"

    SINCE_MINUTES=$(( ($(date +%s) - RUN_START) / 60 + 2 ))
else
    echo "⏭️  Skipping act run (--verify-only)"
    SINCE_MINUTES=60
fi

# ── Step 3: Verify spans ──────────────────────────────────────────────────

echo
echo "═══ Verifying OTel spans ═══"
python3 "$SMARTFIX_REPO/tests/otel/verify_spans.py" \
    --tempo-url "$TEMPO_URL" \
    --since "$SINCE_MINUTES" \
    --wait 30

VERIFY_EXIT=$?

echo
if [[ "$VERIFY_EXIT" -eq 0 ]]; then
    echo "✅ OTel E2E test passed"
    echo "   Browse traces: http://localhost:3000 → Explore → Tempo"
else
    echo "❌ OTel E2E test failed"
    echo "   Browse traces: http://localhost:3000 → Explore → Tempo"
    echo "   Tip: run with --verify-only to re-check without re-running act"
fi

exit "$VERIFY_EXIT"

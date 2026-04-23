#!/usr/bin/env bash
# OTel LGTM stack manager + span verifier for SmartFix (SS-90)
#
# Manages the grafana/otel-lgtm Docker stack and verifies SmartFix span
# structure after a run.  Running the actual SmartFix workflow (via act or
# directly) is the caller's responsibility — this script does not know or
# care how SmartFix was invoked.
#
# Usage:
#   # Start the stack, then check spans from the last 60 minutes:
#   ./tests/otel/run_otel_test.sh
#
#   # Start the stack only (don't run verify_spans.py):
#   ./tests/otel/run_otel_test.sh --start-only
#
#   # Verify spans without (re)starting the stack:
#   ./tests/otel/run_otel_test.sh --verify-only
#
#   # Stop the stack:
#   ./tests/otel/run_otel_test.sh --stop
#
#   # Tune the look-back window:
#   ./tests/otel/run_otel_test.sh --verify-only --since 30
#
# Typical workflow from a consuming repo:
#   1. ./path/to/smartfix/tests/otel/run_otel_test.sh --start-only
#   2. OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318 \
#        <run SmartFix however you normally do>
#   3. ./path/to/smartfix/tests/otel/run_otel_test.sh --verify-only
#
# Requirements:
#   - Docker Desktop or Rancher Desktop running
#   - python3 in PATH

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SMARTFIX_REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
LGTM_COMPOSE="$SMARTFIX_REPO/docker-compose.otel.yml"
TEMPO_URL="http://localhost:3200"

# --- Defaults ---
START=true
VERIFY=true
STOP=false
SINCE=60

# --- Parse args ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --start-only)  VERIFY=false; shift ;;
        --verify-only) START=false;  shift ;;
        --stop)        START=false; VERIFY=false; STOP=true; shift ;;
        --since)       SINCE="$2";  shift 2 ;;
        --tempo-url)   TEMPO_URL="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

# --- Resolve Docker socket (Docker Desktop or Rancher Desktop) ---
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
    echo "❌ Could not find a Docker socket. Set DOCKER_HOST or start Docker/Rancher Desktop." >&2
    exit 1
fi

# ── Stop ──────────────────────────────────────────────────────────────────

if [[ "$STOP" == "true" ]]; then
    echo "Stopping grafana/otel-lgtm stack..."
    docker compose -f "$LGTM_COMPOSE" down
    echo "✅ Stack stopped"
    exit 0
fi

# ── Start ─────────────────────────────────────────────────────────────────

if [[ "$START" == "true" ]]; then
    echo
    echo "═══ Starting grafana/otel-lgtm stack ═══"
    docker compose -f "$LGTM_COMPOSE" up -d

    echo "Waiting for Grafana to be ready..."
    for i in $(seq 1 30); do
        if curl -sf --max-time 5 "http://localhost:3000/api/health" >/dev/null 2>&1; then
            echo "✅ Grafana ready  (http://localhost:3000)"
            break
        fi
        [[ "$i" -eq 30 ]] && { echo "❌ Grafana not ready after 60s" >&2; exit 1; }
        sleep 2
    done

    echo "Waiting for Tempo to be ready..."
    for i in $(seq 1 15); do
        if curl -sf --max-time 5 "${TEMPO_URL}/api/search?limit=1" >/dev/null 2>&1; then
            echo "✅ Tempo ready  ($TEMPO_URL)"
            break
        fi
        [[ "$i" -eq 15 ]] && { echo "❌ Tempo not ready after 30s" >&2; exit 1; }
        sleep 2
    done

    echo
    echo "Stack is up. Set this in your SmartFix workflow:"
    echo "  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318        (direct / outside Docker)"
    echo "  OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318  (inside Docker / act)"
fi

# ── Verify ────────────────────────────────────────────────────────────────

if [[ "$VERIFY" == "true" ]]; then
    echo
    echo "═══ Verifying OTel spans ═══"
    if python3 "$SMARTFIX_REPO/tests/otel/verify_spans.py" \
        --tempo-url "$TEMPO_URL" \
        --since "$SINCE" \
        --wait 30; then
        VERIFY_EXIT=0
    else
        VERIFY_EXIT=$?
    fi
    echo
    if [[ "$VERIFY_EXIT" -eq 0 ]]; then
        echo "✅ OTel span verification passed"
        echo "   Browse traces: http://localhost:3000 → Explore → Tempo"
    else
        echo "❌ OTel span verification failed — see above"
        echo "   Browse traces: http://localhost:3000 → Explore → Tempo"
    fi
    exit "$VERIFY_EXIT"
fi

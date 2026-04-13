#!/usr/bin/env python3
"""
OTel span verifier for SmartFix.

Queries the Tempo HTTP API for the most recent smartfix-run trace and
asserts that spans, names, and attributes match the SS-90 instrumentation spec.

Usage:
    python3 tests/otel/verify_spans.py
    python3 tests/otel/verify_spans.py --tempo-url http://localhost:3200
    python3 tests/otel/verify_spans.py --trace-id <traceID>
    python3 tests/otel/verify_spans.py --since 30   # look back N minutes (default 60)
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError


# ---------------------------------------------------------------------------
# Tempo HTTP API helpers
# ---------------------------------------------------------------------------

def _http_get(url: str, accept: str = "application/json") -> Any:
    req = Request(url, headers={"Accept": accept})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def search_recent_traces(tempo_url: str, since_minutes: int = 60, limit: int = 5) -> List[Dict]:
    """Return trace summaries from the last `since_minutes` minutes."""
    now = int(time.time())
    start = now - since_minutes * 60
    url = (
        f"{tempo_url}/api/search"
        f"?tags=service.name%3Dsmartfix"
        f"&limit={limit}"
        f"&start={start}"
        f"&end={now}"
    )
    data = _http_get(url)
    return data.get("traces", [])


def get_trace(tempo_url: str, trace_id: str) -> Dict:
    """Return the full OTLP-JSON trace for the given trace ID."""
    url = f"{tempo_url}/api/traces/{trace_id}"
    return _http_get(url)


# ---------------------------------------------------------------------------
# OTLP JSON span model
# ---------------------------------------------------------------------------

def _attr_value(attr: Dict) -> Any:
    """Extract a typed value from an OTLP attribute value dict."""
    v = attr.get("value", {})
    for key in ("stringValue", "intValue", "boolValue", "doubleValue"):
        if key in v:
            val = v[key]
            # intValue is encoded as a string in OTLP JSON
            if key == "intValue":
                return int(val)
            return val
    return None


@dataclass
class Span:
    name: str
    span_id: str
    parent_span_id: str          # "" for root
    attributes: Dict[str, Any] = field(default_factory=dict)
    status_code: str = ""        # "STATUS_CODE_ERROR" or ""
    children: List["Span"] = field(default_factory=list)

    def attr(self, key: str, default=None):
        return self.attributes.get(key, default)

    def has_attr(self, key: str) -> bool:
        return key in self.attributes


def _parse_trace(otlp_json: Dict) -> List[Span]:
    """Flatten all spans from an OTLP JSON trace into a list of Span objects."""
    spans = []
    for batch in otlp_json.get("batches", []):
        for scope_spans in batch.get("scopeSpans", []):
            for raw in scope_spans.get("spans", []):
                attrs = {a["key"]: _attr_value(a) for a in raw.get("attributes", [])}
                status = raw.get("status", {})
                status_code = status.get("code", "")
                spans.append(Span(
                    name=raw.get("name", ""),
                    span_id=raw.get("spanId", ""),
                    parent_span_id=raw.get("parentSpanId", ""),
                    attributes=attrs,
                    status_code=status_code,
                ))
    # Build children lists
    by_id = {s.span_id: s for s in spans}
    for span in spans:
        if span.parent_span_id and span.parent_span_id in by_id:
            by_id[span.parent_span_id].children.append(span)
    return spans


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"


@dataclass
class Result:
    status: str
    label: str
    detail: str = ""


class Checker:
    def __init__(self):
        self.results: List[Result] = []

    def check(self, condition: bool, label: str, detail: str = "") -> bool:
        status = PASS if condition else FAIL
        self.results.append(Result(status, label, detail))
        return condition

    def warn(self, condition: bool, label: str, detail: str = ""):
        status = PASS if condition else WARN
        self.results.append(Result(status, label, detail))

    def skip(self, label: str, reason: str = ""):
        self.results.append(Result(SKIP, label, reason))

    def passed(self) -> bool:
        return all(r.status != FAIL for r in self.results)

    def summary(self) -> str:
        counts = {PASS: 0, FAIL: 0, WARN: 0, SKIP: 0}
        for r in self.results:
            counts[r.status] += 1
        return (
            f"{counts[PASS]} passed, {counts[FAIL]} failed, "
            f"{counts[WARN]} warnings, {counts[SKIP]} skipped"
        )


def _print_results(checker: Checker, indent: str = "  "):
    for r in checker.results:
        icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ ", "SKIP": "⏭️ "}.get(r.status, "?")
        detail = f" — {r.detail}" if r.detail else ""
        print(f"{indent}{icon} {r.label}{detail}")


# ---------------------------------------------------------------------------
# Per-span-type verification
# ---------------------------------------------------------------------------

def verify_root_span(span: Span) -> Checker:
    c = Checker()
    c.check(span.name == "smartfix-run", "Span name is 'smartfix-run'", span.name)
    c.check(span.has_attr("session.id"), "Has session.id", str(span.attr("session.id")))
    c.check(
        span.has_attr("contrast.smartfix.vulnerabilities_total"),
        "Has contrast.smartfix.vulnerabilities_total",
        str(span.attr("contrast.smartfix.vulnerabilities_total")),
    )
    c.check(
        not span.has_attr("contrast.smartfix.files_modified"),
        "Does NOT have contrast.smartfix.files_modified (belongs on fix-vulnerability)",
    )
    c.check(
        not span.has_attr("contrast.smartfix.pr_created"),
        "Does NOT have contrast.smartfix.pr_created (belongs on fix-vulnerability)",
    )
    c.check(
        not span.has_attr("contrast.smartfix.pr_url"),
        "Does NOT have contrast.smartfix.pr_url (belongs on fix-vulnerability)",
    )
    return c


def verify_operation_span(span: Span, parent_id: str) -> Checker:
    c = Checker()
    c.check(span.name == "fix-vulnerability", "Span name is 'fix-vulnerability'", span.name)
    c.check(
        span.parent_span_id == parent_id,
        "Is a child of smartfix-run",
        f"parent={span.parent_span_id}",
    )
    # Required finding attributes
    c.check(span.has_attr("contrast.finding.fingerprint"), "Has contrast.finding.fingerprint",
            str(span.attr("contrast.finding.fingerprint")))
    c.check(span.attr("contrast.finding.source") == "runtime",
            "contrast.finding.source == 'runtime'", str(span.attr("contrast.finding.source")))
    c.check(span.has_attr("contrast.finding.rule_id"), "Has contrast.finding.rule_id",
            str(span.attr("contrast.finding.rule_id")))
    c.check(span.has_attr("contrast.smartfix.coding_agent"), "Has contrast.smartfix.coding_agent",
            str(span.attr("contrast.smartfix.coding_agent")))
    # Response attributes (set in finally block)
    c.check(span.has_attr("contrast.smartfix.fix_applied"), "Has contrast.smartfix.fix_applied",
            str(span.attr("contrast.smartfix.fix_applied")))
    c.check(span.has_attr("contrast.smartfix.files_modified"), "Has contrast.smartfix.files_modified",
            str(span.attr("contrast.smartfix.files_modified")))
    c.check(span.has_attr("contrast.smartfix.pr_created"), "Has contrast.smartfix.pr_created",
            str(span.attr("contrast.smartfix.pr_created")))
    # pr_url only when pr was created
    pr_created = span.attr("contrast.smartfix.pr_created")
    if pr_created:
        c.check(span.has_attr("contrast.smartfix.pr_url"), "Has contrast.smartfix.pr_url (pr_created=True)",
                str(span.attr("contrast.smartfix.pr_url")))
    else:
        c.warn(not span.has_attr("contrast.smartfix.pr_url"),
               "contrast.smartfix.pr_url absent when pr_created=False")
    # Optional but expected for SmartFix agent runs
    c.warn(span.has_attr("contrast.finding.language"), "Has contrast.finding.language (optional)",
           str(span.attr("contrast.finding.language")))
    return c


def verify_llm_span(span: Span, parent_id: str) -> Checker:
    c = Checker()
    c.check(span.name.startswith("chat "), "Span name starts with 'chat '", span.name)
    c.check(
        span.parent_span_id == parent_id,
        "Is a child of fix-vulnerability",
        f"parent={span.parent_span_id}",
    )
    c.check(span.has_attr("gen_ai.system"), "Has gen_ai.system",
            str(span.attr("gen_ai.system")))
    c.check(span.has_attr("gen_ai.request.model"), "Has gen_ai.request.model",
            str(span.attr("gen_ai.request.model")))
    c.check(span.attr("gen_ai.operation.name") == "chat",
            "gen_ai.operation.name == 'chat'", str(span.attr("gen_ai.operation.name")))
    c.check(span.has_attr("gen_ai.retry.attempt"), "Has gen_ai.retry.attempt",
            str(span.attr("gen_ai.retry.attempt")))
    c.check(span.has_attr("gen_ai.usage.input_tokens"), "Has gen_ai.usage.input_tokens",
            str(span.attr("gen_ai.usage.input_tokens")))
    c.check(span.has_attr("gen_ai.usage.output_tokens"), "Has gen_ai.usage.output_tokens",
            str(span.attr("gen_ai.usage.output_tokens")))
    c.check(span.has_attr("gen_ai.response.model"), "Has gen_ai.response.model",
            str(span.attr("gen_ai.response.model")))
    return c


# ---------------------------------------------------------------------------
# Top-level trace verifier
# ---------------------------------------------------------------------------

def verify_trace(spans: List[Span]) -> bool:
    """Run all assertions against a parsed trace. Returns True if all checks pass."""
    by_id = {s.span_id: s for s in spans}

    # Find root
    roots = [s for s in spans if not s.parent_span_id]
    if not roots:
        print("❌ No root span found")
        return False

    root = next((s for s in roots if s.name == "smartfix-run"), None)
    if root is None:
        print(f"❌ Root span is not 'smartfix-run' (found: {[s.name for s in roots]})")
        return False

    overall_pass = True

    # --- Root span ---
    print("\n── smartfix-run (root span) ──")
    c = verify_root_span(root)
    _print_results(c)
    print(f"  {c.summary()}")
    if not c.passed():
        overall_pass = False

    vuln_total = root.attr("contrast.smartfix.vulnerabilities_total", 0)
    print(f"\n  vulnerabilities_total = {vuln_total}")

    # --- fix-vulnerability spans ---
    op_spans = [s for s in spans if s.name == "fix-vulnerability"]
    if not op_spans:
        if vuln_total and vuln_total > 0:
            print(f"\n❌ Expected fix-vulnerability spans (vulnerabilities_total={vuln_total}) but none found")
            overall_pass = False
        else:
            print("\n⏭️  No fix-vulnerability spans (vulnerabilities_total=0 — no vulns processed)")
        return overall_pass

    print(f"\n── fix-vulnerability spans ({len(op_spans)} found) ──")
    for i, op in enumerate(op_spans):
        fp = op.attr("contrast.finding.fingerprint", "?")
        rule = op.attr("contrast.finding.rule_id", "?")
        print(f"\n  [{i+1}] {fp} / {rule}")
        c = verify_operation_span(op, root.span_id)
        _print_results(c, indent="    ")
        print(f"    {c.summary()}")
        if not c.passed():
            overall_pass = False

        # --- chat (LLM) spans under this operation span ---
        llm_spans = [s for s in spans if s.name.startswith("chat ") and s.parent_span_id == op.span_id]
        if not llm_spans:
            agent = op.attr("contrast.smartfix.coding_agent", "")
            if agent == "smartfix":
                print(f"    ❌ Expected chat spans under fix-vulnerability (coding_agent=smartfix) but none found")
                overall_pass = False
            else:
                print(f"    ⏭️  No chat spans (coding_agent={agent!r} — external agent, expected)")
        else:
            print(f"\n    ── chat spans ({len(llm_spans)} LLM calls) ──")
            for j, llm in enumerate(llm_spans):
                attempt = llm.attr("gen_ai.retry.attempt", "?")
                model = llm.attr("gen_ai.request.model", llm.name)
                print(f"\n      [{j+1}] {llm.name}  attempt={attempt}  model={model}")
                c = verify_llm_span(llm, op.span_id)
                _print_results(c, indent="        ")
                print(f"        {c.summary()}")
                if not c.passed():
                    overall_pass = False

    return overall_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Verify SmartFix OTel span structure against Tempo")
    parser.add_argument("--tempo-url", default="http://localhost:3200")
    parser.add_argument("--trace-id", default=None, help="Verify a specific trace ID")
    parser.add_argument("--since", type=int, default=60, help="Look back N minutes for traces (default 60)")
    parser.add_argument("--wait", type=int, default=0,
                        help="Poll for traces for up to N seconds before giving up (default 0)")
    args = parser.parse_args()

    # Check Tempo is up
    try:
        _http_get(f"{args.tempo_url}/api/search?limit=1")
    except URLError as e:
        print(f"❌ Cannot reach Tempo at {args.tempo_url}: {e}")
        print("   Is the LGTM stack running?  docker compose -f docker-compose.otel.yml up -d")
        sys.exit(1)

    # Find trace
    if args.trace_id:
        trace_id = args.trace_id
        print(f"Using specified trace ID: {trace_id}")
    else:
        deadline = time.time() + args.wait
        trace_id = None
        while True:
            traces = search_recent_traces(args.tempo_url, since_minutes=args.since)
            smartfix_runs = [t for t in traces if t.get("rootTraceName") == "smartfix-run"]
            if smartfix_runs:
                # Pick the most recent
                smartfix_runs.sort(key=lambda t: t.get("startTimeUnixNano", "0"), reverse=True)
                trace_id = smartfix_runs[0]["traceID"]
                started = int(smartfix_runs[0].get("startTimeUnixNano", 0)) // 1_000_000_000
                duration_s = smartfix_runs[0].get("durationMs", 0) / 1000
                print(f"Found trace: {trace_id}  (started {int(time.time()) - started}s ago, "
                      f"duration {duration_s:.0f}s)")
                break
            if time.time() >= deadline:
                print(f"❌ No smartfix-run traces found in the last {args.since} minutes")
                print(f"   Available traces: {[t.get('rootTraceName') for t in traces]}")
                sys.exit(1)
            print(f"  No traces yet, retrying... ({int(deadline - time.time())}s remaining)")
            time.sleep(5)

    # Fetch and parse
    print(f"\nFetching trace {trace_id} from Tempo...")
    raw = get_trace(args.tempo_url, trace_id)
    spans = _parse_trace(raw)
    print(f"Parsed {len(spans)} spans")

    # Verify
    print("\n" + "=" * 60)
    print("SmartFix OTel Span Verification")
    print("=" * 60)
    passed = verify_trace(spans)
    print("\n" + "=" * 60)

    if passed:
        print("✅ All assertions passed")
        sys.exit(0)
    else:
        print("❌ One or more assertions failed — see above for details")
        sys.exit(1)


if __name__ == "__main__":
    main()

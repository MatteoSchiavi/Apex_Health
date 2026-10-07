"""Offline by default. Live needs --live --allow-paid-live, environment opt-in
and an explicit model. Run ``python -m evals.run`` from backend.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from evals.scenarios import reference_scenarios


async def evaluate(scenarios, *, client=None):
    from evals.harness import run_scenario
    from evals.scorers import score_trace
    results = []
    for scenario in scenarios:
        try:
            trace = await run_scenario(scenario, client=client)
            scores = score_trace(scenario, trace)
            results.append({
                "id": scenario.id, "challenge": scenario.challenge,
                "passed": all(s.passed for s in scores),
                "scores": [s.to_dict() for s in scores],
                "reply": trace.result.reply, "grounding": trace.result.grounding,
                "converged": trace.result.converged, "iterations": trace.result.iterations,
                "tool_audit": trace.result.tool_audit,
                "models": sorted({r.model for r in trace.responses}),
            })
        except Exception as exc:
            # Never persist provider error strings or configuration secrets.
            results.append({"id": scenario.id, "challenge": scenario.challenge,
                            "passed": False, "error": type(exc).__name__, "scores": []})
    passed = sum(r["passed"] for r in results)
    return {
        "schema_version": "apex-agent-evals-v1",
        "mode": "live_synthetic" if client else "deterministic_runtime_replay",
        "scope": "Production loop and registered handlers; strict synthetic memory SQL boundary.",
        "limitations": [
            "Replay responses are reference and attack scripts, not observed model quality.",
            "Safety concepts and causal language use a lexical rubric, not a clinical or model judge.",
            "Memory SQL supports exercised predicates, not full PostgreSQL semantics or transaction isolation.",
            "Costs are rate-table estimates; fixture token usage is synthetic and provider spend is zero.",
            "Offline latency is measured runtime overhead and does not predict live provider latency.",
        ],
        "summary": {"total": len(results), "passed": passed, "failed": len(results) - passed},
        "scenarios": results,
    }


def markdown_report(report):
    summary = report["summary"]
    lines = ["# Apex agent evaluation", "", f"Mode: `{report['mode']}`", "",
             f"Passed **{summary['passed']}/{summary['total']}** scenarios.", "",
             "| Scenario | Result | Failing checks | Estimated USD | Runtime ms |",
             "| --- | --- | --- | ---: | ---: |"]
    for result in report["scenarios"]:
        scores = {s["name"]: s for s in result["scores"]}
        failures = ", ".join(s["name"] for s in result["scores"] if not s["passed"])
        if result.get("error"):
            failures = f"Runtime exception: {result['error']}"
        estimated = scores.get("cost", {}).get("metrics", {}).get("estimated_cost_usd", "—")
        elapsed = scores.get("latency", {}).get("metrics", {}).get("elapsed_ms", "—")
        lines.append(f"| {result['id']} | {'PASS' if result['passed'] else 'FAIL'} | {failures or '—'} | {estimated} | {elapsed} |")
    lines += ["", "## Scope and limits", "", report["scope"], ""]
    lines += [f"- {line}" for line in report["limitations"]]
    for result in report["scenarios"]:
        if result["passed"]:
            continue
        lines += ["", f"## Failure: {result['id']}", ""]
        for score in result["scores"]:
            if not score["passed"]:
                lines.append(f"- **{score['name']}**: `{json.dumps(score['metrics'], sort_keys=True)}`")
    return "\n".join(lines) + "\n"


def write_reports(report, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = output_dir / "report.json", output_dir / "report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    md_path.write_text(markdown_report(report))
    return json_path, md_path


def parser():
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument("--scenario", action="append", choices=[s.id for s in reference_scenarios()],
                      help="Run only this scenario; repeat to select several")
    argp.add_argument("--output-dir", type=Path, default=Path("evals/artifacts"))
    argp.add_argument("--live", action="store_true", help="Use explicitly configured provider on synthetic fixtures")
    argp.add_argument("--allow-paid-live", action="store_true", help="Acknowledge live requests may incur charges")
    return argp


def validate_live_options(args):
    if args.allow_paid_live and not args.live:
        raise ValueError("--allow-paid-live requires --live")
    if args.live:
        if not args.allow_paid_live or os.environ.get("APEX_EVALS_ALLOW_LIVE") != "1":
            raise ValueError("Live requests require --live --allow-paid-live and APEX_EVALS_ALLOW_LIVE=1")
        if not os.environ.get("LLM_PROVIDER_CHEAP", "").strip():
            raise ValueError("Live evaluations require explicit LLM_PROVIDER_CHEAP; no model is guessed")


async def _run(args):
    client = None
    if args.live:
        from app.core.llm import build_llm_client
        client = build_llm_client()
    try:
        selected = [s for s in reference_scenarios() if not args.scenario or s.id in args.scenario]
        return await evaluate(selected, client=client)
    finally:
        if client is not None:
            await client.aclose()


def main(argv=None):
    argp = parser()
    args = argp.parse_args(argv)
    try:
        validate_live_options(args)
    except ValueError as exc:
        argp.error(str(exc))
    report = asyncio.run(_run(args))
    paths = write_reports(report, args.output_dir)
    summary = report["summary"]
    print(f"{report['mode']}: {summary['passed']}/{summary['total']} passed")
    print(f"JSON: {paths[0].resolve()}")
    print(f"Markdown: {paths[1].resolve()}")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

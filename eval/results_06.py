"""Assignment 6: the outcome of every measured run, from the tracker, never from an agent's message.

  python eval/results_06.py

Writes results/runs_06.jsonl, one line per finished run of arm S (agent), M (split) or S-plus
(splus) on a fixtures/tasks6 task (checks/FORMATS.md, section 14.7): the run's arm, task, kind, sweep,
whether it passed eval/check_task.py, each issue's result, its tokens and its wall-clock. Then it
prints the `arms` and `multiplier` blocks for reports/LAB_06.json and a table to read.
A run on a scripted model is left out, and so is a run a rate limit or the quota stopped.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.check_task import check_task          # noqa: E402
from harness.runner import is_free               # noqa: E402
from harness.tasks import load_task              # noqa: E402

ARMS = {"agent": "S", "split": "M", "splus": "S_plus"}
TRACE = re.compile(r"(agent|split|splus)-((?:one|batch)-[a-z0-9]+)-s(\d+)-[0-9a-f]+\.jsonl")
SWEEPS = 3


def finished_runs(runs_dir: Path = ROOT / "runs", *, include_scripted: bool = False) -> list[dict]:
    """The finished measured runs: one dict each, from the trace alone."""
    out = []
    for path in sorted(runs_dir.glob("*.jsonl")):
        match = TRACE.fullmatch(path.name)
        if not match:
            continue
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        start = records[0] if records and records[0].get("type") == "run_start" else None
        end = records[-1] if records and records[-1].get("type") == "run_end" else None
        if not start or not end:
            continue                                            # not finished
        if {"quota", "rate_limited"} & {r.get("terminal_reason") for r in records if r.get("type") == "end"}:
            continue                                            # stopped by a limit: run it again
        if is_free(start.get("backend") or "") and not include_scripted:
            continue
        way, task, sweep = match.group(1), match.group(2), int(match.group(3))
        out.append({"run_id": start["run_id"], "arm": ARMS[way], "way": way, "task": task,
                    "kind": start.get("kind") or ("single" if task.startswith("one-") else "batch"), "sweep": sweep,
                    "tokens": int((end.get("totals") or {}).get("total_tokens") or 0),
                    "wall_s": float(end.get("elapsed_s") or 0.0)})
    return out


def grade(run: dict) -> dict:
    """The run's row: the grounded check, read from the tracker."""
    result = check_task(run["run_id"], load_task(ROOT / "fixtures" / "tasks6" / f"{run['task']}.yaml"))
    return {**run, "passed": bool(result["passed"]), "parts": {str(k): bool(v) for k, v in result["parts"].items()}}


def summarize(rows: list[dict]) -> dict:
    """One arm's single and batch figures, as reports/LAB_06.json's `arms` states them (section 14.8)."""
    out = {}
    for kind in ("single", "batch"):
        mine = [r for r in rows if r["kind"] == kind]
        per_task: dict[str, int] = {}
        sweeps: dict[int, int] = {}
        for r in mine:
            per_task[r["task"]] = per_task.get(r["task"], 0) + int(r["passed"])
            sweeps[r["sweep"]] = sweeps.get(r["sweep"], 0) + int(r["passed"])
        out[kind] = {"runs": len(mine), "passes": sum(int(r["passed"]) for r in mine), "per_task": dict(sorted(per_task.items())),
                     "sweep_min": min(sweeps.values()) if sweeps else None, "sweep_max": max(sweeps.values()) if sweeps else None,
                     "all_three": sum(1 for n in per_task.values() if n >= SWEEPS),
                     "mean_tokens": round(mean(r["tokens"] for r in mine)) if mine else None,
                     "mean_wall_s": round(mean(r["wall_s"] for r in mine), 1) if mine else None}
    return out


def main() -> int:
    rows = [grade(r) for r in finished_runs(include_scripted=os.environ.get("INCLUDE_SCRIPTED") == "1")]
    rows.sort(key=lambda r: (r["arm"], r["task"], r["sweep"]))
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    (results / "runs_06.jsonl").write_text("".join(json.dumps(r, sort_keys=False) + "\n" for r in rows))
    print(f"wrote results/runs_06.jsonl: {len(rows)} runs\n")

    arms = {arm: summarize([r for r in rows if r["arm"] == arm]) for arm in ("S", "M", "S_plus")}
    multiplier = {}
    for kind in ("single", "batch"):
        s, m = arms["S"][kind]["mean_tokens"], arms["M"][kind]["mean_tokens"]
        multiplier[kind] = round(m / s, 2) if s and m else None
    for arm in ("S", "M", "S_plus"):
        for kind in ("single", "batch"):
            c = arms[arm][kind]
            if c["runs"]:
                print(f"{arm:7} {kind:6} passes {c['passes']:>2}/{c['runs']:<2} | per sweep {c['sweep_min']} to {c['sweep_max']} | "
                      f"all three sweeps passed on {c['all_three']} tasks | mean {c['mean_tokens']:>8,} tokens | mean {c['mean_wall_s']:>5} s")
    print(f"\nmultiplier (M over S): single {multiplier['single']}, batch {multiplier['batch']}")
    print("\nfor reports/LAB_06.json:")
    print(json.dumps({"arms": arms, "multiplier": multiplier}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

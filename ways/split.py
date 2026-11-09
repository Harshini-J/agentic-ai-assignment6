"""Arm M in Assignment 6: a coordinator and two roles, split by tool surface.

  coordinator  plain code, no model, no tools of its own. It writes each worker's brief,
               reads each return, and pairs each finding with its issue by construction
               (a worker is named for its issue). It is an agent in the trace.
  investigator one per issue; reads and searches only (issues_read, code_search,
               code_read_file, code_run_tests) and a local return_finding tool.
  writer       one per issue; writes only (issues_label, pulls_open, issues_comment).

Round 1: the five investigators run at once. Round 2: the coordinator reads the returns
and briefs a writer for every issue whose finding names a label and a file. Every call,
every agent's, goes through the registry and its hook. The disclosure line goes on every
comment in one function, ways.agent.with_disclosure, which Disclosing applies before the
registry sees the call.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from agent.loop import load_bounds, run_loop
from harness.tasks import end_state
from split.guards import Waits, check_combined
from split.roles import INVESTIGATOR_ROLES, WRITER_ROLES, RoleTools
from ways.agent import Disclosing, disclosure_line

# A worker's share of its issue's slice of the run's budget. The rest is held back: a worker
# stops only after the call that crosses its share, so the held-back part keeps the run's
# total under the ceiling.
INVESTIGATOR_SHARE, WRITER_SHARE = 0.60, 0.25      # 15% of every slice is held back
WRITER_STEPS = 8


def shares(ctx, n_issues: int):
    """Each worker's Bounds, from the run's budget: (investigator, writer)."""
    base = load_bounds()
    per_issue = (ctx.budget if ctx.budget else base.max_tokens * n_issues) // n_issues
    return (replace(base, max_tokens=int(per_issue * INVESTIGATOR_SHARE)),
            replace(base, max_steps=WRITER_STEPS, max_tokens=int(per_issue * WRITER_SHARE)))


def investigator_brief(issue: int, steps: int, tokens: int) -> str:
    return (f"Investigate issue #{issue}. Its identifier is issue-{issue}. "
            f"Find the file most responsible and send your finding with return_finding. "
            f"You have at most {steps} model calls and about {tokens:,} tokens, and then you are stopped "
            f"without being able to send anything: if you cannot settle it in time, send your best answer "
            f"as candidate, or out_of_budget with what you could not determine.")


def writer_brief(issue: int, contract: dict, read: str) -> str:
    """The writer's brief. `read` is the harness's fact (RoleTools.file_read), not the model's word."""
    found = contract["result"]
    lines = [f"Write the triage of issue #{issue} (identifier issue-{issue}) from this finding. "
             f"Copy the label and the file exactly.", "",
             f"label: {found['label']}", f"file: {found['file']}", f"status: {contract['status']}",
             "read by the investigator: " + {"yes": "yes", "no": "no, so the file is a candidate, not confirmed",
                                             "n/a": "not applicable, the file is none"}[read]]
    if found["what_to_change"]:
        lines.append(f"what to change: {found['what_to_change']}")
    lines.append(f"evidence: {found['evidence']}")
    if contract["could_not_determine"]:
        lines.append("could not determine: " + "; ".join(contract["could_not_determine"]))
    return "\n".join(lines)


def writable(contract: dict | None) -> bool:
    """A finding the writer may act on: a real label and a file (a path, or none), neither undetermined.
    The schema cannot forbid the string unknown or an empty one as a file, so this refuses them: the
    writer is never briefed to write a file that was not determined."""
    if not contract:
        return False
    found = contract["result"]
    file = found["file"]
    return found["label"] != "unknown" and isinstance(file, str) and file.strip().lower() not in ("", "unknown")


def run(ctx) -> None:
    lead = ctx.agent("coordinator")                      # parent None
    registry = Disclosing(ctx.tools, disclosure_line())  # the disclosure line, before the registry
    issues = ctx.issues
    investigator_bounds, writer_bounds = shares(ctx, len(issues))
    share = {"investigator": investigator_bounds.max_tokens, "writer": writer_bounds.max_tokens}
    total_budget = ctx.budget if ctx.budget else load_bounds().max_tokens * len(issues)
    lead.trace.event("budget_plan", budget=total_budget, ceiling=ctx.ceiling, issues=len(issues),
                     investigator_share=share["investigator"], writer_share=share["writer"],
                     held_back=total_budget - len(issues) * (share["investigator"] + share["writer"]))
    surfaces_by_id: dict[str, RoleTools] = {}
    waits = Waits(lead.trace, stop=lambda victim: setattr(surfaces_by_id[victim], "stopped", True)
                  if victim in surfaces_by_id else None)       # every wait is a line in the trace, and a cycle stops one worker

    def investigate(issue: int):
        worker = ctx.agent(f"investigator-{issue}", parent=lead.id)
        surface = RoleTools(registry, INVESTIGATOR_ROLES, worker.id, issue, lead, returns=True)
        surfaces_by_id[worker.id] = surface
        real_end = worker.trace.end

        def end(reason, detail=""):                 # remember why this loop ended, then write the line as usual
            surface.end_reason = reason
            real_end(reason, detail)
        worker.trace.end = end
        run_loop(worker.client, surface, ctx.prompt("investigator.md"),
                 investigator_brief(issue, investigator_bounds.max_steps, investigator_bounds.max_tokens),
                 investigator_bounds, worker.trace)
        return surface

    def write(issue: int, contract: dict, read: str):
        worker = ctx.agent(f"writer-{issue}", parent=lead.id)
        found = contract["result"]
        surface = RoleTools(registry, WRITER_ROLES, worker.id, issue, lead, expect=(found["label"], found["file"]))
        surfaces_by_id[worker.id] = surface
        run_loop(worker.client, surface, ctx.prompt("writer.md"), writer_brief(issue, contract, read),
                 writer_bounds, worker.trace)

    # Round 1: the investigators, at once. The coordinator waits on each.
    for issue in issues:
        waits.wait(lead.id, f"investigator-{issue}", "a finding", 0)
    with ThreadPoolExecutor(max_workers=len(issues)) as pool:
        surfaces = dict(zip(issues, [f.result() for f in [pool.submit(investigate, i) for i in issues]]))
    for issue in issues:
        waits.done(f"investigator-{issue}")

    # Round 2: the coordinator reads the returns, and briefs a writer for each finding it can act on.
    briefed = {}
    for issue, surface in surfaces.items():
        if surface.accepted is None:        # no return that fit the contract ever arrived: a different event,
            lead.trace.event("no_return", worker=f"investigator-{issue}",       # never a made-up worker_return
                             sent=surface.sent, searched=surface.searched, calls_used=surface.calls,
                             reason=surface.end_reason)
            lead.trace.event("writer_skipped", issue=issue, reason="no valid return")
        elif not writable(surface.accepted):
            lead.trace.event("writer_skipped", issue=issue, reason="the finding names no label or file")
        else:
            read = surface.file_read(surface.accepted["result"]["file"])
            if surface.accepted["status"] == "found" and read == "no":     # it said found, and never read the file
                lead.trace.event("unread_finding", worker=f"investigator-{issue}", file=surface.accepted["result"]["file"])
            briefed[issue] = (surface.accepted, read)
    for issue in briefed:
        waits.wait(lead.id, f"writer-{issue}", "the writes", 1)
    with ThreadPoolExecutor(max_workers=max(1, len(briefed))) as pool:
        for f in [pool.submit(write, i, c, r) for i, (c, r) in briefed.items()]:
            f.result()
    for issue in briefed:
        waits.done(f"writer-{issue}")

    # After the last write: the combined result, read from the tracker and tested against rules set
    # before the run. Nothing an agent said is in it, and it needs no answer key.
    if ctx.task is not None:
        violations = check_combined(ctx.task, end_state(ctx.tracker, ctx.run_id, ctx.task))
        lead.trace.event("combined_check", passed=not violations, violations=violations)
    spent = {a.id: a.client.total_tokens for a in ctx.agents.values()}
    lead.trace.event("agent_tokens", tokens=spent)
    over = [a for a, n in spent.items() if a != lead.id and n > share["investigator" if a.startswith("investigator") else "writer"]]
    lead.trace.event("budget_check", total=ctx.client.total_tokens, ceiling=ctx.ceiling,
                     within=ctx.ceiling is None or ctx.client.total_tokens <= ctx.ceiling, over_share=over)
    lead.trace.end("completed", detail=f"{len(briefed)} of {len(issues)} issues written")


__all__ = ["run", "shares", "investigator_brief", "writer_brief", "writable"]

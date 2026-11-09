"""Arm S-plus in Assignment 6: one agent, given what arm M actually spent (run.py --match split).

Slide 18's third question: given the same budget, did one agent do as well? The fair rival to a
team is one agent that spends the team's budget on further attempts (slide 16), not a team.
It is one agent, with no roles and nothing run at once:

  1. an attempt on every issue: a fresh context, read-only tools, an answer sent with
     return_finding (the same contract as the split's investigator);
  2. further attempts, one after another, until the budget cannot pay for another, each on the
     issue its answers leave least settled (no answer yet, then answers that disagree, then an
     answer its own attempt called a candidate or left doubts about, then the fewest attempts);
  3. a choice of answer by a vote over an issue's attempts, with ties settled by what an attempt
     reports about itself (status found, fewest doubts, earliest): nothing here reads the answers;
  4. the chosen answer written once, by code: the label, a draft pull request when the file is not
     none, and the comment last, each through the registry and its hook. The writes are mechanical,
     so no model call pays for them: the budget goes on attempts.

ctx.budget is arm M's mean spend on this task; the harness's ceiling stays at the arms' own, so
the budget is the target, never a wall.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from statistics import mean

from agent.loop import load_bounds, run_loop
from harness.formats import normalize_path
from harness.roles import arg, tool_for
from split.roles import INVESTIGATOR_ROLES, RoleTools
from ways.agent import disclosure_line, with_disclosure

FIRST_GUESS = 30_000        # what an attempt is expected to cost, until one has finished
CAP = 1.5                   # an attempt may spend this many times what the last ones cost
MOST_ATTEMPTS_PER_ISSUE = 4


def attempt_brief(issue: int, steps: int, tokens: int) -> str:
    return (f"Make one attempt at issue #{issue}. Its identifier is issue-{issue}. "
            f"Find the file most responsible and send your answer with return_finding. "
            f"You have at most {steps} model calls and about {tokens:,} tokens, and then you are stopped "
            f"without being able to send anything: if you cannot settle it in time, send your best answer "
            f"as candidate, or out_of_budget with what you could not determine.")


def usable(contract: dict | None) -> bool:
    """An attempt's answer can be written: a real label and a file (a path, or none)."""
    if not contract:
        return False
    found = contract["result"]
    file = found["file"]
    return found["label"] != "unknown" and isinstance(file, str) and file.strip().lower() not in ("", "unknown")


def key_of(contract: dict) -> tuple[str, str]:
    return contract["result"]["label"], normalize_path(contract["result"]["file"]) or "none"


def choose(attempts: list[dict]) -> dict | None:
    """The attempt whose answer wins a vote among an issue's usable attempts, or None.

    Most votes; then the answer more attempts called `found`; then the answer with the fewest doubts
    listed (could_not_determine); then the earliest. None of it reads an answer key."""
    good = [a for a in attempts if usable(a["contract"])]
    if not good:
        return None
    votes = Counter(key_of(a["contract"]) for a in good)

    def rank(answer):
        mine = [a for a in good if key_of(a["contract"]) == answer]
        return (-votes[answer], -sum(a["contract"]["status"] == "found" for a in mine),
                sum(len(a["contract"]["could_not_determine"]) for a in mine), min(a["k"] for a in mine))
    winner = min(votes, key=rank)
    return min((a for a in good if key_of(a["contract"]) == winner), key=lambda a: a["k"])


def unsettled(attempts: list[dict]) -> tuple:
    """How unsettled an issue is, so the next attempt goes where it is most needed: smaller sorts first
    means more needed. No usable answer; answers that disagree; a doubt or a candidate; then fewest attempts."""
    good = [a for a in attempts if usable(a["contract"])]
    if not good:
        return (0, len(attempts))
    answers = {key_of(a["contract"]) for a in good}
    doubtful = any(a["contract"]["status"] != "found" or a["contract"]["could_not_determine"] for a in good)
    return (1 if len(answers) > 1 else 2 if doubtful else 3, len(attempts))


def title_of(what_to_change: str, file: str) -> str:
    first = (what_to_change or "").strip().split(". ")[0].strip().rstrip(".")
    return (first[:72] if first else f"Update {file}")


def run(ctx) -> None:
    issues = ctx.issues
    n = len(issues)
    base = load_bounds()
    budget = ctx.budget if ctx.budget else base.max_tokens * n
    root = ctx.agent("splus")                              # the one agent; its attempts are its fresh contexts
    attempts: dict[int, list[dict]] = {issue: [] for issue in issues}
    costs: list[int] = []
    root.trace.event("budget_plan", budget=budget, ceiling=ctx.ceiling, issues=n)

    def attempt(issue: int) -> None:
        k = len(attempts[issue]) + 1
        agent = ctx.agent(f"attempt-{issue}-{k}", parent=root.id)
        expected = mean(costs) if costs else FIRST_GUESS
        bounds = replace(base, max_tokens=int(CAP * expected))
        surface = RoleTools(ctx.tools, INVESTIGATOR_ROLES, agent.id, issue, root, returns=True)
        run_loop(agent.client, surface, ctx.prompt("splus.md"), attempt_brief(issue, bounds.max_steps, bounds.max_tokens),
                 bounds, agent.trace)
        costs.append(agent.client.total_tokens)
        attempts[issue].append({"k": k, "contract": surface.accepted, "tokens": agent.client.total_tokens})

    for issue in issues:                                    # 1. an attempt on every issue
        attempt(issue)
    while sum(len(a) for a in attempts.values()) < MOST_ATTEMPTS_PER_ISSUE * n:       # 2. further attempts, while they fit
        remaining = budget - ctx.client.total_tokens
        if remaining < mean(costs):
            break
        pick = min((i for i in issues if len(attempts[i]) < MOST_ATTEMPTS_PER_ISSUE), key=lambda i: unsettled(attempts[i]), default=None)
        if pick is None:
            break
        attempt(pick)

    line = disclosure_line()                                 # 3 and 4: choose, then write each chosen answer once
    step = 0

    def write(name: str, tool_input: dict):
        nonlocal step
        step += 1
        return root.call_tool(step, name, tool_input)

    for issue in issues:
        chosen = choose(attempts[issue])
        votes = Counter(key_of(a["contract"]) for a in attempts[issue] if usable(a["contract"]))
        root.trace.event("chosen", issue=issue, attempts=len(attempts[issue]), votes={f"{l}|{f}": v for (l, f), v in votes.items()},
                         answer=None if chosen is None else list(key_of(chosen["contract"])))
        if chosen is None:
            continue
        found = chosen["contract"]["result"]
        label, file = key_of(chosen["contract"])
        ref = f"issue-{issue}"
        if write(tool_for("apply_label"), {arg("apply_label", "number"): ref, arg("apply_label", "label"): label}).is_error:
            continue
        if file != "none":
            what = " ".join(str(found["what_to_change"] or "").split())[:3500]       # the tool's cap is 4,000, and an error, not a cut
            body = f"File: {file}\n\n{what or 'See the comment on the issue.'}"
            if write(tool_for("open_pr"), {arg("open_pr", "number"): ref, arg("open_pr", "branch"): f"repomind/issue-{issue}",
                                           arg("open_pr", "title"): title_of(found["what_to_change"], file),
                                           arg("open_pr", "body"): body}).is_error:
                continue
        why = " ".join(str(found["evidence"] or found["what_to_change"] or "").split())[:1500]   # the cap is 2,000 with the disclosure line
        text = f"label: {label}\nfile: {file}\n{why}".rstrip()
        write(tool_for("comment"), {arg("comment", "number"): ref, arg("comment", "body"): with_disclosure(text, line)})
    root.trace.event("budget_check", total=ctx.client.total_tokens, budget=budget,
                     attempts=sum(len(a) for a in attempts.values()))
    root.trace.end("completed", detail=f"{sum(len(a) for a in attempts.values())} attempts on {n} issues")


__all__ = ["run", "choose", "unsettled", "usable", "attempt_brief"]

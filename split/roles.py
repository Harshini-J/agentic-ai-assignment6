"""The split's roles: what each worker may call, and the facts about what it did.

A role's tool surface is the object handed to its loop (agent/loop.py's run_loop takes
anything with .schemas and .call(name, input)). RoleTools offers a worker only its
own tools' schemas and refuses any other name itself, so a refused call never
reaches the registry (and never counts as one of its protocol errors). Every call it
does forward goes through the run's registry and hook.

The investigator also holds a local tool, return_finding, which is not the registry's.
The contract's `searched` and `calls_used` are filled in here from the worker's own
calls, never from what the model says it did (checks/FORMATS.md, section 14.4).
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from harness.formats import normalize_path, parse_triage_comment
from harness.roles import arg, role_of, tool_for
from harness.schema import errors as schema_errors
from tools import ToolResult

CONTRACT = json.loads((Path(__file__).parent / "contract.schema.json").read_text())

INVESTIGATOR_ROLES = ("read_issue", "search", "read_file", "run_tests")
WRITER_ROLES = ("apply_label", "open_pr", "comment")
OWN_ISSUE_ROLES = ("read_issue", "apply_label", "open_pr", "comment")   # every tool that names an issue

RETURN_TOOL = "return_finding"
_MODEL_FIELDS = ("result", "status", "not_searched", "could_not_determine")   # the rest come from the calls
RETURN_SCHEMA = {
    "name": RETURN_TOOL,
    "description": ("Send your finding to the coordinator, once, when you can name the responsible file or "
                    "cannot go on. It is the only thing that leaves your context: say what you could not "
                    "settle. A return that breaks the shape is refused and you send it again."),
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": list(_MODEL_FIELDS),
        "properties": {k: CONTRACT["properties"][k] for k in _MODEL_FIELDS},
    },
    "strict": True,
}


class WorkerStopped(Exception):
    """The coordinator stopped this worker (a cycle of waits). Raised from its next call, which ends its loop."""


class RoleTools:
    """One worker's tool surface."""

    def __init__(self, registry, roles: tuple[str, ...], agent_id: str, issue: int, lead, *, returns: bool = False,
                 expect: tuple[str, str] | None = None):
        self.registry = registry
        self.allowed = {tool_for(r) for r in roles}
        self.agent_id, self.issue, self.lead, self.returns = agent_id, issue, lead, returns
        self.expect = expect            # a writer's brief: (label, file), which its writes must match
        self.calls = 0                  # calls to the course's tools, offered or not: what the checker counts
        self.searched: list[str] = []   # queries and paths, each once, in order
        self.read: set[str] = set()     # files its read calls returned, normalised: a read that failed is not one
        self.accepted: dict | None = None
        self.sent = 0                   # returns sent, valid or not
        self.stopped = False            # set by the coordinator to stop this worker
        self.end_reason: str | None = None   # why its loop ended (token_budget, turn_limit, model_stopped, ...)

    @property
    def schemas(self) -> list[dict]:
        out = [s for s in self.registry.schemas if s["name"] in self.allowed]
        return out + [RETURN_SCHEMA] if self.returns else out

    def call(self, name: str, tool_input: dict, plan_step=None) -> ToolResult:
        if self.stopped:
            raise WorkerStopped(f"{self.agent_id} was stopped by the coordinator")
        if self.returns and name == RETURN_TOOL:
            return self._return(tool_input)
        if role_of(name):
            self._note(name, tool_input)
        if name not in self.allowed:
            return ToolResult(f"{name} is not one of your tools. You have: {', '.join(sorted(self.allowed))}.",
                              True, 0.0)
        if role_of(name) in OWN_ISSUE_ROLES and not self._own_issue(name, tool_input):
            return ToolResult(f"You are working on issue-{self.issue} only.", True, 0.0)
        refusal = self._against_brief(name, tool_input)
        if refusal:
            return ToolResult(refusal, True, 0.0)
        result = self.registry.call(name, tool_input)
        if role_of(name) == "read_file" and not result.is_error and isinstance(tool_input, dict):
            self.read.add(normalize_path(str(tool_input.get(arg("read_file", "path"), ""))))
        return result

    def file_read(self, file: str | None) -> str:
        """Whether the worker read the file it names: n/a for none (nothing to read), yes, or no."""
        shown = normalize_path(file) if file is not None else None
        return "n/a" if shown in (None, "none") else "yes" if shown in self.read else "no"

    def _own_issue(self, name: str, tool_input) -> bool:
        value = tool_input.get(arg(role_of(name), "number")) if isinstance(tool_input, dict) else None
        return str(value).strip().lower().lstrip("#").removeprefix("issue-") == str(self.issue)

    def _against_brief(self, name: str, tool_input) -> str | None:
        """A writer's write that departs from its brief is refused, never repaired: the model is
        told why and writes again. It runs before the registry, so a mismatch never reaches the tracker."""
        if not self.expect or not isinstance(tool_input, dict):
            return None
        label, file = self.expect
        role = role_of(name)
        if role == "apply_label":
            given = str(tool_input.get(arg(role, "label"), "")).strip().lower()
            if given != label:
                return f"The finding's label is {label}, not {given!r}. Apply the finding's label."
        elif role == "open_pr":
            if normalize_path(file) == "none":
                return "The finding's file is none: open no pull request."
            text = f"{tool_input.get(arg(role, 'title'), '')}\n{tool_input.get(arg(role, 'body'), '')}".lower()
            if file.lower() not in text and PurePosixPath(file).name.lower() not in text:
                return f"The pull request must name {file}."
        elif role == "comment":
            got = parse_triage_comment(str(tool_input.get(arg(role, "body"), "")))
            if got != (label, normalize_path(file)):
                return (f"The comment's first two lines must be 'label: {label}' and 'file: {file}'; "
                        f"yours read label {got[0]!r}, file {got[1]!r}.")
        return None

    def _note(self, name: str, tool_input) -> None:
        self.calls += 1
        role = role_of(name)
        key = {"search": arg("search", "query"), "read_file": arg("read_file", "path")}.get(role)
        value = tool_input.get(key) if key and isinstance(tool_input, dict) else None
        if value is not None and str(value) not in self.searched:
            self.searched.append(str(value))

    def _return(self, tool_input) -> ToolResult:
        """Validate the return against the contract, record it, and accept or refuse it."""
        self.sent += 1
        contract = ({**tool_input, "searched": list(self.searched), "calls_used": self.calls}
                    if isinstance(tool_input, dict) else tool_input)      # recorded as it arrived, never replaced
        problems = schema_errors(contract, CONTRACT)
        self.lead.trace.event("worker_return", worker=self.agent_id, contract=contract,
                              valid=not problems, errors=problems)
        if problems:      # rejected, never repaired: the model is told and sends it again
            return ToolResult("Refused, nothing was recorded. Send the return again, fixed: " + "; ".join(problems),
                              True, 0.0)
        if self.accepted is not None:   # one finding per worker: a later return is traced, never acted on
            return ToolResult("You have already returned a finding. Stop now.", True, 0.0)
        self.accepted = contract
        return ToolResult("Recorded. You are done: stop.", False, 0.0)

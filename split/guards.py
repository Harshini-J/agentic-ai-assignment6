"""The split's cheap checks (Lecture 6, slide 47). None of them coordinates anything: each is there
so you can see or check what happened. The replays in checks/check_06.py call the three classes
and functions below (checks/FORMATS.md, section 14.6); the return contract is split/roles.py.

  WaitGraph      who waits on whom; the cycle a new wait closes; the worker to stop to break it.
  Waits          the coordinator's use of it: every wait is a `wait` line in the trace, a cycle is
                 a `worker_stopped` line, and the victim is stopped.
  SharedState    compare-and-set on state agents share: a write names the version it read, and is
                 refused if the state has changed since; a key makes a retry land once.
  check_combined the end state against rules set before the run, with no answer key.
"""

from __future__ import annotations

import threading
from pathlib import PurePosixPath

from harness.formats import LABELS, normalize_path, parse_triage_comment


class WaitGraph:
    """Waits between agents. An edge waiter -> on stays until `done(on)` says that agent has finished."""

    def __init__(self):
        self.edges: dict[str, set[str]] = {}
        self._closed_by: str | None = None      # the waiter of the wait that last closed a cycle
        self._lock = threading.Lock()

    def wait(self, waiter: str, on: str, what: str = "") -> list[str] | None:
        """Record that `waiter` now waits on `on`. The cycle this wait closes, as the agents in it
        (the waiter first), or None."""
        with self._lock:
            self.edges.setdefault(waiter, set()).add(on)
            path = self._path(on, waiter)
            if path is None:
                return None
            self._closed_by = waiter
            return [waiter] + path[:-1]          # the path ends back at the waiter

    def _path(self, start: str, goal: str) -> list[str] | None:
        """A path of waits from `start` to `goal`, both included, or None."""
        stack, seen = [(start, [start])], set()
        while stack:
            node, path = stack.pop()
            if node == goal:
                return path
            if node in seen:
                continue
            seen.add(node)
            stack.extend((nxt, path + [nxt]) for nxt in sorted(self.edges.get(node, ())))
        return None

    def victim(self, cycle: list[str]) -> str:
        """The worker to stop to break the cycle: one of the cycle's agents, never the coordinator.
        The one whose wait closed the cycle if it is a worker, else the first worker in it."""
        workers = [a for a in cycle if a != "coordinator"]
        if not workers:
            raise ValueError(f"a cycle of the coordinator alone has no worker to stop: {cycle}")
        return self._closed_by if self._closed_by in workers else workers[0]

    def done(self, agent: str) -> None:
        """`agent` has finished: nothing waits on it any more, and it waits on nothing."""
        with self._lock:
            self.edges.pop(agent, None)
            for targets in self.edges.values():
                targets.discard(agent)


class Waits:
    """The coordinator's waits: each is a `wait` line in the trace, fed to the graph. A cycle is
    traced as a `worker_stopped` line, and `stop(victim)` is called to stop that worker."""

    def __init__(self, trace, stop=None, graph: WaitGraph | None = None):
        self.trace, self.stop, self.graph = trace, stop, graph or WaitGraph()

    def wait(self, waiter: str, on: str, what: str, turn: int) -> list[str] | None:
        self.trace.event("wait", waiter=waiter, on=on, what=what, turn=turn)
        cycle = self.graph.wait(waiter, on, what)
        if cycle:
            victim = self.graph.victim(cycle)
            self.trace.event("worker_stopped", worker=victim, reason="a cycle of waits: " + " -> ".join(cycle + cycle[:1]))
            if self.stop:
                self.stop(victim)
        return cycle

    def done(self, agent: str) -> None:
        self.graph.done(agent)


class SharedState:
    """State that agents share, with compare-and-set. `initial` is path -> content; each path is at
    version 1, and a path not there is at version 0 and empty."""

    def __init__(self, initial: dict[str, str]):
        self._files = {path: (content, 1) for path, content in initial.items()}
        self._applied: dict[str, bool] = {}     # key -> the answer its first write got: a retry lands once
        self._lock = threading.Lock()

    def read(self, agent: str, path: str) -> tuple[str, int]:
        """The content and its version."""
        with self._lock:
            return self._files.get(path, ("", 0))

    def write(self, agent: str, path: str, content: str, version: int, key: str | None = None) -> bool:
        """Compare-and-set: write only if `path` is still at `version`, the version the agent read.
        True when written; False when refused, leaving the content as it was. A write with a key it
        has already sent answers as it did the first time and writes nothing more."""
        with self._lock:
            if key is not None and key in self._applied:
                return self._applied[key]
            ok = self._files.get(path, ("", 0))[1] == version
            if ok:
                self._files[path] = (content, version + 1)
            if key is not None:
                self._applied[key] = ok
            return ok

    def content(self, path: str) -> str:
        with self._lock:
            return self._files.get(path, ("", 0))[0]


def _names(text: str, file: str) -> bool:
    """A pull request names a file when its title or body holds the path or the file's name."""
    text = (text or "").lower()
    return file.lower() in text or PurePosixPath(file).name.lower() in text


def check_combined(task, state: dict) -> list[str]:
    """The combined result's violations of the task's rules; [] when it passes.

    Read from the end state, never from what any agent said, and set before the run. For each
    issue: one comment, with a label line (one of the four labels) and a file line; exactly that
    label on the issue; one pull request naming the comment's file when the file is not none, and
    none when it is. It needs no answer key, so it catches parts that disagree with each other
    (a comment naming one file, its pull request another); it cannot tell a finding that is
    consistently wrong from a right one."""
    violations: list[str] = []
    for issue in task.issues:
        seen = state.get(issue) or state.get(str(issue))
        if not seen:
            violations.append(f"issue {issue}: no end state")
            continue
        comments, labels, prs = seen.get("comments") or [], seen.get("labels") or [], seen.get("prs") or []
        if len(comments) != 1:
            violations.append(f"issue {issue}: {len(comments)} comments, not one")
            continue
        label, file = parse_triage_comment(comments[0])
        if label is None or file is None:
            violations.append(f"issue {issue}: the comment has no {'label' if label is None else 'file'} line")
            continue
        if label not in LABELS:
            violations.append(f"issue {issue}: the comment's label {label!r} is not one of {list(LABELS)}")
        applied = sorted({str(x).strip().lower() for x in labels})
        if applied != [label]:
            violations.append(f"issue {issue}: the labels on the issue are {applied}, the comment's is {label!r}")
        file = normalize_path(file) or "none"
        if file == "none":
            if prs:
                violations.append(f"issue {issue}: {len(prs)} pull requests, where the comment's file is none")
        elif len(prs) != 1:
            violations.append(f"issue {issue}: {len(prs)} pull requests, not one, for the comment's file {file}")
        elif not _names(f"{prs[0].get('title', '')}\n{prs[0].get('body', '')}", file):
            violations.append(f"issue {issue}: the pull request does not name the comment's file {file}")
    return violations


__all__ = ["WaitGraph", "Waits", "SharedState", "check_combined"]

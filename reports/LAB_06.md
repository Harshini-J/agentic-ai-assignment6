# Assignment 6 · Split it, measure it, decide

Model: Anthropic, claude-sonnet-5, the same for every run.

## Part A · The gates, before you build

**The roles you considered, and what each would need from the others mid-task.**

**Roles:** a **coordinator** (receives the task, writes briefs, reads returns, holds no write tools), an **investigator** per issue (`issues_read`, `code_search`, `code_read_file`, `code_run_tests` only) and a **writer** per issue (`issues_label`, `pulls_open`, `issues_comment` only). I rejected a reviewer that re-checks the investigator's file: on the same model it shares the investigator's blind spots, and it would need the investigator's evidence, not just its answer, which means talking mid-task.

| Two roles | What one needs from the other while the task runs | How it would get it | What that costs |
|---|---|---|---|
| Coordinator and investigator | The investigator needs the issue number and its share of the token budget, once, before it starts. The coordinator needs the finding. | Through the lead, between rounds | A bottleneck at the lead. Whatever the return omits is lost: files ruled out, and whether the file was read or only inferred. All agents share one token ceiling, so an unenforced share lets one worker starve the rest. |
| Investigator and writer | The writer needs the label, the file (or `none`), a line on what to change for the PR body, and whether the file was read or is only a candidate. The investigator needs nothing back. | Through the lead: the investigator's return becomes the writer's brief | Direct messages would allow "are you sure?", but the writer would wait on the investigator and the full record would fill its window. Shared files add nothing: the investigator writes no state. |
| Coordinator and writer | The writer needs the finding, relayed. The coordinator needs to know what landed. | Through the lead, between rounds | The writer's report is not proof: what landed is verified from the tracker by code. A comment, once read, cannot be undone, so a bad brief has lasting effects. |
| Investigator and investigator (batch) | Nothing: the issues are unrelated and their tools are read-only. | None | None, apart from the shared token ceiling the coordinator divides. |
| Writer and writer (batch) | Nothing. Each writes under its own issue number and branch `repomind/issue-<n>`. | Shared tracker, keyed by issue | No write conflict. They share one reviewer queue: `open_pr` requires approval (`policy/autonomy.yaml`), so up to five PRs (one per issue whose file is not `none`) wait for one person. Part C's `scripted:approve-all` hides this cost from the measured wall-clock. |

- **For one issue:** every need is met by one return through the lead. The writer cannot start until the investigator returns, so the two never run at once: a pipeline, not a team. Parts that must talk are one task, not two. Gate 1 says no, because the label, PR and comment all come from the one finding and must agree: the comment's label is the applied label, and the PR names the comment's file.
- **For a batch of five:** the parts for gate 1 are the five issues, which need nothing from each other. Within each issue the investigator-to-writer dependency remains, so that split restricts tool access rather than enabling parallel work. The coordinator must pair five findings with the right five issues and divide the token budget. The shared constraints are the token ceiling and the reviewer queue.
- **Why one writer per issue:** each writer sees only one finding, so cross-issue mix-ups cannot happen inside a writer's context. The cost is ten workers per batch, each loading its own prompt and tool schemas, which Part C measures in the multiplier.

**The sketch** (text, or an image in `reports/`):

```
ONE ISSUE

                        runner: task, issue #n
                                   │
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │                     coordinator                      │
        └─────┬───────────┬─────────────────┬───────────┬──────┘
              │           ▲                 │           ▲
              │ (1)       │ (2)             │ (3)       │ (4)
              ▼           │                 ▼           │
        ┌─────┴───────────┴──────┐    ┌─────┴───────────┴──────┐
        │      investigator      │    │         writer         │
        │    read-only tools     │    │    write-only tools    │
        └────────────────────────┘    └───────────┬────────────┘
                                                  │ (5)
                                                  ▼
                                             ┌─────────┐       ┌───────────────────────┐
                                             │ tracker ├──────►│ combined-result check │
                                             └─────────┘  (6)  └───────────────────────┘

   (1) brief + budget share      (2) return, checked against the contract
   (3) the finding, relayed      (4) what the writer says it did
       as the writer's brief     (5) label, PR, comment
   (6) after the run, the combined-result check reads the tracker,
       not any agent's report

   The one dependency: investigator to writer (label, file, what to change,
   read or candidate), only through the coordinator, between rounds.
   Nothing flows back to the investigator. Shared: the run's one token ceiling.


BATCH OF FIVE

  ┌──────────────────────────────────────────────────────────────────────────────────────┐
  │  coordinator, round 1: writes five briefs, one per issue, each with its token share  │
  └───────┬─────────────────┬─────────────────┬─────────────────┬─────────────────┬──────┘
          │ (1) brief       │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼                 ▼
  ┌───────┴──────┐  ┌───────┴──────┐  ┌───────┴──────┐  ┌───────┴──────┐  ┌───────┴──────┐
  │ investigator │  │ investigator │  │ investigator │  │ investigator │  │ investigator │
  │    #4410     │  │    #4412     │  │    #4414     │  │    #4420     │  │    #4423     │
  └───────┬──────┘  └───────┬──────┘  └───────┬──────┘  └───────┬──────┘  └───────┬──────┘
    no arrows between investigators: read-only tools, unrelated issues
          │ (2) returns     │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼                 ▼
  ┌───────┴─────────────────┴─────────────────┴─────────────────┴─────────────────┴──────┐
  │     coordinator, round 2: reads five returns, checks each against the contract,      │
  │         pairs each finding with its issue number, writes five writer briefs          │
  └───────┬─────────────────┬─────────────────┬─────────────────┬─────────────────┬──────┘
          │ (3) one each    │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼                 ▼
  ┌───────┴──────┐  ┌───────┴──────┐  ┌───────┴──────┐  ┌───────┴──────┐  ┌───────┴──────┐
  │    writer    │  │    writer    │  │    writer    │  │    writer    │  │    writer    │
  │    #4410     │  │    #4412     │  │    #4414     │  │    #4420     │  │    #4423     │
  └───────┬──────┘  └───────┬──────┘  └───────┬──────┘  └───────┬──────┘  └───────┬──────┘
          │ (4) writes      │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼                 ▼
  ┌───────┴─────────────────┴─────────────────┴─────────────────┴─────────────────┴──────┐
  │               tracker, keyed by issue and by branch repomind/issue-<n>               │
  └───────────────────────────────────────────┬──────────────────────────────────────────┘
                                              │ (5) reads
                                              ▼
                                 ┌─────────────────────────┐
                                 │  combined-result check  │
                                 └─────────────────────────┘

  (5) after the run, the combined-result check reads the tracker, not any agent's report.
  No arrows between writers; up to five open_pr calls (one per issue whose file is not
  none) wait in one reviewer queue.
  Shared by every agent: the run's one token ceiling, split into shares by the coordinator.
  (Each writer's own report back to the coordinator is left off for space.)
```

**What each role returns, and what it cannot say** (for one issue and a batch of five).

| Role | Returns | Unable to say |
|---|---|---|
| Investigator | Label, file or `none`, what to change, status (`found`, `candidate` or `out_of_budget`), what it searched and did not, calls used, `could_not_determine` | Why it rejected other files (its context is discarded). Whether bug versus feature was a close call: a judgment, not a search fact. Anything it never examined. A bare `none` is ambiguous unless the contract separates a `question` issue from a search that found nothing. |
| Writer | The label, PR and comment it created | Whether the file is right: it has no read tools. Whether the finding was a candidate or verified, unless the brief says so. Whether its writes landed: only the tracker says that. |
| Coordinator | A run summary and the workers' returns | Whether the end state is correct: that is checked by code against the tracker, not by any agent. |

For a batch, the extra risk is a cross-issue mix-up: issue A's file on issue B's comment is **silent divergence**, where every worker succeeds and the whole is wrong. Each investigator knows only its own issue, so no return or per-worker check can catch it. Only the combined-result check on the tracker's end state can, when the mix-up leaves an issue's comment, label and PR disagreeing; a mix-up that is wrong but consistent needs the answer key in Part C's `check_task`.

**The four gates** (slide 46), in order, stopping at the first no.

| Gate | One issue | Why | A batch of five | Why |
|---|---|---|---|---|
| 1. The parts work mostly without talking | fail | The label, PR and comment all come from the investigator's one finding and must agree: the comment's label is the applied label, and the PR names the comment's file. One task done in sequence, not two. | pass | The parts are the five issues: unrelated, investigated with read-only tools, and written under separate issue numbers and branches. None needs another mid-task. |
| 2. Each part's result can be checked on its own | not_reached | Stopped at gate 1. | pass | Each issue can be checked alone from the tracker, with rules that need no answer key: one comment with label and file lines, that label applied, and a PR naming the comment's file unless it is `none`. A worker's own report is not that check: in the planted wrong end state every worker reported success, yet issue 4414's comment names `src/api/reports.ts` and its PR names `src/export/csv.ts`. Only a check read from the tracker after the coordinator finishes catches that, so Part B builds it. It catches parts that disagree, not a finding that is wrong throughout; the answer key in Part C's `check_task` is what catches that. |
| 3. A team buys what one agent cannot get more cheaply | not_reached | Stopped at gate 1. | pass, narrowly | Only speed counts here: five investigators running at once bring a batch's wall-clock closer to one issue's than to five. This holds only if the split really runs them at the same time. Room does not count, since one agent gets it more cheaply (compaction, an outside event log, a fresh context per issue, as arm S-plus does). Tools and models do not count either: the lecture rates specialisation by tool surface as strong, but one agent gets the same restriction more cheaply by being offered only read tools until its finding is fixed, then only write tools, as the planned way's executor (`ways/planned.py`) already offers one tool per step; and the model is fixed. Part C's wall-clock must show the speed. |
| 4. The result is worth the multiplier | not_reached | Stopped at gate 1. | fail | Nobody waits on the daily triage, so saved time is worth little, and with a person reviewing, up to five `open_pr` approvals queue behind one reviewer anyway. The deliverable is the same as arm S's, at the cost of a coordinator and ten workers. Anthropic reports about 15× a chat's tokens for multi-agent and about 4× for one agent, but those are averages on its own workload, not one task run both ways, so they are a prior; Part C measures mine. This flips if batches grow large or latency starts to matter. |

- **The benefit you are trying to buy, and the condition it needs:** The benefit I am buying is **parallelism**, which reduces wall-clock time when tasks are truly independent. The five issues in a batch meet this condition because they are unrelated and the investigators use only read tools. A single issue does not, since the writer must wait for the investigator's finding before starting. This benefit only exists if all five investigators actually run concurrently. I count it as bought only if Part C shows that arm M's batch wall-clock time is clearly lower than arm S's, approximately 60% or less. Otherwise, the additional workers provide no meaningful speed benefit. I am not relying on the other two benefits:

  - **Context isolation** keeps each worker's context small, and needs little communication. That holds in my design because every worker receives one brief and returns one result. It is probably the most reliable benefit of the split, but a single agent can achieve something similar at lower cost through compaction, an external event log, or a fresh context for each issue. Arm S-plus tests this alternative directly.

  - **Specialisation** is useful when roles have genuinely different requirements. My design provides tool-level specialisation: the investigator cannot perform writes, and the writer cannot search. However, both roles use the same model, held fixed, and a single agent could achieve similar restrictions by receiving only read tools until its finding is finalized. Therefore, I consider specialisation a secondary benefit rather than the main reason for splitting the task.

- **Your prediction, as committed in `reports/PREDICTIONS_06.md`, and its commit:** `00375b0`. About 2.0× arm S's tokens on single tasks and 1.3× on batches; a tie on single tasks and the split ahead by about one run in six on batches; arm S-plus matches the split. This agrees with gate 4's fail.

## Part B · The split

- The coordinator and the roles, and the tools each holds:
- Why they split by tool surface:
- The return contract, field by field, and which fields come from the worker's tool calls:
- Each worker's share of the budget, and what is held back:
- The five checks, where each is in your code:

## Part C · Measured

**The five constants** (slide 59): model, tools, budget, evaluator, task set.

**The results.**

| Arm | Kind | Passes / runs | Lowest and highest sweep | Tasks all three passed | Mean tokens | Mean wall-clock (s) |
|---|---|---|---|---|---|---|
| S | single | | | | | |
| S | batch | | | | | |
| M | single | | | | | |
| M | batch | | | | | |
| S-plus | single | | | | | |
| S-plus | batch | | | | | |

- Your multiplier (M over S), single and batch, beside the lecture's 15×:
- Whether S-plus's spend matched M's in fact, task by task:

**Slide 18's three questions**, for each kind of task.

| Question | One issue | A batch of five |
|---|---|---|
| Did the split spend more? | | |
| Does spending more raise the score? | | |
| Given the same budget, did one agent do as well? | | |

- What you would have claimed from arms S and M alone, and what you claim now:

**Every arm M run that failed.**

| Run | What each agent read, wrote and waited on | The first thing that went wrong | Anomaly | MAST category |
|---|---|---|---|---|
| | | | | |

## Part D · The decision

- One issue:
- A batch of five:
- The condition that would reopen it:
- The record: `decisions/0006-topology.md`

## AI assistance

Which tool, what it wrote, and what you checked:

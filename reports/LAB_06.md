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

- **The coordinator and the roles, and the tools each holds:**
  - **Coordinator** (`ways/split.py`): Plain code, with no model or tools. It appears in the trace as an agent with parent `null`. It prepares briefs, reads returns, and matches findings to issues using issue-specific worker names. It uses no tokens.
  - **Investigator**, one per issue: `issues_read`, `code_search`, `code_read_file`, `code_run_tests`, and a local `return_finding`. It can investigate but cannot make changes.
  - **Writer**, one per issue: `issues_label`, `pulls_open`, `issues_comment`. It can write but cannot read or search code.
  - **Flow:** Round 1 runs all investigators concurrently. Round 2 runs writers concurrently for findings with a valid label and file, using threads. Development runs used single issues, so Part C's batch wall-clock is the first test of this parallel execution. Every call passes through the registry and Assignment 5 hook, and comments pass through `with_disclosure` (`Disclosing`) before the registry.

- **Why they split by tool surface:** Tool restrictions control what an agent *can* do, while prompts only give instructions. An investigator cannot modify the tracker, and a writer receives only a structured finding, not the issue text. `RoleTools` enforces this in code: only assigned tool schemas are available, calls to other tools or issues are refused, and writes are checked against the writer's brief. This includes the label, PR file (or no PR for `none`), and the comment's first two lines. Invalid writes are refused, not repaired. However, free-text fields still reach the writer, and one agent could achieve similar restrictions using read-only tools until its finding is finalized. I therefore treat tool separation as a secondary benefit.

- **The return contract, field by field, and which fields come from the worker's tool calls:** Defined before the roles in `split/contract.schema.json`, validated on every return, and recorded as a `worker_return` trace entry. Invalid returns are refused and requested again, never repaired. Non-object returns are recorded as received, and only the first valid return is used.

  | Field | Holds | From |
  |---|---|---|
  | `result` | `label` (or `unknown`); `file`: path, `none` for a question, or `null` if undetermined; `what_to_change`; `evidence` | Model |
  | `status` | `found`, `candidate`, or `out_of_budget` | Model |
  | `not_searched`, `could_not_determine` | What was not investigated and what could not be resolved | Model |
  | `searched`, `calls_used` | Queries and paths examined, recorded once; actual course-tool calls | **Harness, from tool calls** |

  The schema allows an undetermined label or file only with `out_of_budget`, distinguishing `none` (no file change) from `null` (not determined). `writable()` also rejects `unknown` and `""`. Checks outside the schema never change `valid`: they record `no_return` when no valid return is produced and `unread_finding` when a `found` result names an unread file. The writer's brief states whether the file was read, based on the harness record. **What the contract loses:** Why other files were rejected, the investigator's reasoning, and how close the bug-versus-feature decision was. This is the cost of isolation.

- **Each worker's share of the budget, and what is held back:** `ctx.budget` (5B for a batch) is divided into fixed shares per issue: 60% for the investigator and 25% for the writer, enforced as worker token limits. At B = 250,000, these are 150,000 and 62,500 tokens, leaving 37,500 (15%) as slack (`budget_plan`). This is not a separate reserve; it allows a worker to exceed its share by one call while keeping the run below its ceiling. Shares are static: a worker that finishes early passes nothing on. The coordinator uses no tokens. Investigators have 12 model calls, writers have 8, and both have a 180-second limit. The investigator's brief states its calls and its token share so it can return `candidate` or `out_of_budget` before being stopped. `budget_check` records total usage. In development, investigators used about 25,000 of 150,000 tokens and writers about 10,000 of 62,500.

- **The five checks, where each is in your code:**

  | Check | Where | In short |
  |---|---|---|
  | Return contract | `split/contract.schema.json`, `RoleTools._return` (`split/roles.py`) | Validates and traces returns; invalid ones are refused. |
  | Deadlock detection | `WaitGraph`, `Waits` (`split/guards.py`), used in `ways/split.py` | Records each wait; a cycle stops one worker, not the coordinator. Workers never wait on each other; replay detects the cycle at turn 1. |
  | Combined result | `check_combined` (`split/guards.py`), after the last write | Checks tracker state against predefined rules; catches inconsistent outputs, not consistently wrong findings. |
  | Idempotency and compare-and-set | Assignment 3 write keys; `SharedState` (`split/guards.py`) | Refuses stale writes, and a retried write lands once. Unused at run time because agents share only the issue-keyed tracker; replay rejects Worker B's stale write. |
  | One trace | `agent`/`parent` on every line; `agent_tokens`, `budget_check` | Records agent relationships, waits, and token usage, which sums to the run total. |

- **Tried before measuring** (development issues 4191 and 4192, B = 250,000): Both passed the grounded check. Each investigator's first return was valid and `found`, with the file read. No writes were refused, and both combined checks passed. Each run used about 35,000 tokens, took 28 seconds, and cost $0.08. This confirms the implementation works with a real model, not its overall accuracy; Part C measures that. The writer's brief checks never refused a write in any run, so I tested them directly with nine cases: three writes to another issue, a wrong label, a PR and comment naming the wrong file, and three correct writes. The six invalid writes were refused, and the scripted runs showed correct writes pass.

## Part C · Measured

**The five constants** (slide 59): model `claude-sonnet-5`; tools `schemas_sha` `703c0002892f27ec`; budget 250,000 tokens per issue (1,250,000 per batch), with one ceiling per task for arms S and M, while arm S-plus received each task's mean arm M spend by design; evaluator `checks_sha` `55abcd67e6a3b208` (`eval/check_task.py`, `eval/check_triage.py`, and the answers), with reviewer `scripted:approve-all`; and task set, the eight tasks in `fixtures/tasks6/` (`batch-a`, `batch-b`, `one-4402`, `one-4403`, `one-4405`, `one-4406`, `one-4409`, `one-4413`). The runner recorded these in every `run_start` line, and the same constants covered all 72 runs. The scripted reviewer also removed human waiting time. Eleven S-plus runs (sweep 2's issues 4406, 4409, and 4413, plus all of sweep 3) failed on their first model call due to my API account's usage limit, using 0 tokens. I moved them to `runs/discarded/` because the harness reruns only runs a quota or rate limit stopped, and it counts a run that ended with an error, as these did, as finished. I reran them with a new key but the same model, code, and command. None of the five constants changed.

Every arm used `--jobs 1`, and no run ended rate-limited. The harness retries a refused call silently and the trace does not record it, so I cannot rule out a short retry wait; across 919 measured model calls the slowest single call took 14.5 s (medians 1.7 to 2.5 s by arm) and none took over 20 s, so waits did not dominate, and the wall-clock figures reflect the design, not contention.

**The results.** "Lowest and highest sweep" counts tasks passed in a sweep (out of 6 for singles, 2 for batches).

| Arm | Kind | Passes / runs | Lowest and highest sweep | Tasks all three passed | Mean tokens | Mean wall-clock (s) |
|---|---|---|---|---|---|---|
| S | single | 18 / 18 | 6 and 6 | 6 of 6 | 49,547 | 13.6 |
| S | batch | 5 / 6 | 1 and 2 | 1 of 2 | 174,196 | 63.8 |
| M | single | 18 / 18 | 6 and 6 | 6 of 6 | 39,516 | 20.1 |
| M | batch | 3 / 6 | 1 and 1 | 1 of 2 | 221,495 | 24.8 |
| S-plus | single | 18 / 18 | 6 and 6 | 6 of 6 | 28,927 | 13.9 |
| S-plus | batch | 4 / 6 | 1 and 2 | 1 of 2 | 208,642 | 95.3 |

Per task (passes of 3 · mean tokens · mean wall-clock), and S-plus's spend as a share of its budget (arm M's mean):

| Task | Arm S | Arm M | Arm S-plus | S-plus over M |
|---|---|---|---|---|
| one-4402 | 3/3 · 51,248 · 15.8 s | 3/3 · 47,993 · 21.7 s | 3/3 · 31,243 · 14.1 s | 65% |
| one-4403 | 3/3 · 46,763 · 12.0 s | 3/3 · 40,986 · 19.6 s | 3/3 · 31,759 · 15.4 s | 77% |
| one-4405 | 3/3 · 47,630 · 12.8 s | 3/3 · 35,217 · 18.2 s | 3/3 · 28,568 · 12.7 s | 81% |
| one-4406 | 3/3 · 53,653 · 16.4 s | 3/3 · 40,888 · 23.7 s | 3/3 · 30,483 · 17.4 s | 75% |
| one-4409 | 3/3 · 49,484 · 12.8 s | 3/3 · 35,759 · 18.3 s | 3/3 · 25,988 · 11.2 s | 73% |
| one-4413 | 3/3 · 48,504 · 11.7 s | 3/3 · 36,255 · 18.9 s | 3/3 · 25,523 · 12.6 s | 70% |
| batch-a | 2/3 · 200,093 · 70.9 s | 0/3 · 213,779 · 25.4 s | 1/3 · 207,314 · 100.4 s | 97% |
| batch-b | 3/3 · 148,299 · 56.8 s | 3/3 · 229,211 · 24.2 s | 3/3 · 209,971 · 90.1 s | 92% |

- **My multiplier (M over S):** 0.80 on single tasks and 1.27 on batches, from each run's `run_end` total. The split used fewer tokens on all six single tasks, by 6% to 28%, but more on both batches: 7% more on batch-a and 55% more on batch-b, so the batch figure is mostly batch-b. The lecture's about 15× is Anthropic-reported, for typical use on its own workload, measured against a chat, where the same source puts one agent at about 4×; mine compares one split design against one agent on one task set, so the two are not comparable. **Wall-clock:** the split was slower on every single task (18 to 24 seconds against 12 to 16) because its two workers run one after the other, as Part A's gate 1 expected, and faster on batches, taking 39% of arm S's time.
- **Whether S-plus's spend matched M's in fact, task by task:** each S-plus budget was set to arm M's mean token usage for that task, and the budgets agree to the token (arm M's column in the table). On batches S-plus used 92% to 97% of its budget, in 6 or 7 attempts per batch of five issues (1.2 to 1.4 per issue, at about 30,000 to 36,000 tokens each): one attempt on every issue and one or two more, sent to the issues the answers left least settled; on batch-a, one of the extra attempts went to issue 4412 in all three sweeps. On singles it used 65% to 81%, and every one of the 18 runs made exactly one attempt: an attempt costs 24,000 to 32,000 tokens (two ran long, at 39,135 and 43,741), which leaves too little for a second within budgets of 35,000 to 48,000. So the vote could decide only one or two issues per batch and none of the singles. S-plus uses a prompt that matches the investigator's apart from its opening paragraph, the same return contract and the same read-only tools, with the writes done by code, so it differs from arm M mainly in structure, while its differences from arm S go beyond the token budget.

**Slide 18's three questions**, for each kind of task.

| Question | One issue | A batch of five |
|---|---|---|
| Did the split spend more? | No. M used 39,516 tokens against S's 49,547 (0.80×). | Yes. M used 221,495 tokens against S's 174,196 (1.27×). |
| Does spending more raise the score? | No. All three arms passed 18/18: S-plus at 28,927 tokens, M at 39,516 and S at 49,547. The score was at its ceiling. | No. S passed 5/6 at 174,196 tokens, S-plus 4/6 at 208,642 and M 3/6 at 221,495. The sample is small, and every failed batch run, in every arm, got issue 4412 wrong. |
| Given the same budget, did one agent do as well? | Yes. S-plus passed 18/18 on 73% of M's actual spend. | Yes. S-plus passed 4/6 to M's 3/6 on 94% of M's spend. A gap of one run is within noise, so I read this as "as well", not "better". |

The second question is the least clean: the three arms differ in more than budget (M splits the work across agents, and S-plus has a different prompt, a read-only tool surface and writes made by code), so I read it as "none of these spends, from 28,900 to 49,500 tokens on singles and from 174,000 to 221,000 on batches, bought a higher score".

The split showed no gain in correctness. The only advantage one agent did not match was batch speed: M took 39% of arm S's wall-clock time. That fits the investigators running at once, not extra spending, since S-plus spent 94% of M's tokens and took 95.3 s.

- **What I would have claimed from arms S and M alone, and what I claim now:**
  - **From S and M alone:** on single issues, the split got the same accuracy on 20% fewer tokens, which could look like a benefit of the team design. On batches, it was faster but spent more and scored lower.
  - **Now:** S-plus, one agent with read-only attempts and writes made by code, also passed 18/18, on 73% of the split's tokens. So the saving does not come from having several agents. From my two development runs, I estimate it comes from smaller calls, fewer tool definitions and shorter context histories, all of which one agent can also use.
  - **On batches:** the split's lower score is not explained by spending too little. One agent given the same budget did at least as well.

**Every arm M run that failed.** Three runs failed, all batch-a, all on issue 4412 (the right answer is `question`, file `none`); the other four issues in each passed.

| Run | What each agent read, wrote and waited on | The first thing that went wrong | Anomaly | MAST category |
|---|---|---|---|---|
| `split-batch-a-s01-683f15` | `investigator-4412` read the issue (a reporter asking how to configure a probe that returned 200 with `degraded`), searched `/api/v1/health` and `degraded`, and read `src/api/health.ts` (4 calls). It returned `found` / `bug` / `src/api/health.ts`, but its `could_not_determine` said the intended fix was a policy decision that the code alone does not resolve. `writer-4412` received only the brief and applied the label, opened a PR, and posted a matching comment. Only the coordinator waited: on the investigators in round 1 and on the writers in round 2. | The investigator classified a question as a bug, even though its own return acknowledged that the code could not resolve the decision. | none (the writer correctly followed an incorrect finding) | `task_verification` |
| `split-batch-a-s02-2d111c` | Same investigation (4 calls), but `could_not_determine` questioned whether returning 200 for a degraded state was intentional. | The same incorrect classification. | none | `task_verification` |
| `split-batch-a-s03-7951f6` | Same investigation, with an additional `healthRouter` search (5 calls). `could_not_determine` questioned whether degraded-as-200 was a documented design decision. | The same incorrect classification. | none | `task_verification` |

These three runs show the same underlying cause, so I count them as one finding. Nothing checked for contradictions within the investigator's return. The contract allows `status: found` even when `could_not_determine` identifies the unresolved question that determines whether the issue is a bug or simply a question. The schema, the writer's brief checks and the combined-result check all passed, because they verify structure and consistency, not correctness against an answer key. A secondary interpretation is system design, since the contract permits this combination and the writer can only follow the finding. I rank it second because both roles behaved as designed. The mistake was not unique to the split: arm S also missed issue 4412 in 1 of its 3 batch-a runs, and arm S-plus's attempts answered `bug` in 5 of their 6 tries.

## Part D · The decision

- One issue:
- A batch of five:
- The condition that would reopen it:
- The record: `decisions/0006-topology.md`

## AI assistance

Which tool, what it wrote, and what you checked:

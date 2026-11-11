# 0006 · Topology: one agent or a split

**Status:** Decided, 2026-11-09. RepoMind remains a single-agent system. The split (`lab-06-split`) was tested but will not be merged.

## What I tested

I compared a coordinator with one investigator (read-only tools) and one writer (write-only tools) per issue against a single agent (arm S) and a single agent given the split's measured token budget (arm S-plus: read-only attempts, voting, and writes performed by code). I used eight tasks across three sweeps: six single issues and two batches of five.

**The gates, before building:**

| Gate | One issue | A batch of five |
|---|---|---|
| 1. The parts work mostly without talking | fail | pass |
| 2. Each part's result can be checked on its own | not_reached | pass |
| 3. A team buys what one agent cannot get more cheaply | not_reached | pass, narrowly (speed only) |
| 4. The result is worth the multiplier | not_reached | fail |

**The prediction** (`reports/PREDICTIONS_06.md`, commit `00375b0`, before any split run): I expected the split to use about 2.0× arm S's tokens on singles and 1.3× on batches, tie on singles, and perform better by roughly one run in six on batches. I also expected batch wall-clock time to be 60% of arm S's or less, with arm S-plus performing as well as the split.

## What I found

**The five constants**, unchanged across all 72 runs: model `claude-sonnet-5`; tools `schemas_sha` `703c0002892f27ec`; budget 250,000 tokens per issue (1,250,000 per batch) for arms S and M, with arm S-plus receiving arm M's mean spend per task; evaluator `checks_sha` `55abcd67e6a3b208`, with reviewer `scripted:approve-all`; and task set `batch-a`, `batch-b`, `one-4402`, `one-4403`, `one-4405`, `one-4406`, `one-4409`, `one-4413`.

| Arm | Single: passes · mean tokens · wall-clock | Batch: passes · mean tokens · wall-clock |
|---|---|---|
| S, one agent | 18/18 · 49,547 · 13.6 s | 5/6 · 174,196 · 63.8 s |
| M, the split | 18/18 · 39,516 · 20.1 s | 3/6 · 221,495 · 24.8 s |
| S-plus, one agent at M's spend | 18/18 · 28,927 · 13.9 s | 4/6 · 208,642 · 95.3 s |

**Multiplier (M over S):** 0.80 on singles and 1.27 on batches. These results are not directly comparable with the lecture's 15× figure, which comes from Anthropic's average against a chat on its own workloads.

**The three questions:**

| | One issue | A batch of five |
|---|---|---|
| Did the split spend more? | No (0.80×) | Yes (1.27×) |
| Does spending more raise the score? | No: all arms passed 18/18, reaching the ceiling | No: S spent the least and scored highest |
| Given the same budget, did one agent do as well? | Yes: 18/18 using 73% of M's spend | Yes: 4/6 versus M's 3/6, using 94% of M's spend |

**Against the prediction:** The batch multiplier (1.27× versus 1.3×), speed (39% of arm S's wall-clock versus the predicted 60% or less), and S-plus matching the split were consistent with my predictions. On singles, however, the split used fewer tokens rather than 2.0× more, and the saving cannot be credited to the team because S-plus used even fewer. On batches, the split did not perform better; it passed two fewer runs than arm S. All three M failures came from the same misreading of issue 4412, where a question was classified as a bug even though the investigator's `could_not_determine` expressed uncertainty. No check compared the finding against that uncertainty (MAST: task verification). Arm S missed 4412 once and S-plus twice, so the handoff itself was not the failure. With only three runs per arm, I cannot conclude that splitting improved or reduced accuracy.

## The decision

- **One issue: one agent.** Gate 1 fails because the label, PR, and comment all depend on one finding. The split becomes a sequential pipeline that is slower (20.1 s versus 13.6 s) without improving correctness. A single agent also matched and exceeded its token savings.
- **A batch of five: one agent.** The split achieved the speed benefit predicted by gate 3, taking 24.8 s instead of 63.8 s, but provided no other clear advantage. It used 27% more tokens and passed fewer runs, while a single agent given comparable spending performed at least as well. Daily triage has no strict deadline, and human PR approvals would still queue behind one reviewer. Gate 4 therefore fails because the speed benefit does not justify the additional cost.

## What would reopen it

I would reconsider the batch decision for **at least 20 independent issues, each with its own test that a worker can run to verify its answer**, executed concurrently with the same constants and three sweeps. The return contract must first prevent a `found` result from containing a non-empty `could_not_determine`. The split would then need to (a) pass at least as many tasks as arm S and more than S-plus at the split's measured spending, (b) use no more than 1.1× arm S's tokens, and (c) finish within 50% of arm S's wall-clock time. I would also reconsider if a triage deadline existed that arm S's serial execution (12.8 s per issue in a batch) could not meet but the split could.

**Does my batch result speak to it?** Only partly. The batches contained independent issues, and investigators ran concurrently, reducing wall-clock time to 39% of arm S's, which satisfies condition (c). However, the split failed conditions (a) and (b). The issues also lacked individual tests that workers could run to verify their findings. Correctness was evaluated afterward using an answer key, while the combined check only verified consistency. This allowed issue 4412's incorrect finding to pass through every check in the run. The experiment therefore demonstrates a speed benefit, not a correctness benefit. Whether per-issue verification would improve the results remains untested. These findings argue against splitting batches of five but do not establish what would happen with larger batches.

## What each choice loses

- **By splitting:** 27% more tokens per batch; the investigator's reasoning, which the return contract does not preserve, including why files were rejected and how uncertain a decision was; a handoff that can faithfully carry an incorrect finding; eleven agents to trace and debug per batch instead of one; and slower execution on single issues.
- **By not splitting:** The batch speed advantage (approximately 39 seconds saved per batch of five, potentially more for larger batches) and code-enforced tool separation, where investigators cannot write and writers cannot search. However, one agent can still use a fresh context for each issue, as S-plus demonstrated, and can approximate the same tool restrictions by allowing only read tools until the finding is finalized.

## Limits

There were only six batch runs per arm across two batch tasks, and issue 4412 accounts for the entire score difference. Arm S classified 4412 correctly in 2 of 3 runs, while the investigator and S-plus, using nearly identical prompts, were correct only once in nine attempts (three investigator runs and six S-plus attempts). This means prompt effects cannot be separated from topology effects. S-plus also differs from S in its prompt, tool access, and comments posted by code, so their comparison changes more than the budget. The experiment used one model, one task set, and batches of five.

`ARCHITECTURE.md` remains unchanged: RepoMind stays a single-agent system. That is the outcome of this experiment.

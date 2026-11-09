# Predictions for Assignment 6, committed before any run of my split

Model: claude-sonnet-5, held fixed throughout. I wrote these predictions before running the split so that the experiments would test my original expectations.

## 1. How many times arm S's tokens will my split spend per task?

- **Single tasks: about 2.0×.** The investigator performs roughly the same work as arm S on one issue, including reading the issue, searching the code, and examining the relevant file. However, the split adds overhead because the coordinator must prepare a brief and read the return, the writer loads its own prompt and tool schemas, and the investigator needs an additional call to report its findings. For a task with only about ten steps, I expect this overhead to be significant.
- **Batch tasks: about 1.3×.** Arm S handles all five issues in one growing context, so its input token usage increases as the task progresses. The split gives each issue a fresh, smaller context, which should reduce repeated context costs and offset much of the additional worker overhead. I still expect the split to use slightly more tokens, although a result close to 1× would not surprise me.

## 2. Which will pass more tasks, arm S or arm M, and by roughly how much?

- **Single tasks: a tie, within one pass out of 18 runs.** A single issue is manageable for one agent, so I do not expect the split to improve correctness. Instead, the handoff between investigator and writer introduces another opportunity to lose information.
- **Batch tasks: M ahead by about one run out of six.** Arm S must track five different issues in the same context, which increases the chance of mixing up information later in the batch. The split's separate contexts should reduce this risk, although mistakes in the coordinator's issue assignments could cancel out the improvement.
- **Wall-clock (batch):** I expect arm M to take approximately 60% or less of arm S's time, provided the five investigators actually execute concurrently.

## 3. Will arm S-plus, one agent given my split's spend, do as well as the split?

- **Single tasks: yes.** If the split does not outperform arm S, giving a single agent additional resources should achieve at least comparable results.
- **Batch tasks: yes, probably.** A single agent using the same token budget for multiple attempts and selecting an answer through voting should perform about as well as the split. Even if the split performs slightly better on batches, I expect arm S-plus to close that gap.

Overall, I predict that the split will use more tokens while achieving roughly the same correctness. If the results support this, the additional spending rather than the multi-agent design itself will be the main factor to consider.

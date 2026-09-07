# CLAUDE.md — Crux

Project-wide instructions for every agent (coder, tester) dispatched on this
repo. This file didn't exist before, which is why coders implemented tickets
correctly but never pushed the branch or updated the issue — nothing told
them to. See Commander housekeeping around issues #201/#202 for the failure
mode this file exists to close.

## Branching workflow

- `develop` — integration branch. All finished, tester-verified work lands
  here. **Never commit directly to `main`.**
- `main` — production. Only the human promotes `develop` → `main`, after UAT
  sign-off.
- `feature/<issue-N>-<slug>` — one branch per ticket, cut from `develop`,
  includes the issue number. Coders create these; nobody merges feature
  branches straight to `main`.

## Agent lifecycle

- **Coder**: create the feature branch off `develop`, implement the ticket,
  push the branch, label the issue **SIT**, and leave a comment on the issue
  summarizing what shipped. Do **not** merge.
- **Tester**: check out the feature branch, verify every acceptance
  criterion, post a test report as an issue comment, then **merge to
  `develop`** and label the issue **UAT**.
- **Human**: reviews UAT, signs off, and promotes `develop` → `main`. This is
  the only path code reaches production.

If a step is skipped — a coder implements and commits locally but never
pushes/labels, or a tester verifies but never merges — the ticket stalls
invisibly: the work exists but GitHub never finds out. Do every step, in
order, every time, even when the work already exists from a prior session —
finding pre-existing local commits does not excuse pushing them and
labeling the ticket.

**Headless dispatch has no notification mechanism.** You are run via `claude
-p`, not an interactive session — there is no later turn and nothing resumes
you. If you run tests or a merge via `run_in_background: true`,
`ScheduleWakeup`, or any other async/polling pattern and then end your
response, the process simply exits and the work is lost — the ticket will
show as "verified" in your own reasoning but nothing will have actually
happened on GitHub or `develop`. Run the full suite and the merge
**synchronously, in the same turn**, and wait for the command to return
before writing your final report. This exact failure stalled issue #204:
the tester said "both test suites are running in the background, I'll pick
this back up once they finish" — but headless dispatch has no "once they
finish," so nothing ever did.

## Tests

Tests must not make live HTTP calls — use an in-process test client. The bar
for any change is adding no NEW test failures against `develop`'s current
baseline, not reaching zero (pre-existing failures are not your problem
unless the ticket is specifically about one of them).

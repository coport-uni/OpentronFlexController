# claude_test

Debug and diagnostic scripts. Nothing here is part of CI. Production
tests live in [`tests/`](../tests/).

Per CLAUDE.md §8 these scripts are exempt from the 80-column limit and
from mandatory docstrings. They are **not** exempt from the Verification
Gate of §5.1.

| File | What it does | What was learned |
|---|---|---|
| `show_error_detection.py` | Feeds each deliberately broken protocol and deck configuration to `FlexController` and prints the error it reports, so detection can be read directly instead of inferred from a passing test. | Faults surface at three different layers, not one: a syntax error is refused by `POST /protocols` with HTTP 422 before any analysis exists; an undefined labware and a slot collision are caught by the analysis; a missing deck fixture passes analysis entirely and only fails once the run reaches the missing area. Spec §7 files all of these under "analysis error", which is accurate only for the middle group. |
| `audit_mit_convention.py` | Audits the repository against CLAUDE.md §2, checking what ruff cannot: docstring presence and Google sections, verb-shaped function names, noun-shaped class names, English-only source, and continuation-line operator placement. Exits non-zero on any finding. | A style checker must be written against tokens, not regexes. A first regex version reported 94 findings of which 87 were phantom — `or` matched inside `error`, `floor`, and `operator`, docstring prose was read as code, and pytest fixtures were asked for `Args:` sections that would document a call that never happens. Genuine findings: six naming faults, all in this directory. |

## Changes to the audit's vocabulary

`audit_mit_convention.py` recognises verbs from a hand-kept set, and its
own comment says that set is "the vocabulary the codebase uses; anything
outside it is reported for a human to judge rather than auto-failed". So
a `naming-verb` finding is a question, not a verdict, and the answer is
sometimes that the word is a perfectly good verb the list had not met
yet. Widening the set is then the fix; renaming the function to satisfy
the list would make the code worse to serve the checker.

| Date | Added | Prompted by |
|---|---|---|
| 2026-08-18 | `collect`, `write` | `FlexController.collect_labware_files` and the `write_definition` test helper |

Anything reported that is **not** a verb still has to be renamed. The
point of the list is to make that judgement explicit, not to wave it
through.

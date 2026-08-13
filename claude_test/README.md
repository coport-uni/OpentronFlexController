# claude_test

Debug and diagnostic scripts. Nothing here is part of CI. Production
tests live in [`tests/`](../tests/).

Per CLAUDE.md §8 these scripts are exempt from the 80-column limit and
from mandatory docstrings. They are **not** exempt from the Verification
Gate of §5.1.

| File | What it does | What was learned |
|---|---|---|
| `show_error_detection.py` | Feeds each deliberately broken protocol and deck configuration to `FlexController` and prints the error it reports, so detection can be read directly instead of inferred from a passing test. | Faults surface at three different layers, not one: a syntax error is refused by `POST /protocols` with HTTP 422 before any analysis exists; an undefined labware and a slot collision are caught by the analysis; a missing deck fixture passes analysis entirely and only fails once the run reaches the missing area. Spec §7 files all of these under "analysis error", which is accurate only for the middle group. |

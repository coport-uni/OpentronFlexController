# LearnedPatterns

Lessons carried forward from completed work, so they are reused rather
than rediscovered. Format and categories follow CLAUDE.md §10.

---

## §1. Recurring Issues

**Behaviour is asserted where it is convenient, not where it happens**
- **Problem**: Three integration tests failed on the first run — the
  staging-slot check, the deck-fixture check, and the syntax-error
  check. All three asserted the layer the spec named rather than the
  layer the robot actually uses.
- **Cause**: The spec's test plan was written from a model of
  robot-server, and the model was wrong in three places.
- **Fix**: Probed each behaviour directly with `curl` before rewriting
  the assertion, then asserted the observed layer and documented the
  deviation in the test docstring.
- **Rule**: Always confirm where a system reports a fault before writing
  a test that asserts it; a green test on a guessed layer is worth less
  than a red one. (from ToDo#1 D)

---

## §2. Solved Gotchas

**robot-server deduplicates identical protocol uploads**
- **Problem**: A protocol uploaded under a deliberately broken deck
  configuration came back clean, because the robot returned an analysis
  computed earlier under a good configuration.
- **Cause**: `POST /protocols` keys on file content. Identical bytes
  yield the existing protocol record and may reuse its analysis.
- **Fix**: Appended a unique trailing comment to the protocol before
  uploading it in any test whose result depends on external state
  (`unique_copy` in `tests/test_integration_dev_server.py`).
- **Rule**: Never assume an upload produced a fresh analysis; make the
  bytes unique whenever the expected result depends on server state.
  (from ToDo#1 D, TC-09)

**A file-type runtime parameter must be uploaded before the protocol**
- **Problem**: The protocol cannot be analysed without its CSV.
- **Cause**: `csv_data` is passed by file identifier, so the identifier
  must exist before the protocol that references it is uploaded.
- **Fix**: `upload_data_file` runs before `upload_protocol` and records
  the identifier for both the upload form and the run body.
- **Rule**: Always upload file-type parameters first, and send the same
  values at upload and at run creation — a mismatch triggers
  re-analysis and silently invalidates the gate just passed.
  (from ToDo#1 C, TC-05)

**The gripper path needs more than 96 transfers to appear**
- **Problem**: TC-07 requires a gripper `moveLabware` command, but the
  analysis of a 3-row CSV contained none.
- **Cause**: The protocol swaps tipracks only when the first is
  exhausted. Tips consumed are one for diluent plus one per data row, so
  fewer than 96 rows never triggers the swap.
- **Fix**: Generated a 96-row CSV (`data/od_normalization_96.csv`) and
  used it for the TC-07 analysis; two `usingGripper` moves then appear.
- **Rule**: Always size test input to the code path being verified, not
  to what runs fastest. (from ToDo#1 D, TC-07)

---

## §3. Library Quirks

**Protocol analysis ignores the deck configuration**
- **Problem**: Removing the waste chute fixture from `cutoutD3` produced
  a clean analysis and a successfully created run.
- **Cause**: robot-server analyses a protocol without reference to the
  deck configuration. The mismatch is only detected when the run reaches
  the missing addressable area.
- **Fix**: TC-09 now drives the run to completion and asserts
  `status == "failed"` with `AreaNotInDeckConfigurationError`.
- **Rule**: Never treat a clean analysis as proof the deck can serve the
  protocol; the two are checked independently.
  (from ToDo#1 D, TC-09)

**A Python syntax error is refused at upload, not at analysis**
- **Problem**: `verify_only` raised `TransportError` instead of
  returning a failed verdict for an uncompilable protocol.
- **Cause**: `POST /protocols` compiles the file during the request and
  answers HTTP 422 `ProtocolFilesInvalid`. No protocol, analysis, or run
  is created.
- **Fix**: The test asserts the 422 and its body, which names the file
  and the offending line.
- **Rule**: Always expect protocol faults at one of three layers —
  upload (422), analysis (`errors`), or run (`failed`) — and handle all
  three. (from ToDo#1 D)

**The pipette load name never appears in robot responses**
- **Problem**: TC-07 looks for `flex_96channel_1000` in the analysis;
  the string is absent.
- **Cause**: `flex_96channel_1000` is the Python API load name. The
  robot reports `p1000_96` in analyses and `p1000_96_v3.7` from
  `/instruments`.
- **Fix**: Asserted `p1000_96`, with a comment recording the mapping.
- **Rule**: Always verify identifier strings against a real response
  before asserting on them; API-side and robot-side names differ.
  (from ToDo#1 D, TC-07)

---

## §4. Workflow Lessons

**A lint hook must run from the project root**
- **Problem**: The `post-write-lint.sh` hook copied from CommonClaude
  failed on every Python write with a TOML parse error pointing at
  `/tmp/ruff.toml`, a stale unrelated file.
- **Cause**: Ruff resolves configuration starting from the working
  directory, and the hook inherited whatever directory it was invoked
  in.
- **Fix**: Added `cd "${CLAUDE_PROJECT_DIR:-...}"` before the ruff calls.
- **Rule**: Always pin a hook's working directory; never rely on the
  directory it happens to inherit. (from ToDo#1 A)

**Encode formal waivers in the tool, not in bypasses**
- **Problem**: The lint hook blocked a `claude_test/` script over the
  80-column limit that CLAUDE.md §8 explicitly waives.
- **Cause**: The waiver lived only in prose; the linter had never been
  told.
- **Fix**: Added a `per-file-ignores` entry for `claude_test/*` in
  `ruff.toml`, citing the section.
- **Rule**: Always express a documented exception as configuration; a
  waiver a tool cannot see becomes an override habit.
  (from ToDo#1 A)

---

**Carrying an error detail is not the same as showing it**
- **Problem**: A protocol with a syntax error was reported to the
  operator as `TransportError: POST /protocols returned 422` and nothing
  else, even though the robot had named the file and the line.
- **Cause**: `TransportError` stored the response body on the exception,
  but the CLI handler printed only `str(error)`, so the useful half of
  the report never reached the terminal.
- **Fix**: `_describe_failure` unpacks `TransportError.body` and
  `AnalysisError.errors`, and the CLI prints each line under the summary.
- **Rule**: Always check what the operator actually sees; an error the
  code holds but never prints is an error the operator does not have.
  (from ToDo#1 E)

**A branch that collects issues becomes a PR nobody can review**
- **Problem**: One pull request merged 7492 lines across 42 files, about
  nineteen times the 400-line guidance of CLAUDE.md §15.3.
- **Cause**: Work kept being added to a branch that was already open.
  Conventions, controller, console, and documentation were four
  separable deliverables tracked under three separate issues, but each
  new task landed on the same branch because it was there.
- **Fix**: None available after the fact -- splitting retroactively would
  discard the review history attached to the pull request. Recorded in
  the pull request body instead.
- **Rule**: Always cut a fresh branch when a new issue is opened; a
  branch serving more than one issue is already too large.
  (from ToDo#6)

**A committed checker starts checking itself**
- **Problem**: The convention audit passed with zero findings, then
  reported five against its own file on the very next run.
- **Cause**: The script had just been committed, so `git ls-files` began
  listing it and it entered its own audit set.
- **Fix**: Fixed the two real gaps it exposed in itself -- a short verb
  vocabulary and a waiver applied inconsistently.
- **Rule**: Always re-run a self-referential tool after committing it;
  the run that matters is the first one where it can see itself.
  (from ToDo#6)

**Withholding a safety fix can be the more dangerous option**
- **Problem**: A branch fixed a default that would have overwritten a real
  robot's deck configuration, but CLAUDE.md §5.1 rule 2 keeps unverified
  hardware paths off `main`, so the fix sat unmerged.
- **Cause**: The rule is written to stop unverified code being *trusted*.
  Applied literally it also stopped unverified code being *corrected*,
  while the hazard it corrected stayed on the default branch.
- **Fix**: Merged deliberately, with the pull request banner rewritten to
  state the code is unverified on hardware and why it was merged anyway,
  the tracking issue left open, and the README warning kept in place.
- **Rule**: Always compare the risk of merging against the risk of the
  branch that is already on `main`; a gate that protects the default
  branch stops protecting it once the default branch is the worse of the
  two. (from ToDo#9)

## §5. Environment Specifics

**robot-server needs libsystemd headers before `make setup`**
- **Problem**: `make setup` failed building `systemd-python==234`.
- **Cause**: The wheel is compiled from source and needs libsystemd via
  `pkg-config`, absent on a clean Ubuntu 24.04 container.
- **Fix**: `apt-get update && apt-get install -y libsystemd-dev
  pkg-config`. The `apt-get update` is required — a stale index gives
  404s on the package files.
- **Rule**: Always run `apt-get update` before installing build
  dependencies in a container image of unknown age.
  (from ToDo#1 B)

**The development server forgets its deck configuration on restart**
- **Problem**: Deck fixtures registered in one session are gone in the
  next.
- **Cause**: `dev-flex.env` sets
  `OT_ROBOT_SERVER_persistence_directory=automatically_make_temporary`.
- **Fix**: Kept the fixture list in `configs/deck_od_normalization.json`
  and made `execute` apply it as workflow step 3.
- **Rule**: Always treat development-server state as disposable and
  reapply configuration from a versioned file.
  (from ToDo#1 B)

---

## §99. Uncategorized

**The reference protocol is not in the Opentrons source repository**
- **Problem**: `OD_Normalization.py` was not found anywhere in
  `Opentrons/opentrons`, and the Protocol Library page renders entirely
  on the client, so the HTML carries no code.
- **Cause**: Library protocols are served from a GraphQL API rather than
  the source repository.
- **Fix**: Retrieved it from
  `https://library.opentrons.com/api/graphql` via
  `getProtocolBySlug(slug:)`, whose `protocolText` field holds the
  source, and vendored the result at `protocols/OD_Normalization.py`.
- **Rule**: Always check for a data API behind a client-rendered page
  before concluding a resource cannot be fetched.
  (from ToDo#1 B)

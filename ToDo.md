# ToDo

## Task 1: Adopt CommonClaude conventions and implement FlexController per spec v0.3

**Date**: 2026-08-13
**GitHub Issue**: #1
**Spec**: `docs/flex_controller_spec_v0.3.md`

### Command Input Validation

- **Target**: this repository — conventions files, `flex_controller.py`, tests.
- **Method**: vendor `coport-uni/CommonClaude` as a submodule under `external/`,
  mirror its `CLAUDE.md` and `.claude/` hooks here, then implement and verify
  `FlexController` against a local Flex `robot-server` development server.
- **Purpose**: deliver the tool described by spec v0.3 and prove, with real
  command output, that it uploads a protocol, gates on the analysis, runs it,
  collects results, and correctly detects injected protocol errors.
- **Reference materials reviewed**: `docs/flex_controller_spec_v0.3.md`,
  `docs/sim-od-normalization.json`, `external/CommonClaude/CLAUDE.md`,
  Opentrons `robot-server` source (`Makefile`, `dev-flex.env`, routers).
- **LearnedPatterns.md**: absent at task start; bootstrapped at task end
  from this task's completed items (see CLAUDE.md §10).

### Checklist

#### A. Conventions

- [x] Add `https://github.com/coport-uni/CommonClaude` as a submodule at
      `external/CommonClaude`
- [x] Write project `CLAUDE.md` — project overview plus the CommonClaude
      ruleset (§1 through §17)
- [x] Copy `.claude/settings.json` and the five hooks into this repository
- [x] Add `.gitignore` per CLAUDE.md §13 and `ruff.toml` with 80-column limit
- [x] Verify each hook fires by feeding it a crafted tool-input payload

#### B. Development server (spec §3, stage S1)

- [x] Clone `Opentrons/opentrons` and sync `robot-server` dependencies
- [x] Install `docs/sim-od-normalization.json` into `robot-server/simulators`
      and point `dev-flex.env` at it
- [x] Start the server and confirm the simulated 96-channel pipette, gripper,
      and three modules are attached
- [x] Record the build procedure in `docs/dev_server_setup.md`
- [x] Obtain the reference protocol `OD_Normalization.py` (spec §1.3)
- [x] Write the verification CSV per spec §2.4

#### C. Implementation (spec §4, stages S2 through S4)

- [x] Implement `FlexController` — transport, endpoints, workflow, monitoring
- [x] Keep instance state to the five attributes named in spec §4.1
- [x] Take host, port, timeout, and polling period as constructor arguments only
- [x] Implement the analysis gate of spec §5.2 with no bypass option
- [x] Implement the terminal run states of spec §5.3 as a named constant, and
      warn rather than raise on an unknown state string
- [x] Implement the `dev` and `robot` profiles per spec §4.4
- [x] Implement the CLI entry point
- [x] Confirm the method count stays at or under 30 (spec §4.3 rule 5)

#### D. Verification (spec §8) — required before any git operation

- [x] TC-01 unit: response parsing against stored JSON fixtures
- [x] TC-02 unit: retry three times on 5xx, zero times on 4xx
- [x] TC-03 integration: `health` returns name `opentrons-dev`
- [x] TC-04 integration: the twelve fixtures of spec §3.4 read back
- [x] TC-05 integration: CSV upload returns a file ID present in `GET /dataFiles`
- [x] TC-06 integration: protocol upload returns a protocol ID and analysis ID
- [x] TC-07 integration: analysis clean, and the six checks of spec §8 present
- [x] TC-08 integration: undefined labware produces an error and blocks the run
- [x] TC-09 integration: missing `cutoutD3` fixture is caught by the analysis
- [x] TC-10 integration: a full run reaches `succeeded`
- [x] TC-11 integration: `stop` after `play` reaches `stopped`
- [x] Error injection: Python syntax error is reported, run blocked
- [x] Error injection: layout error — two labware in one slot — is reported
- [x] Error injection: missing runtime parameter file is reported
- [x] `ruff check` and `ruff format --check` clean on all Python files
- [ ] TC-12, TC-13 acceptance on the real device — **out of scope**, no device
      is present; see CLAUDE.md §5.1 rule 2

#### E. Wrap-up

- [x] Record results in `claude_test/README.md`
- [x] Bootstrap `LearnedPatterns.md` per CLAUDE.md §10
- [x] Commit, push, and open a PR carrying the verification output

### Outcome notes

Appended rather than edited into the checklist above, which is a record
of what was planned (CLAUDE.md §4 rule 2).

- **TC-09 detection layer differs from the plan.** The item above reads
  "caught by the analysis". It is not: robot-server analyses a protocol
  without reference to the deck configuration, so the analysis is clean
  and the run is created. The fault surfaces during the run as
  `AreaNotInDeckConfigurationError`. The test asserts the observed
  behaviour. See `LearnedPatterns.md` §3.
- **Syntax errors are refused at upload**, with HTTP 422
  `ProtocolFilesInvalid`, not through the analysis `errors` array.
- **TC-07 needs the 96-row CSV.** The gripper only moves a tiprack once
  the first is exhausted, which takes more than 96 pickups.
- **TC-12 and TC-13 were not attempted.** No Opentrons Flex is present.
  Nothing in this task is evidence about hardware (CLAUDE.md §5.1).

---

## Task 2: Independent Re-verification and Operator-facing Error Detail

**Date**: 2026-08-13
**GitHub Issue**: #3
**Spec**: `docs/flex_controller_spec_v0.3.md` (v0.3)

Task 1 was verified by the session that wrote it. This task re-runs the
verification from the outside -- driving the CLI and the class directly
rather than through the test suite -- so the result does not rest on the
tests agreeing with the code that produced them.

### Checklist

- [x] Re-run the full suite against a live development server (54 passed)
- [x] Drive each fault protocol through the CLI and read the real output
- [x] Confirm TC-07 evidence in a real run: 2 `moveLabware` with
      `usingGripper`, 3 `loadModule`, 192 aspirates for 96 CSV rows,
      97 waste-chute tip drops
- [x] Confirm TC-10 independently: run reaches `succeeded`, 788 commands,
      0 failed
- [x] Confirm TC-11 independently: `play` then `stop` reaches `stopped`
- [x] Confirm TC-09 independently: demote `cutoutD3`, observe a clean
      analysis and a `failed` run with `AreaNotInDeckConfigurationError`
- [x] Fix: surface the robot's own explanation in the CLI, not just the
      status line (`_describe_failure`)
- [x] Add unit tests for the new reporting path
- [x] Record the lesson in `LearnedPatterns.md` §4

### Outcome notes

- **Defect found and fixed.** `TransportError` carried the robot's
  explanation on `.body`, but the CLI printed only `str(error)`, so an
  operator uploading a protocol with a syntax error saw
  `POST /protocols returned 422` and no file or line. The CLI now prints
  the detail beneath the summary. This was the one substantive gap the
  original verification missed, because the tests asserted against the
  exception object rather than against the terminal output.
- **TC-09 remains a documented deviation from spec §7**, confirmed a
  second time by direct observation rather than by test.
- **TC-12 and TC-13 are still not run.** No Opentrons Flex is present.

---

## Task 3: Operator console (`main.py`) with step-by-step run display

**Date**: 2026-08-13
**GitHub Issue**: #4
**Requested**: read the Flex's information, verify and upload a protocol,
and watch the program execute step by step.

### Command Input Validation

- **Target**: a new `main.py` at the repository root, plus the two
  read-only endpoint methods it needs on `FlexController`.
- **Method**: a staged console that reads robot identity and attached
  hardware, applies the deck, verifies through the analysis gate, then
  streams each command as the robot completes it. An interactive mode
  walks the analysis command list one step at a time.
- **Purpose**: make the tool observable. Until now the only way to see
  what the robot did was to read a JSON artifact after the fact.
- **Reference materials reviewed**: `docs/flex_controller_spec_v0.3.md`
  §4.2 (method table), §5 (workflow), and the live command API, probed
  directly before designing the display (see Findings).

### Findings that shaped the design (probed, not assumed)

- `GET /runs/{id}/commands` grows during a run — `totalLength` went
  40 → 483 → 788 — so commands can be streamed as they complete.
- Each command carries `status`, `startedAt`, `completedAt`, and
  `links.current` names the command executing now.
- A 96-row run finishes in ~4.2 s on the simulator, too fast to follow,
  so a deterministic step-through of the analysis is offered alongside
  the live stream.

### Checklist

- [x] Add `get_instruments` and `get_modules` to `FlexController`
- [x] Record that the class now exceeds the 30-method review threshold of
      spec §4.3 rule 5, and carry out the reconsideration it prescribes
- [x] `main.py` stage 1: robot identity, pipettes, gripper, modules
- [x] `main.py` stage 2: apply and show the deck configuration
- [x] `main.py` stage 3: upload the CSV and the protocol
- [x] `main.py` stage 4: wait for the analysis and show the verdict
- [x] `main.py` stage 5: list the planned steps, readably
- [x] `main.py` stage 6: run, streaming each command as it completes
- [x] `main.py` stage 7: final summary with per-type counts and errors
- [x] `--verify-only` stops after the gate; `--step` walks the plan
- [x] Resolve labware, module, and pipette identifiers to readable names
- [x] Unit tests for the command describer and the stage helpers
- [x] Verify by running against the development server, output kept
- [x] `ruff check` and `ruff format --check` clean

### Outcome notes

- **Two display defects found by running the console, not by testing
  it.** Both produced blank labware and well names during a run, and
  neither was visible from the analysis path. First, a run assigns its
  own identifiers to the same labware, so a name map built from the
  analysis resolves nothing. Second, a run lists a labware only once it
  has been loaded, so reading the run before the command list leaves
  names a tick behind. The stream now rebuilds names from the run and
  reads the run after the commands.
- **`FlexController` is at 32 methods**, past the review threshold of
  spec §4.3 rule 5. The reconsideration the rule prescribes is
  `docs/transport_layer_review.md`: do not split yet, and the four
  conditions that would make the split due. The test now asserts the
  exact count and requires that document to exist.
- **A second entry point now exists** beside the CLI function of spec
  §4.1. `main.py` is a client of the class and adds no robot behaviour,
  but it is a deviation and is recorded as one.
- **`protocols/hello_flex.py` added** as a minimal example, to make it
  plain that what reaches the robot is an ordinary Python file.

---

## Task 4: Fidelity check — simulator vs real Flex, log vs published procedure

**Date**: 2026-08-13
**GitHub Issue**: #4 (continued)
**Asked**: is the development server identical to an Opentrons Flex, and
does the run log match the procedure published with the protocol?

### Checklist

- [x] Compare development server and real device: config, versions,
      calibration, timing
- [x] Test empirically whether the simulator enforces physical reality
- [x] Fetch the published procedure from the Protocol Library API
- [x] Fetch the official example CSV linked in that description
- [x] Compare the observed command log against the published procedure
- [x] Reconcile the command counts arithmetically against the CSV
- [x] Vendor the official CSV as `data/od_normalization_reference.csv`
- [x] Fix: `--verify-only` wrote no artifact despite `--artifact-dir`
- [x] Add regression tests for artifact saving

### Outcome notes

- **The development server is not a Flex.** It shares the codebase, the
  API, the port, and the analysis engine, so it validates protocol
  logic. It does not model physics. Proven: a protocol that aspirates
  200 uL from a reservoir holding nothing and dispenses 1200 uL into a
  360 uL well completed `succeeded` with zero errors. `robot_serial` is
  `simulator`, `fw_version` is `0`, and every calibration offset is a
  fabricated 0.0.
- **The log matches the published procedure in sequence**: three modules
  loaded, diluent phase, DNA phase, tiprack switch by gripper when the
  first rack empties. Counts reconcile exactly — 348 aspirates and 104
  tip pickups predicted from the official CSV, 348 and 104 observed.
- **Three documented discrepancies.** The description says the protocol
  "requires implementation of" three modules, but zero module action
  commands are planned; they are loaded and left idle. Spec §2.4's CSV
  header differs from the official file's. The official CSV is 103 rows,
  above the 96 needed to exercise the gripper, which is why spec §2.4's
  3-row starter never reaches that path.
- **Defect found and fixed.** `--verify-only` saved nothing even when
  `--artifact-dir` was given, so the one command an operator runs to
  inspect a protocol kept no record. The analysis is now saved as soon
  as it completes, including for a rejected protocol.

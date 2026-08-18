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

---

## Task 5: Convention audit and documentation set

**Date**: 2026-08-13
**GitHub Issue**: #5
**Requested**: check the code against CLAUDE.md and the MIT convention;
organise the work and the spec departures into separate markdown files;
rewrite README.md for a reader who has never used an Opentrons Flex,
using diagrams and tables, stating what the simulation established and
what was borrowed from which repository.

### Checklist

- [x] Run ruff check and ruff format across the repository
- [x] Check the 80-column limit, tabs, and indentation
- [x] Audit the rules ruff cannot see: docstrings and their Google
      sections, verb-shaped function names, noun-shaped class names,
      English-only source, continuation-line operator placement
- [x] Fix every genuine finding
- [x] Write `docs/code_quality_audit.md`
- [x] Write `docs/spec_deviations.md`
- [x] Write `docs/verification_report.md`
- [x] Write `docs/upstream_references.md`
- [x] Rewrite `README.md` for a newcomer, with diagrams and tables
- [x] Verify every numeric claim in the new documents against a real run
- [x] Verify every internal document link resolves

### Outcome notes

- **The audit tool was wrong three times before the code was.** A first,
  regex-based version reported 94 findings; 17 were phantom operator
  faults from matching "or" inside "error", "floor", and "operator", and
  70 were phantom docstring faults from demanding `Args:` for pytest
  fixtures. A token-based rewrite reported 8, of which one came from
  skipping string literals. The final count of genuine findings was
  **six**, all in `claude_test/`: scenario functions named for nouns
  where CLAUDE.md §2 asks for verbs. CLAUDE.md §8 waives columns and
  docstrings there, not naming.
- **One documentation claim was wrong and was corrected**, not shipped:
  the README described `hello_flex.py` as twenty lines when it is
  thirty-four.
- **Ten spec deviations are now catalogued** with evidence. Three are
  errors in the spec's model of robot-server, two are ours and
  deliberate, five are gaps or typos.
- **A convention divergence is recorded rather than silently followed**:
  CLAUDE.md §2 specifies `lower_case` constants, against PEP 8 and
  against the CommonClaude table it derives from. The project file wins
  per §1, and the code follows it.

---

## Task 6: Merge the branch into main

**Date**: 2026-08-13
**Pull Request**: #2, merged as `a6cc599`
**Closes**: #1, #4, #5

### Checklist

- [x] Re-verify on the working tree before any git operation (§5.1)
- [x] Confirm the integration suite ran rather than skipped
- [x] Fix what the verification caught
- [x] Bring the PR title and body up to date with the whole branch
- [x] State TC-12 and TC-13 as NOT VERIFIED in the PR
- [x] Merge with a merge commit, preserving the six commits
- [x] Delete the branch, local and remote
- [x] Confirm `main` carries the work and the three issues closed

### Outcome notes

- **The verification gate earned its keep at the last moment.** The audit
  script had been committed in the previous task, which put it under
  `git ls-files`, so the next run audited it and reported five findings
  against itself. Both causes were in the checker: `check` and `find`
  were missing from the verb vocabulary, and the CLAUDE.md §8 docstring
  waiver was applied to presence but not to the Google sections, which
  penalised a voluntary one-line docstring while excusing none at all.
  Fixed in `e01d4ee`, then the whole gate was re-run from the start
  rather than resumed.
- **The PR body was stale and would have breached §15.2.** It described
  the first commit only; five more had landed and the suite had grown
  from 52 tests to 84. Rewritten against a verification run performed
  immediately before the merge.
- **§15.3 was not satisfied and this is recorded, not hidden.** The PR
  merged 7492 lines across 42 files against guidance of 400.

---

## Task 7: Conda setup instructions in README, verified

**Date**: 2026-08-13
**GitHub Issue**: #6
**Requested**: add conda-based environment setup and command examples to
`README.md`, and verify the commands actually work.

### Command Input Validation

- **Target**: `README.md`, plus an `environment.yml` for conda to consume.
- **Method**: create a real conda environment from the file, install into
  it, and run every command the README will publish, from a shell where
  that environment is active.
- **Purpose**: the install section currently says `pip install requests`
  and nothing else. A reader on conda has no starting point, and the dev
  tooling (`pytest`, `ruff`) is not mentioned at all.
- **Reference materials**: `CLAUDE.md` §5.1 verification gate, `ruff.toml`,
  the existing `README.md` §3 and §7.

### Checklist

- [x] Add `environment.yml` naming the Python version and dependencies
- [x] Create the environment from that file on this machine
- [x] Verify `python`, `requests`, `pytest`, `ruff` resolve inside it
- [x] Run every README command inside the environment and keep the output
- [x] Rewrite README §3 Step 1 with conda first, pip as the alternative
- [x] Add a command-examples section covering the common tasks
- [x] Confirm no README command is published without having been run
- [x] `ruff`, the convention audit, and the 84 tests still pass
- [x] Commit, PR, merge

### Notes

- Spec CLAUDE.md gives Python 3.10+; this machine's system Python is
  3.12.3, so the environment pins a version at or above the floor rather
  than matching the host by accident.

### Outcome notes

- **Two defects found by running the commands rather than writing them.**
  Both would have shipped had the section been written from memory.
- **`ruff format --check .` failed in the conda environment but passed on
  the host.** Ruff 0.16 began formatting Python inside Markdown fences;
  the host had 0.15.9, the environment installed 0.16.3. A command the
  README publishes must not pass or fail depending on which ruff the
  reader happens to have, so `*.md` is now excluded in `ruff.toml` and
  both versions were confirmed to agree.
- **The README misdescribed its own code sample.** It introduced the
  snippet as `hello_flex.py` "minus its imports and metadata", but the
  snippet had also been compressed and stripped of `label=` arguments.
  Reworded to say what it actually is.
- **All 36 commands in the README's bash blocks were executed**, including
  the pip and venv alternative, which was run in a throwaway virtual
  environment to confirm the tool and the tests work outside conda too.
- The environment was **deleted and rebuilt from `environment.yml`** to
  prove the documented path works from nothing. It takes about ten
  seconds.

---

## Task 8: Prepare the real-device path (stage S5)

**Date**: 2026-08-13
**GitHub Issue**: #8
**Requested**: make a real device runnable from this conda environment by
supplying only its IP, a protocol file, and a CSV, and write down how to
do it.

### Command Input Validation

- **Target**: `main.py` argument handling and the robot-profile path, plus
  a runbook document.
- **Method**: remove the dangerous default, add the pre-flight checks of
  spec §10 that software can actually make, strengthen the confirmation,
  and document the S5 procedure end to end.
- **Purpose**: stage S5 acceptance. Every earlier task ran against a
  simulator; this is the first that ends with a machine moving.
- **Reference materials**: spec §10 (transition checklist), §4.4
  (profiles), §5 (workflow), CLAUDE.md §5.1 rules 2 and 5,
  `docs/spec_deviations.md` D-1.

### The defect this task starts from

`--deck` defaults to `configs/deck_od_normalization.json`, and
`show_deck` **writes** whatever it is given. On `--profile robot` that
silently overwrites the real robot's deck configuration with our
reference layout — asserting a waste chute at D3 whether or not one is
bolted there. Per D-1 the analysis will not object, so the mismatch first
appears mid-run, on a machine that is already moving.

### Checklist

- [x] `--deck` no longer defaults to writing; `robot` reads unless asked
- [x] Pre-flight: reachability, robot name, apiLevel support, attached
      instruments, attached modules, deck configuration
- [x] Block only on facts the tool is certain of; show the rest for the
      operator standing there to judge
- [x] Confirmation requires typing the robot's own name, not "yes"
- [x] No bypass flag for the confirmation (spec §4.4, §5.2)
- [x] `--expect-name` for spec §10 item 4
- [x] Write `docs/real_device_procedure.md`: TC-12 then TC-13, abort
      procedure, what to record
- [x] README section for the real device
- [x] Verify every reachable path against the development server
- [x] State plainly that the hardware path is **not** verified, and leave
      the branch unmerged until it is (CLAUDE.md §5.1 rule 2)

### Notes

- Spec §10 has twelve items. Seven are observable from software (2, 3, 4,
  5, 6, 7, 9); items 8 and 10 — fixtures physically installed, labware
  position calibration — are not, and must be listed for a human.
- TC-12 and TC-13 cannot be run here. No Opentrons Flex exists in this
  environment.

### Outcome notes

- **A dangerous default was the starting point, not a late discovery.**
  `--deck` defaulted to the reference layout and the console wrote it
  unconditionally, so `--profile robot` would have overwritten a real
  robot's deck configuration on the first run. Fixed by making the
  default profile-aware: `dev` applies the reference layout, `robot`
  reads and shows it, and writing takes an explicit `--deck`. Both
  directions were verified against the development server by planting a
  marker fixture and checking whether it survived.
- **The confirmation now takes the robot's name, not "yes".** Verified:
  typing `yes` declines with exit 2 and creates no run.
- **Pre-flight blocks on two things only** — unreachable robot, wrong
  robot. Everything else is shown for the operator, because this console
  cannot know what an arbitrary protocol needs and the analysis gate
  already refuses what the robot itself rejects.
- **The audit caught three real faults in this task's own code**: `parse`
  and `verdicts` naming, and missing docstrings on the new test stub.
- **The documented stop command was executed against a live run** and
  took it to `stopped`, rather than being written from memory.
- **TC-12 and TC-13 remain unrun.** No Opentrons Flex exists here. Per
  CLAUDE.md §5.1 rule 2 this branch is pushed but **must not be merged**
  until they have been run with an operator present.

---

## Task 9: Merge the real-device path into main, unverified

**Date**: 2026-08-13
**Pull Request**: #9, merged as `344e8d4`
**Issue #8**: deliberately left **open**

### What was decided

Merged at the repository owner's direction, against the letter of
CLAUDE.md §5.1 rule 2, which keeps an unverified hardware path off
`main`. Recorded here so it reads as a decision rather than an oversight.

### Why merging was the lower risk

`main` already carried the hazard this branch removes. Before the merge
`--deck` defaulted to writing the reference deck layout, so anyone who
pulled `main` and ran `--profile robot` would have overwritten a real
robot's deck configuration on the first run — and per D-1 the analysis
would not have objected. Withholding the fix kept that hazard on the
default branch, where it was more likely to reach a machine than the fix
was.

Merging lowers the risk. It does **not** discharge the verification gate.

### What is still true after the merge

- [ ] TC-12 real device dry-run — **NOT RUN**
- [ ] TC-13 real device full run — **NOT RUN**
- [x] Issue #8 kept open until both pass
- [x] The pull request banner rewritten to say the code was merged
      unverified, and why
- [x] `README.md` still states plainly that no hardware has run this
- [x] Verification gate re-run before the merge: ruff clean, audit 0
      findings, 95 tests passing

**Nothing on `main` may be read as evidence about hardware.**

---

## Task 10: Document the Windows PowerShell conda trap in README

**Date**: 2026-08-18
**GitHub Issue**: pending — `gh` is not installed on this Windows host
**Requested**: record the reason `conda` is unavailable in PowerShell in
`README.md`.

### Command Input Validation

- **Target**: `README.md` §3 Step 1, where the reader is told to run
  `conda env create` and `conda activate`.
- **Method**: add a collapsed Windows note giving the symptom, the
  diagnosis command, the one-line remedy, and how to confirm it worked.
- **Purpose**: §3 Step 1 currently assumes `conda` resolves. On a fresh
  Windows install it does not, and the failure names the wrong cause —
  the shell reports a missing command, while the real cause is a blocked
  profile. A reader who trusts the message edits `PATH` and gets nowhere.

### Reference material

The diagnosis was measured on this machine, 2026-08-18:

- Miniconda is installed at `C:\Users\swoho\miniconda3`; calling
  `Scripts\conda.exe --version` directly answers `conda 26.5.3`.
- Neither the user nor the machine `PATH` carries a conda entry. This is
  expected: `conda init` uses a profile hook, not `PATH`.
- `conda init powershell` has already run — the hook block is present in
  `...\WindowsPowerShell\profile.ps1`.
- `Get-ExecutionPolicy -List` reports every scope `Undefined`, so the
  effective policy is `Restricted`, the profile is refused with
  `PSSecurityException / UnauthorizedAccess`, and `conda` is never
  defined.

### Checklist

- [x] Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` with the
      operator's consent, and capture the before/after output — the
      remedy is not documented until it has been run (§5.1)
- [x] Add the Windows note to `README.md` §3 Step 1
- [x] Append the finding to `LearnedPatterns.md` §5 Environment
      Specifics (see LP §5)
- [x] Cut branch `docs/windows-powershell-conda`
- [ ] Open the GitHub issue and the PR once `gh` is available

### Verification

The operator applied the policy change and reported it working; the
state was then measured from a clean PowerShell session with the
inherited `Process` scope cleared.

**Before** — reproduced with `-ExecutionPolicy Restricted`:

```
Restricted
. : File ...\WindowsPowerShell\profile.ps1 cannot be loaded because
running scripts is disabled on this system.
    + FullyQualifiedErrorId : UnauthorizedAccess
conda : The term 'conda' is not recognized as the name of a cmdlet,
function, script file, or operable program.
    + FullyQualifiedErrorId : CommandNotFoundException
```

**After**:

```
        Scope ExecutionPolicy
        ----- ---------------
MachinePolicy       Undefined
   UserPolicy       Undefined
      Process       Undefined
  CurrentUser    RemoteSigned
 LocalMachine       Undefined

effective : RemoteSigned
conda 26.5.3

# conda environments:
base                 *   C:\Users\swoho\miniconda3
opentrons-flex           C:\Users\swoho\miniconda3\envs\opentrons-flex
```

**The locked-down fallback**, also measured rather than assumed —
`conda.exe activate` under `Restricted` refuses and leaves no
environment active:

```
CondaError: Run 'conda init' before 'conda activate'
```

No Python file changed, so `ruff` and `pytest` have nothing to say
about this task. Every claim added to `README.md` corresponds to one of
the outputs above.

### Open

`gh` is not installed on this Windows host, so the issue and the pull
request could not be created here. The branch stays local and unpushed
until that is resolved.

### Update — `gh` installed on the Windows host

At the operator's request, the blocker above was removed:

```
$ winget install --id GitHub.cli -e --source winget
Found GitHub CLI [GitHub.cli] Version 2.97.0
Successfully verified installer hash
Successfully installed

$ gh --version
gh version 2.97.0 (2026-07-31)
```

The installer put `gh.exe` in `C:\Program Files\GitHub CLI\` and added
that directory to the machine `PATH`, so terminals opened after the
install resolve `gh` without further configuration.

Authentication is still outstanding, and cannot be done from here:
`gh auth login` needs a browser or a pasted token, both of which
require an interactive session.

```
$ gh auth status
You are not logged into any GitHub hosts. To log in, run: gh auth login
```

- [x] Install `gh`
- [ ] `gh auth login` — operator, interactive
- [ ] Open the GitHub issue and the PR for this task once logged in

A second note: this host had no git identity at all, so the first
commit attempt was refused. It is now set **repository-locally** to the
value the previous commit used, `coport-uni <ohsungwoo@unist.ac.kr>`.
Nothing was written to the global git configuration.

---

## Task 11: Conda environment on Windows, and the first verified real-device run

Requested: build the `environment.yml` environment with Anaconda on the
Windows host and prove it works; then verify communication with the real
Flex by reading its serial number and model without moving it; then run
the test protocol on the device following the layout in the protocol
file, and confirm that no CSV is required.

### Environment

Neither conda nor Python was present on the Windows host. The operator
chose **Miniconda** over the full Anaconda distribution, since
`environment.yml` draws only on conda-forge.

```
$ winget install --id Anaconda.Miniconda3 --silent
Successfully installed          # -> C:\Users\swoho\miniconda3
```

`conda env create` first failed. The env file lists only conda-forge,
but conda always appends the implicit `defaults` channel, whose
Anaconda repositories are behind a Terms of Service gate:

```
CondaToSNonInteractiveError: Terms of Service have not been accepted for
the following channels: repo.anaconda.com/pkgs/{main,r,msys2}
```

Rather than accept Anaconda's commercial terms for repositories this
project never draws on, the `defaults` alias was pointed at conda-forge:

```
$ conda config --add channels conda-forge
$ conda config --add default_channels https://conda.anaconda.org/conda-forge
$ conda env create -f environment.yml          # succeeded
```

- [x] Install a conda distribution on the Windows host
- [x] Create the `opentrons-flex` environment from `environment.yml`
- [x] `conda init powershell` so `conda activate` works in a shell

### Environment verification, offline

Run inside the environment, with the output kept:

```
Python 3.12.13          # matches the version README records
requests 2.34.2 · pytest 9.1.1 · ruff 0.16.3

$ python -m pytest tests/ -q
72 passed, 23 skipped in 4.75s
  all 23 skips are tests/test_integration_dev_server.py, reason
  "no robot-server development server on localhost:31950"

$ ruff check .                 All checks passed!
$ ruff format --check .        7 files already formatted
$ python claude_test/audit_mit_convention.py
  files audited : 7 / findings : 0
$ python main.py --help        full option list printed
```

The transport path was exercised with no server listening: the
pre-flight blocked before any upload, after the retry backoff ran
1s -> 2s -> 4s, and both entry points exited 1 on a clean
`TransportError`.

- [x] Verify the environment offline; keep the real output

### Real-device identity, read only

Device reached over a direct Ethernet link. Only GET requests were
issued -- `/health`, `/instruments`, `/modules`, `/deck_configuration`
-- so nothing moved.

```
name           BionicsDEMO1
robot_serial   FLXA3020260521001
robot_model    OT-3 Standard          board FLEX_B2
api / system   9.1.1 / v9.1.1         fw 69
protocol API   2.15 - 2.29
address        169.254.108.46:31950   mDNS FLXA3020260521001.local

left       p1000_single_v3.6      P1KSV3620260422A12
right      p1000_multi_v3.5       P1KMV3520260513A08
extension  gripperV1.3            GRPV1320260521009

heaterShakerModuleV1   HSV012026051414
thermocyclerModuleV2   TCV2120260603A03
absorbanceReaderV1     OPTMAA00088
```

Note for later work: this device has **no 96-channel pipette**, so the
reference protocol `OD_Normalization.py` cannot run on it as written.

- [x] Verify communication by reading serial number and model, no motion

### Two blockers found by the analysis gate

The first attempt was rejected, and the gate behaved exactly as spec
section 5.2 requires -- no run was created:

```
result  : not-ok    errors : 1
ExceptionInProtocolError [line 26]: FileNotFoundError: Labware
"thermo_fisher_nunclon_sphera_96_well_u_bottom_174925" not found with
version 1 in namespace "opentrons".
```

That definition is absent from Opentrons shared-data at both schema 2
and schema 3, so it is **custom labware** (namespace `custom_beta`,
version 2). The desktop app keeps custom definitions in its own store,
which is why the protocol runs there and not over HTTP. `POST
/protocols` accepts several `files` parts, and sending the definition
alongside the protocol resolved it -- `load_labware` picked up the
version-2 definition without an explicit `version=` argument.

Second, the protocol loads `magneticBlockV1` at C1 while the robot had
`cutoutC1` set to `singleLeftSlot`. The operator confirmed the block is
physically installed, so the deck configuration was corrected to match
the protocol. The original was saved first and remains reversible.

- [x] Supply the custom labware definition with the protocol
- [x] Align `cutoutC1` with the protocol's magnetic block

### The run

Operator present, e-stop within reach, deck checked against the plan
before the go-ahead was given.

```
robot         BionicsDEMO1 at 169.254.108.46
run id        60451ab1-b67d-4cf7-811a-c143a018bd23
final status  succeeded
started       2026-08-18T07:14:50.404521Z
completed     2026-08-18T07:16:16.360100Z
errors        0        failed commands  0

27 commands, all succeeded: home, 3 loadModule, 7 loadLabware,
loadPipette, closeLabwareLatch, 3 comment, 2 pickUpTip, 2 aspirate,
2 dispense, 2 moveToAddressableArea, 2 dropTipInPlace, openLabwareLatch
```

- [x] Run the protocol on the real device, layout as the file gives it
- [x] Confirm no CSV is needed -- the robot reported
      `runTimeParameters: []`, because the protocol declares no
      `add_parameters`. This matches the desktop app, which does not
      ask for one.

### Caveats recorded honestly

1. **The upload did not go through production code.**
   `FlexController.upload_protocol` sends a single file, so it cannot
   carry a custom labware definition. The upload used a scratchpad
   harness; the deck write, analysis gate, run creation, play and
   monitoring all used the production controller's public methods.
   `python main.py` still cannot run this protocol. Task 12 closes this.
2. **`--params "{}"` is mandatory** for this protocol. `main.py`
   defaults to the reference protocol's `{"dry_run": True,
   "waste_type": 1}`, which this protocol does not declare.
3. **The run records were not written at run time**, because the
   scratchpad harness never called `save_artifact`. They were retrieved
   from the robot afterwards and written through the production method:
   `artifacts/run.json`, `artifacts/commands.json`, `analysis.json`,
   and the earlier rejection kept as
   `analysis_rejected_custom_labware.json`.
4. **The robot's own logs are not collected by this tool at all.** All
   seven were pulled by hand into `artifacts/` (110 MB); `artifacts/`
   is gitignored.
5. The deck configuration on the robot is left changed at `cutoutC1`.
   Reverting it is required if the magnetic block is removed.

### Open

`gh auth login` is still outstanding on this host, so no GitHub issue
could be created for this task. It needs a browser or a pasted token
and cannot be completed non-interactively.

```
$ gh auth status
You are not logged into any GitHub hosts. To log in, run: gh auth login
```

- [ ] `gh auth login` — operator, interactive
- [ ] Open the issue and the PR for Task 11 and Task 12 once logged in

---

## Task 12: Run a custom-labware protocol from `main.py` on a real device

> Proposed. Awaiting the operator's confirmation before work starts.

Requested: make the protocol runnable with a plain `python` command, and
write the real-device commands into `README.md` and `main.py`.

Task 11 proved the protocol runs on `BionicsDEMO1`, but only through a
scratchpad harness, because `upload_protocol` sends one file and the
protocol needs a custom labware definition alongside it. This task moves
that capability into the tool.

### Scope

- [x] `flex_controller.py`: give `upload_protocol` a `labware_paths`
      argument so `POST /protocols` carries the protocol together with
      any number of custom labware definitions. Thread it through
      `verify_only` and `execute` so both entry points can use it.
- [x] `main.py`: add `--labware`, repeatable, accepting either a
      definition file or a directory of them; pass it to the upload and
      show what was sent in the Upload stage.
- [x] `configs/`: add a deck fixture list for this protocol, so the
      magnetic block at C1 and the waste chute at D3 can be applied with
      `--deck` instead of by hand.
- [x] `README.md`: a real-device section giving the exact commands --
      the read-only identity check, the dry run, and the run -- with
      real output.
- [x] `ruff check .` and `ruff format --check .` clean; `pytest` green,
      with new tests covering the multi-file upload.
- [x] Verify on `BionicsDEMO1` with the operator present, and keep the
      output for the PR (spec section 5.1).

### Notes

- The protocol file was renamed `TestMover.py` -> `TestSingletip.py`
  during Task 11; the README commands must use the current name.
- `--params "{}"` stays mandatory for this protocol. Whether `main.py`
  should stop defaulting to the reference protocol's parameters is a
  separate question, deliberately left out of this task.

### Progress

`gh auth login` (left open by Task 11) has since been completed on this
host, so this task has a GitHub issue: #10.

```
$ gh auth status
github.com
  * Logged in to github.com account coport-uni (keyring)
```

- [x] `main.py`: write the real-device command into the module
      docstring. The example now names `protocols/TestSingletip.py`, the
      device address and `--expect-name BionicsDEMO1`, `--labware
      protocols/labware`, and the empty `--csv` and `--params "{}"` that
      this protocol needs, with notes on the read-only deck and the
      PowerShell empty-argument trap. (issue #10)

Documentation only, so verification was a check of every claim against
the code and the device record, per spec section 5.1:

```
$ python -c "...build_parser().parse_args([the documented arguments])"
profile     : robot | host: 169.254.108.46 | expect: BionicsDEMO1
protocol    : protocols/TestSingletip.py
csv         : '' -> upload skipped: True
params      : {}
labware sent: 4 definitions from protocols/labware
deck default: None -> robot profile reads only

$ ruff check main.py          All checks passed!
$ ruff format --check main.py  1 file already formatted
```

The PowerShell claim was measured rather than recalled:

```
PS> python -c "import sys; print(sys.argv[1:])" --csv "" --params "{}"
['--csv', '--params', '{}']          # the empty argument is dropped
PS> python -c "import sys; print(sys.argv[1:])" --csv='' --params '{}'
['--csv=', '--params', '{}']         # argparse reads this as ''
```

Left open: the documented `--labware protocols/labware` sends all four
definitions in that directory, where only
`thermo_fisher_nunclon_sphera_96_well_u_bottom_174925` is needed. The
verified Task 11 upload sent that one file alone, so the directory form
is still unproven on the device.

Also noticed, outside this change: `main.py` still defaults
`default_protocol`, `default_csv`, and `reference_deck` to
`OD_Normalization.py`, `data/od_normalization.csv`, and
`configs/deck_od_normalization.json`, all of which are deleted in the
working tree. The `--profile dev` examples at the top of the same
docstring therefore no longer run as written.

### Verification

Confirmed by the operator before work started: `--labware` takes files
and directories both; a deck configuration file is wanted; verification
stops at `--verify-only`.

Software checks, run in the conda environment:

```
$ python -m pytest tests/ -q
77 passed, 23 skipped in 4.83s     # was 72 passed; five new tests

$ ruff check .                     All checks passed!
$ ruff format --check .            7 files already formatted
$ python claude_test/audit_mit_convention.py
  files audited : 7 / findings : 0
```

The audit first reported `collect_labware_files` and `write_definition`
as non-verbs. Both are verbs; the auditor's vocabulary simply lacked
them, and its own comment says the list is "the vocabulary the codebase
uses ... reported for a human to judge". `collect` and `write` were
added to it rather than the functions renamed into something worse.

`collect_labware_files` became a **static method** rather than a
module-level function. Spec section 4.1 fixes the externally exposed
entry points at the class and one CLI function, so a public module-level
helper would have been a third. That took the method count from 32 to
33, which `test_method_count_is_the_documented_one` deliberately fails
on until the addition is argued for in
`docs/transport_layer_review.md`; that argument is now recorded there.

On the device, operator present, `BionicsDEMO1`:

```
$ python main.py --profile robot --host FLXA3020260521001.local \
    --expect-name BionicsDEMO1 --protocol protocols/TestSingletip.py \
    --csv "" --params "{}" --deck configs/deck_testsingletip.json \
    --labware protocols/labware --verify-only --no-plan

3. Upload
  custom labware   corning_3590_96_wellplate_360ul_flat.json
  custom labware   costar_7007_96_wellplate_330ul_u_bottom.json
  custom labware   spl_96_well_cell_culture_plate_330ul_flat_bottom (1).json
  custom labware   thermo_fisher_nunclon_sphera_96_well_u_bottom_174925 (1) (1).json
  protocol         TestSingletip.py

4. Analysis
  status  completed     result  ok
  planned commands  27   errors  0
  Gate passed: the robot accepted this protocol.

Done: verified, nothing was run
exit=0
```

The first attempt failed, and the failure is worth keeping. The deck
file was written without `opentronsModuleSerialNumber` on the module
fixtures, and the robot refused it:

```
PUT /deck_configuration returned 422
InvalidDeckConfiguration: Invalid deck configuration.
```

The file was rebuilt from what the robot itself reports, which is now
what `README.md` tells the reader to do.

### Not verified

Per the operator's decision, verification stopped at the analysis gate.
**`main.py` has not driven a full run through the `--labware` path.**
The protocol has run on this device (Task 11), but that run's upload
used a scratchpad harness rather than the code changed here. `README.md`
says so in the same words.

### Open

Still blocked on `gh auth login`, so Task 11 and Task 12 have no GitHub
issue and no pull request. The branch `feature/custom-labware-upload`
stays local until that is done.

---

## Task 13: Stop the console from sending a CSV by default

Requested: the real-device command reported a CSV error; stop using a
CSV at all. Issue #13.

### Cause

`main.py` defaulted `--csv` to `data/od_normalization.csv`, the
reference protocol's data file, so every other protocol had to switch it
off with an empty argument. Both ways out failed:

```
PS> python main.py ... --csv "" --params "{}"
main.py: error: argument --csv: expected one argument
   # PowerShell 5.1 drops the empty argument before argparse sees it

$ python main.py ...            # flag omitted
FileNotFoundError: data/od_normalization.csv
   # the reference protocol's data was deleted from the working tree
```

`protocols/TestSingletip.py` declares no runtime parameters at all, so
no data file was ever wanted.

### Change

- [x] `main.py`: `--csv` defaults to nothing; a data file is uploaded
      only when the operator names one. The flag stays for a protocol
      that declares one with `parameters.add_csv_file`
- [x] `main.py` docstring: the real-device example drops `--csv`
- [x] `tests/test_main_console.py`: cover the new default
- [x] `README.md` and `docs/real_device_procedure.md`: remove the CSV
      from the commands an operator is told to type, and correct the
      guidance that called an empty `--csv` necessary
- [x] `flex_controller.py` left untouched -- spec section 5.1 still
      requires a file-type parameter to be uploaded before the protocol,
      and its own CLI keeps `--csv` / `--csv-variable`

### Verification

Dry run on `BionicsDEMO1` from PowerShell, the shell that was failing,
with the operator present. Nothing moved.

```
PS> python main.py --profile robot --host 169.254.108.46 `
      --expect-name BionicsDEMO1 `
      --protocol protocols/TestSingletip.py `
      --labware protocols/labware `
      --params "{}" --verify-only --no-plan
EXIT=0

0. Pre-flight
  OK    reachable            http://169.254.108.46:31950
  OK    robot name           BionicsDEMO1
  OK    robot software       v9.1.1

3. Upload
  custom labware           corning_3590_96_wellplate_360ul_flat.json
  custom labware           costar_7007_96_wellplate_330ul_u_bottom.json
  custom labware           spl_96_well_cell_culture_plate_330ul_flat_bottom (1).json
  custom labware           thermo_fisher_nunclon_sphera_96_well_u_bottom_174925 (1) (1).json
  protocol                 TestSingletip.py

4. Analysis
  status                   completed
  result                   ok
  planned commands         27
  errors                   0
  Gate passed: the robot accepted this protocol.

Done: verified, nothing was run
```

```
$ ruff check .                 All checks passed!
$ ruff format --check .        7 files already formatted
$ python -m pytest tests/ -q   78 passed, 23 skipped in 4.84s
```

The run was `--verify-only`, so the full run through this path is still
unproven, exactly as Task 12 records.

### Note on tracking

`gh auth login` is done on this host, contrary to the Task 11 and Task
12 entries above: `gh auth status` reports account `coport-uni`, and
issues #10 through #13 were opened from here. #10 duplicated #12 and was
closed as such.

Still open, and deliberately untouched: `main.py` also defaults
`--params` to the reference protocol's `{"dry_run": true,
"waste_type": 1}` and `--protocol` to the deleted
`protocols/OD_Normalization.py`. That is the same defect class as this
CSV one, and it is why `--params "{}"` is still mandatory in every
command above.

---

## Task 13: Retire the reference protocol, and make the operator choose

Requested: the OD-600 normalization material is no longer wanted, the
protocol is something the operator must look at rather than inherit from
a default, the run confirmation should be `y`/`n` rather than the robot's
name, and the GitHub documentation should reflect everything verified so
far.

### Scope

- [x] Delete the OD-600 material: `protocols/OD_Normalization.py`,
      `data/od_normalization*.csv`, `configs/deck_od_normalization.json`.
      They are already gone from the working tree; this stages the
      removal and clears what still points at them.
- [x] `main.py`: `--protocol` becomes **required**, with no default. Drop
      `default_protocol`, `reference_deck`, `default_parameters`, and the
      dev-profile deck write that depended on the reference layout.
- [x] `main.py` and `flex_controller.py`: the pre-run confirmation takes
      `y`/`n` instead of the robot's name or the word `yes`. Both entry
      points behave the same way.
- [x] Update the tests that assert the retired defaults and the prompt.
- [x] `README.md` and `docs/`: remove the OD material from anything that
      tells a reader what to do now, and record what the device runs have
      established.
- [x] `ruff check` / `ruff format --check` clean; `pytest` green.
- [ ] Verify both protocols on the device through `--verify-only`.

### A concern, stated once and then set aside

The name-typing prompt was a deliberate choice, and `README.md` gives the
reasoning: muscle memory types `yes`, and it cannot type the name of a
machine the operator has not looked at. Moving to `y`/`n` makes the gate
one keystroke, which is exactly what that design was avoiding.

Spec section 4.4 requires only that the `robot` profile ask for a
confirmation, not what shape it takes, so `y`/`n` is within the spec. The
operator has asked for it and owns the bench. It is being done, with the
robot's name still printed above the prompt so the machine is still
named, just not typed.

### Historical records are not rewritten

`docs/verification_report.md`, `docs/code_quality_audit.md`,
`docs/spec_deviations.md`, and the completed entries in `ToDo.md` and
`LearnedPatterns.md` describe runs that actually happened against the
OD-600 protocol. Deleting the protocol does not make those runs untrue,
and editing them to pretend otherwise would be a defect. They keep their
OD references. Only material that instructs a reader what to run **now**
is changed.

### Verification

Software checks, in the conda environment:

```
$ python -m pytest tests/ -q
79 passed, 23 skipped in 4.34s

$ ruff check .                     All checks passed!
$ ruff format --check .            7 files already formatted
$ python claude_test/audit_mit_convention.py
  files audited : 7 / findings : 0

$ python main.py --profile dev
main.py: error: the following arguments are required: --protocol
```

The last line is the point of the task: a bare command no longer uploads
anything.

The `README.md` stage-6 sample was rebuilt from the records of the real
run in `artifacts/`, rather than kept as prose about a protocol that no
longer exists. Doing that surfaced why the console builds its name map
from the run and not the analysis -- a run assigns fresh identifiers to
the same labware -- and that reasoning is now in the README instead of
only in a docstring.

### NOT VERIFIED on the device

The robot was disconnected before this task's changes could be exercised
on it:

```
$ Test-NetConnection FLXA3020260521001.local -Port 31950
TcpTestSucceeded : False
```

Per section 5.1 rule 2 the branch stays local: **not pushed, no pull
request, not merged.** Three changes here reach a real device and none
has been run against one --

1. the `y`/`n` confirmation, which is the gate before motion,
2. `--protocol` being required, on the `robot` profile,
3. an omitted `--deck` now writing nothing on **either** profile, where
   the `dev` profile used to write the reference layout.

Item 3 only ever removes a write, so it cannot assert a fixture that is
not there; that is the direction section 5.1 worries about, not the
other. It still has not been run.

When the robot is back, `--verify-only` on `protocols/TestSingletip.py`
and `protocols/Test8tips.py` closes this, and the run confirmation needs
one deliberate `n` to check that declining still exits 2.

### Open

Two files still name the deleted OD-600 material:

- `tests/test_integration_dev_server.py` -- `protocol_path`, `deck_path`,
  `small_csv`, `full_csv`.
- `claude_test/show_error_detection.py` -- the deck configuration, the
  protocol, and the CSV.

Both talk to a **development server**, and there is none on this Windows
host, so re-pointing them at a surviving protocol could not be verified
here. Repointing blind would also lose real coverage: the OD-600
protocol was the only one exercising a file-type runtime parameter, the
96-channel pipette, the gripper, and a staging slot, and neither
`TestSingletip.py` nor `Test8tips.py` uses any of those. Choosing what
replaces that coverage is a decision, not a rename, and it is left open
rather than guessed at.

`CLAUDE.md` and `docs/flex_controller_spec_v0.3.md` also still describe
the OD-600 protocol as the project's reference. Both are governing
documents rather than instructions to a reader, so they are left for the
operator to amend deliberately.

### Follow-up: `claude_test/README.md`

`claude_test/README.md` is the index for that directory, and it had not
been updated when `audit_mit_convention.py` gained `collect` and `write`
in Task 12. It now records why the vocabulary was widened rather than the
functions renamed -- the auditor's own comment says a `naming-verb`
finding is "reported for a human to judge", so widening is the fix when
the reported word really is a verb -- and carries a dated table of what
has been added.

Documentation only; no code changed.

```
$ python -m pytest tests/ -q       79 passed, 23 skipped
$ ruff check .                     All checks passed!
$ ruff format --check .            7 files already formatted
$ python claude_test/audit_mit_convention.py
  files audited : 7 / findings : 0
```

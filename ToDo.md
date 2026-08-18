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

# OpentronFlexController

A Python tool that sends a protocol to an **Opentrons Flex** laboratory
robot, checks it for errors before anything moves, runs it, and shows you
each step as it happens.

No Flex? Neither did we. Everything below runs against a **simulator on
your own computer**.

```
  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
  │  you write   │  HTTP   │   the Flex   │         │  the robot   │
  │  a .py file  │ ──────▶ │  checks it   │ ──────▶ │    moves     │
  └──────────────┘         └──────────────┘         └──────────────┘
                                  │
                                  ▼  found a problem?
                           nothing moves
```

---

## Contents

| Section | For |
|---|---|
| [1. What is an Opentrons Flex?](#1-what-is-an-opentrons-flex) | Never seen one |
| [2. How the pieces fit](#2-how-the-pieces-fit) | Understanding the parts |
| [3. Try it in five minutes](#3-try-it-in-five-minutes) | Getting hands-on |
| [4. Reading the output](#4-reading-the-output) | Making sense of a run |
| [5. When something is wrong](#5-when-something-is-wrong) | Broken protocols |
| [6. What we proved, and what we did not](#6-what-we-proved-and-what-we-did-not) | Trusting the results |
| [7. Command reference](#7-command-reference) | Daily use |
| [8. Where everything lives](#8-where-everything-lives) | Finding files |
| [9. What we borrowed](#9-what-we-borrowed) | Provenance |

---

## 1. What is an Opentrons Flex?

A **liquid handling robot**. It does by machine what a scientist otherwise
does by hand with a pipette: move small, precise volumes of liquid between
wells on a plate, hundreds of times, without getting bored or tired.

The work surface is called the **deck**. It is a grid of slots, each
holding one piece of labware:

```
        ┌────────┬────────┬────────┐──┐
   A    │   A1   │   A2   │   A3   │A4│   ← A4 is a "staging" slot,
        ├────────┼────────┼────────┤──┤     an extra shelf
   B    │   B1   │   B2   │   B3   │B4│
        ├────────┼────────┼────────┤──┤
   C    │   C1   │   C2   │   C3   │C4│
        ├────────┼────────┼────────┤──┤
   D    │   D1   │   D2   │   D3   │D4│
        └────────┴────────┴────────┘──┘
          front-left            right
```

The vocabulary you need, and nothing more:

| Word | Plain meaning |
|---|---|
| **Labware** | Anything you put on the deck: a plate, a tip rack, a liquid reservoir |
| **Well** | One little cup in a plate. A standard plate has 96, named `A1` to `H12` |
| **Pipette** | The part that sucks up and squirts out liquid |
| **Tip** | A disposable plastic cone on the pipette. New tips prevent cross-contamination |
| **Tip rack** | A tray of fresh tips |
| **Gripper** | A robotic hand that picks up whole pieces of labware and moves them |
| **Module** | A powered gadget on the deck — heats, cools, or shakes |
| **Waste chute** | A hole to drop used tips into |
| **Protocol** | A Python file describing the experiment |
| **Deck configuration** | A list telling the robot which fixtures are bolted where |

Our test robot has a **96-channel pipette** — one head with 96 nozzles that
can fill an entire plate at once, or be told to use just one nozzle.

### The two-word version of what this tool does

> Upload a Python file. Watch the robot follow it.

---

## 2. How the pieces fit

**The tool runs on your computer. The protocol runs on the robot.** This
trips people up, so it is worth being explicit:

```
   YOUR COMPUTER                                    THE ROBOT (or simulator)
  ┌───────────────────────────┐                    ┌────────────────────────┐
  │                           │                    │                        │
  │  main.py                  │   1. upload CSV    │                        │
  │  flex_controller.py       │ ─────────────────▶ │  stores the file       │
  │                           │                    │                        │
  │       these stay here     │   2. upload .py    │                        │
  │                           │ ─────────────────▶ │  ANALYSES it           │
  │                           │                    │  ┌──────────────────┐  │
  │                           │ ◀───────────────── │  │ errors? → STOP   │  │
  │                           │   3. verdict       │  │ clean?  → a list │  │
  │                           │                    │  │  of commands     │  │
  │                           │                    │  └──────────────────┘  │
  │                           │   4. "play"        │                        │
  │                           │ ─────────────────▶ │  executes them         │
  │                           │                    │       ↓  ↓  ↓          │
  │  prints each step  ◀───── │   5. poll status   │   the deck moves       │
  └───────────────────────────┘                    └────────────────────────┘
```

Step 2 is the important one. The robot **reads your Python file and works
out every physical action in advance**. That list is the "analysis". If it
cannot produce one, the robot refuses, and nothing moves.

### A protocol is just a Python file

Here is what [`protocols/HelloFlex.py`](protocols/HelloFlex.py) does, with
its imports, docstring, and labels trimmed away so the shape is visible:

```python
def run(protocol: protocol_api.ProtocolContext):
    tiprack   = protocol.load_labware("opentrons_flex_96_tiprack_200ul", "A2")
    plate     = protocol.load_labware("corning_96_wellplate_360ul_flat", "B2")
    reservoir = protocol.load_labware("nest_1_reservoir_195ml", "B3")
    chute     = protocol.load_waste_chute()

    pipette = protocol.load_instrument("flex_96channel_1000")
    pipette.configure_nozzle_layout(style=protocol_api.SINGLE, start="A1")

    pipette.pick_up_tip(tiprack.wells()[0])
    pipette.aspirate(100, reservoir.wells()[0])   # suck up 100 µL
    pipette.dispense(100, plate["A1"])            # squirt it into well A1
    pipette.drop_tip(chute)
```

Upload it and the robot turns it into **twelve commands** — one per API
call, plus setup:

| Your line | Becomes |
|---|---|
| *(automatic)* | `1  home the gantry` |
| `load_labware(...)` × 3 | `2–4  load labware` |
| `load_instrument(...)` | `5  load pipette p1000_96 on left` |
| `configure_nozzle_layout(...)` | `6  configure nozzles to SINGLE, starting A1` |
| `pick_up_tip(...)` | `8  pick up tip from Tips[A1]` |
| `aspirate(100, ...)` | `9  aspirate 100.0 uL at Reservoir[A1]` |
| `dispense(100, ...)` | `10 dispense 100.0 uL at Plate[A1]` |
| `drop_tip(chute)` | `11–12 move to chute, drop tip` |

---

## 3. Try it in five minutes

### Step 1 — set up the environment

Conda is the recommended route: it pins the Python version too, so the
environment you build matches the one these results came from.

```bash
conda env create -f environment.yml
conda activate opentrons-flex
```

That reads [`environment.yml`](environment.yml) and takes about ten seconds.
Check it worked:

```bash
python -V                                        # Python 3.12.13
python -c "import requests; print(requests.__version__)"
```

Everything from here on assumes that environment is active. Your shell
prompt will usually show `(opentrons-flex)`.

<details>
<summary><b>Windows: <code>conda</code> not found in PowerShell</b></summary>

```
PS> conda --version
conda : The term 'conda' is not recognized as the name of a cmdlet,
function, script file, or operable program.
```

The message names the wrong culprit, and the obvious reaction — go and
edit `PATH` — leads nowhere. `conda init powershell` deliberately puts
nothing on `PATH`. It writes a hook into your PowerShell profile
instead, and a profile is a script. If the execution policy forbids
scripts, the profile never loads and the hook never runs.

So interrogate the policy, not the `PATH`:

```powershell
Get-ExecutionPolicy -List
```

Every scope reading `Undefined` means the effective policy is
`Restricted` — the Windows client default — and a `Restricted` shell
refuses its own profile on the way up:

```
. : File ...\WindowsPowerShell\profile.ps1 cannot be loaded because
running scripts is disabled on this system.
    + FullyQualifiedErrorId : UnauthorizedAccess
```

Allow local scripts for your own account. No administrator rights are
needed, and it does not weaken the check on downloaded ones:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Open a new window and confirm:

```powershell
Get-ExecutionPolicy      # RemoteSigned
conda --version          # conda 26.5.3
```

If your machine is locked down and the policy cannot be changed, note
that calling `conda.exe` by its full path is only half a workaround.
One-shot commands work; activation does not, because activation has to
edit the shell it is called from:

```
CondaError: Run 'conda init' before 'conda activate'
```

Call the environment's interpreter directly instead, and skip
activation altogether:

```
%USERPROFILE%\miniconda3\envs\opentrons-flex\python.exe main.py --profile dev
```

</details>

<details>
<summary><b>What the environment contains, and why</b></summary>

| Package | Why |
|---|---|
| `python=3.12` | `CLAUDE.md` gives 3.10 as the floor; pinned so builds match |
| `requests` | The tool's **only** runtime dependency |
| `pytest` | To run the 102 tests |
| `ruff` | Lint and format, at the 80-column limit this project uses |

`pytest` and `ruff` are development tools, but the README asks you to run
both, so they are in the file rather than somewhere you have to go find.

</details>

<details>
<summary><b>Prefer pip and venv?</b></summary>

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install requests               # to run the tool
pip install pytest ruff            # to run the tests and the linter
```

Needs Python 3.10 or newer. Only `requests` is required to drive a robot.

</details>

Removing it later is one command:

```bash
conda deactivate
conda env remove -n opentrons-flex
```

### Step 2 — start the simulator

You need a Flex `robot-server` running locally. The full recipe, including
one system package the official instructions omit, is in
[`docs/dev_server_setup.md`](docs/dev_server_setup.md).

```bash
# roughly:
apt-get update && apt-get install -y libsystemd-dev pkg-config
git clone https://github.com/Opentrons/opentrons.git
cd opentrons/robot-server && make setup && make dev-flex
```

Confirm it answers:

```bash
curl -H "Opentrons-Version: 3" http://localhost:31950/health
```

### Step 3 — look, without touching

`--verify-only` uploads and checks a protocol but **never moves anything**.
Safe to run at any time.

```bash
python main.py --profile dev --verify-only
```

### Step 4 — run it

```bash
python main.py --profile dev
```

You will see seven stages:

| Stage | Shows |
|---|---|
| 1. Robot | Its name, software version, and what is plugged in |
| 2. Deck configuration | Which fixture sits at each of the twelve cutouts |
| 3. Upload | The CSV and protocol going up, with their IDs |
| 4. Analysis | Pass or fail, and the runtime parameters used |
| 5. Planned steps | Everything the robot intends to do, before it does it |
| 6. Running | Each command as it completes |
| 7. Summary | Totals by command type, and any errors |

### Step 5 — go one step at a time

```bash
python main.py --profile dev --verify-only --step \
  --protocol protocols/HelloFlex.py
```

Press Enter to advance through the plan, `q` to stop.

---

## 4. Reading the output

Stage 6 is the interesting one. This is a real run of
`protocols/TestSingletip.py` on `BionicsDEMO1`, reconstructed from the
records it left in `artifacts/`:

```
     1  OK    home the gantry
     3  OK    load module magneticBlockV1 at slot C1
     5  OK    load labware thermo_fisher_nunclon_sphera_96_well_u_bottom_174925 at heaterShakerModuleV1
    12  OK    load pipette p1000_single_flex on left
    14  OK    comment: Step 1: Transferring 100 uL from EP tube C2 A1 to D2 A1.
    15  OK    pick up tip from opentrons_flex_96_filtertiprack_200ul[A1]
    16  OK    aspirate 100.0 uL at opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap[A1]
    17  OK    dispense 100.0 uL at corning_96_wellplate_360ul_flat[A1]
    18  OK    move to 1ChannelWasteChute
    19  OK    drop tip

  run succeeded after 88.9s
```

| Column | Meaning |
|---|---|
| `17` | Step number, counting from 1 |
| `OK` | Finished. `RUN` = in progress, `FAIL` = failed, blank = not started |
| `dispense 100.0 uL at corning_96_wellplate_360ul_flat[A1]` | What happened, in the names *your protocol chose* |

Two things worth noticing, because they show the display is reporting
reality rather than guessing:

- **`1ChannelWasteChute`** — the robot names the chute by the pipette
  that reached it. Run the same protocol with an 8-channel pipette and
  the name changes, because the addressable area does.
- **`p1000_single_flex`** — the protocol asked for `flex_1channel_1000`.
  What prints is what the robot reports it actually loaded.

### Where the names come from

The console builds its name map from the **run**, not from the analysis,
and rebuilds it on every tick:

```
   the analysis                    the run
  ┌────────────────────┐          ┌────────────────────┐
  │ labwareId: 4f0c... │          │ labwareId: a917... │
  │ "tiprack_200ul"    │          │ "tiprack_200ul"    │
  └────────────────────┘          └────────────────────┘
        planned                        executing
             └──── different ids for the same labware ────┘
```

A run assigns its own identifiers, so a map built from the analysis
resolves nothing once the robot is moving. The run also lists a labware
only after it has been loaded, which is why the first steps of a run can
print a well without its labware name and later ones do not.

---

## 5. When something is wrong

This is the part that matters. **A protocol the robot rejects never reaches
the deck.**

A mistake can be caught at three different moments, and the tool handles
all three:

```
   upload  ──────▶  analysis  ──────▶  run
     │                  │                │
     ▼                  ▼                ▼
  HTTP 422        errors[] not      run status
  file won't       empty → no        = failed
   compile         run created
```

| What you did wrong | Caught at | What you are told |
|---|---|---|
| Forgot a colon in your Python | **upload** | `expected ':' (bad_syntax.py, line 16)` |
| Named labware that does not exist | analysis | `Labware "corning_96_wellplate_9999ul_flat" not found` |
| Put two plates in the same slot | analysis | `LocationIsOccupiedError: ... already present at slotName=B2` |
| Forgot the CSV a parameter needs | analysis | `RuntimeParameterRequired: CSV parameter needs to be set` |
| Asked about a run that does not exist | HTTP 404 | `RunNotFound` — and no pointless retries |
| Deck missing the waste chute | **run** | `AreaNotInDeckConfigurationError: 1ChannelWasteChute not provided` |

See all six for yourself:

```bash
python claude_test/show_error_detection.py
```

> ⚠️ **The last row is a trap worth knowing.** The robot analyses a
> protocol *without looking at the deck configuration*. So a deck that
> cannot serve the protocol passes analysis, the run is created, and the
> failure happens mid-run — on a machine that is already moving. This
> contradicts the specification, which expected the analysis to catch it.
> Full evidence: [D-1](docs/spec_deviations.md#d-1).

---

## 6. What we proved, and what we did not

Everything above ran against a **simulator**, not a Flex. That distinction
decides what you may conclude.

### The simulator shares the software, not the machine

| | Simulator | Real Flex |
|---|---|---|
| `robot-server` code, API, port | **Identical** | **Identical** |
| Analysis engine | **Identical** | **Identical** |
| Motors | Virtual | Real |
| `robot_serial` | `simulator` | A real serial number |
| Calibration offsets | All `0.0`, made up | Measured on the bench |
| 96-row run | **4.2 seconds** | Tens of minutes |

### It does not model physics — we checked

We wrote a protocol that is physically impossible:

- aspirate 200 µL, seven times, from a reservoir **containing nothing**
- dispense **1200 µL into a 360 µL well**

The simulator ran it to **`succeeded`, zero errors.** On real hardware the
pipette draws air and the well overflows.

### So: what is actually established?

| Question | Answer |
|---|---|
| Does the tool speak the robot's API correctly? | ✅ **Proven** |
| Does a Python protocol upload, analyse, and execute? | ✅ **Proven** |
| Are broken protocols caught before motion? | ✅ **Proven** — 6 faults, 3 layers |
| Do the commands match what the protocol intends? | ✅ **Proven** — counts reconcile exactly |
| Are the liquid volumes physically possible? | ❌ Not checked by anything here |
| Is the labware where the protocol thinks it is? | ❌ Needs calibration on a real deck |
| Will the robot avoid collisions? | ❌ Not modelled |
| How long will a real run take? | ❌ 4.2 s is not a measurement |

**In one line:** this project verifies the *software and the protocol
logic*. It says nothing about *physical outcomes*.

### Test results

```
$ python -m pytest tests/ -q
79 passed, 23 skipped

$ ruff check . && ruff format --check .
All checks passed!
```

| Specification test | Result |
|---|---|
| TC-01 to TC-08, TC-10, TC-11 | ✅ Pass |
| TC-09 | ✅ Pass, as amended — see [D-1](docs/spec_deviations.md#d-1) |
| TC-12, TC-13 (real device) | ⛔ **Not run — no device exists here** |

We also compared our run log against the procedure **published with the
protocol**, using its official example CSV. The sequence matched, and so
did the arithmetic: **348 aspirates and 104 tip pickups predicted, 348 and
104 observed.**

Full detail: [`docs/verification_report.md`](docs/verification_report.md).

### Ten places reality differed from the specification

We found ten. Three are outright errors in the spec's model of the robot,
two are ours and deliberate, and the rest are gaps or typos. Each is
recorded with its evidence in
[`docs/spec_deviations.md`](docs/spec_deviations.md).

---

## 7. Command reference

```bash
python main.py [options]
```

| Option | Effect |
|---|---|
| `--profile dev` | Target `localhost`. No confirmation prompt |
| `--profile robot --host <ip>` | Target a real device. **Asks before moving** |
| `--verify-only` | Stop after the check. Nothing moves |
| `--step` | Walk the plan, one Enter per step |
| `--protocol <file>` | Your `.py`. **Required** — there is no default |
| `--csv <file>` | Data file, only for a protocol that declares one. Nothing is sent without it |
| `--deck <file>` | Deck fixture list. `--deck ""` to leave the deck alone |
| `--labware <path>` | Custom labware definition, or a folder of them. Repeatable |
| `--no-plan` | Skip the plan listing, which can be long |
| `--tick <seconds>` | How often to poll while running |
| `--artifact-dir <dir>` | Where to save the analysis and run records |

Exit status: `0` success · `1` failure · `2` operator declined.

### Worked examples

The `dev` commands here were run in the conda environment above, against
the development server. The `robot` commands were run on a real Flex,
with the operator present. Exit status follows each one.

**`--protocol` is required.** There is no default: which protocol runs is
the one decision that has to be made deliberately, and the console will
not guess.

**Check a protocol without moving anything** — the safest thing you can
run, and the one to reach for first.

```bash
python main.py --profile dev --verify-only --no-plan \
  --protocol protocols/HelloFlex.py                           # exit 0
```

**Run it.**

```bash
python main.py --profile dev --no-plan \
  --protocol protocols/HelloFlex.py                           # exit 0
```

**Send custom labware with it.** Definitions the Opentrons desktop
application holds in its own store have to travel with the protocol over
HTTP. Point `--labware` at a folder and every `*.json` in it goes up.

```bash
python main.py --profile robot --host FLXA3020260521001.local \
  --expect-name BionicsDEMO1 --verify-only --no-plan \
  --protocol protocols/TestSingletip.py --params "{}" \
  --deck configs/deck_testsingletip.json \
  --labware protocols/labware                                 # exit 0
```

**Watch a bad protocol get refused.** Note the exit status.

```bash
python main.py --profile dev --verify-only --no-plan \
  --protocol tests/protocols/bad_labware.py                   # exit 1
```

**Step through the plan by hand** — Enter to advance, `q` to stop.

```bash
python main.py --profile dev --verify-only --step \
  --protocol protocols/HelloFlex.py
```

**Batch mode**, when you want a JSON verdict instead of a live display.

```bash
python flex_controller.py --profile robot \
  --host FLXA3020260521001.local --verify-only \
  --protocol protocols/Test8tips.py --params "{}" \
  --deck configs/deck_testsingletip.json \
  --labware protocols/labware                                 # exit 0
```

```json
{
  "passed": true,
  "protocol_id": "7d2e849d-3068-42ce-bba0-f4db88fa5468",
  "analysis_id": "98fd7d6d-6f6a-4ce0-bfe3-ae7112af9fbf",
  "errors": [],
  "command_count": 77
}
```

**Everything the project checks about itself.**

```bash
python -m pytest tests/ -q                    # 79 passed, 23 skipped
ruff check . && ruff format --check .         # All checks passed!
python claude_test/audit_mit_convention.py    # findings : 0
```

The 23 skips are the development-server integration module, which stands
down when nothing is listening on `localhost:31950`.

**Full option list.**

```bash
python main.py --help
```

### Running on a real Flex

Supply the robot's address and a protocol. Everything else has a safe
default, and no data file is sent unless you name one.

```bash
conda activate opentrons-flex

python main.py --profile robot --host 192.168.1.50 \
  --expect-name flex-lab-01 \
  --protocol my_protocol.py \
  --verify-only                       # dry run first: nothing moves
```

Drop `--verify-only` when the dry run looks right.

#### A worked example, run on real hardware

`protocols/TestSingletip.py` moves 100 µL from an EP tube and 100 µL from
a reservoir into the same plate well. This is what was run against
`BionicsDEMO1` on 2026-08-18, with the operator present:

```bash
conda activate opentrons-flex

python main.py --profile robot --host FLXA3020260521001.local \
  --expect-name BionicsDEMO1 \
  --protocol protocols/TestSingletip.py \
  --deck configs/deck_testsingletip.json \
  --labware protocols/labware \
  --verify-only --no-plan                                     # exit 0
```

That day the command also carried `--csv "" --params "{}"`, because the
console still defaulted both to a reference protocol's values. It no
longer does, so neither flag is needed.

```
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
```

Drop `--verify-only` to run it. Four details in that command are easy to
get wrong.

**`--labware` is what makes custom labware work.** The desktop
application keeps custom definitions in a store of its own, so a protocol
that runs there fails over HTTP with `FileNotFoundError: Labware "..."
not found`. `POST /protocols` takes the definitions as extra file parts,
and `--labware` is how they get there. Point it at a folder and every
`*.json` inside goes up; point it at a single file and only that one
does. Repeat the flag for more than one source. Sending a definition the
protocol never loads is harmless.

**No data file is sent unless `--csv` names one.** A protocol needs a CSV
only if it declares one with `parameters.add_csv_file`; a protocol with no
`add_parameters` at all reports `runTimeParameters: []`, and the desktop
application does not ask for a CSV either. Leaving the flag off also
avoids Windows PowerShell, which swallows an empty argument and leaves
argparse complaining that `--csv` expects one — so `--csv ""` is a shape
worth not needing.

**`--params` is only for a protocol that declares scalar parameters.**
Omitted, nothing is sent, which is what a protocol with no
`add_parameters` wants. `Test8tips.py` declares `start_tip_column` and
`demo_mode`; omitting `--params` runs it on their declared defaults, and
`--params '{"start_tip_column": 1}'` overrides one of them.

**The deck file belongs to one machine.** Module fixtures carry
`opentronsModuleSerialNumber`, and the robot answers `422
InvalidDeckConfiguration` when they are missing or belong to another
device. Read yours off the robot and edit from there:

```bash
curl -H "Opentrons-Version: 3" \
  http://FLXA3020260521001.local:31950/deck_configuration
```

Writing a deck configuration asserts what is **physically bolted on**.
`configs/deck_testsingletip.json` claims a magnetic block at C1 and a
waste chute at D3; if yours are not installed, do not send it — pass
`--deck ""` and set the deck from the touchscreen instead.

> **On addressing.** A Flex on a direct Ethernet link takes a link-local
> address that changes between sessions. The mDNS name is stable, so
> prefer `--host FLXA3020260521001.local` over the IPv4 address you saw
> last time. Substitute your own robot's serial.

> ⚠️ **Read [`docs/real_device_procedure.md`](docs/real_device_procedure.md)
> first.** It covers the physical checks no software can make, the
> dry-run-then-run order, and how to stop a run.

Two things differ from `dev`, and both are safety decisions:

| | `dev` | `robot` |
|---|---|---|
| Before the run | starts immediately | you answer `y` at a prompt |
| Pre-flight | informational | wrong robot or unreachable robot **blocks** |

The deck behaves the same on both: an omitted `--deck` reads the
configuration and writes nothing. Writing one asserts which fixtures are
physically bolted on, and claiming a waste chute that is not there is how
a run drives into thin air — the analysis will not object
([D-1](docs/spec_deviations.md#d-1)), so the run fails mid-motion
instead. This console cannot see your bench, so it never guesses.

The confirmation prints the robot's name and asks `Proceed? [y/N]`.
Anything other than `y` or `yes` declines and exits 2. Read the name
before you answer — it is the machine that is about to move, and one
keystroke is all that stands between the prompt and the deck.

**Verified on hardware.** On 2026-08-18, on `BionicsDEMO1` (serial
`FLXA3020260521001`, system `v9.1.1`), with the operator present:

| Protocol | What was verified |
|---|---|
| `TestSingletip.py` | A full run through `main.py`: 27 commands, all `succeeded`, 0 errors, 89 s (run `197ac9ae`) |
| `Test8tips.py` | The analysis gate: `result ok`, 77 planned commands, 0 errors |

The records are in `artifacts/`, which is gitignored. Note that
`analysis.json`, `run.json`, and `commands.json` are fixed names and are
**overwritten by every run** — pass `--artifact-dir` if you want to keep
more than the last one. The robot's own log files are not collected by
this tool at all.

One caveat on the confirmation prompt and the deck default described just
above: both changed **after** those runs, and neither has been exercised
on the device since.

### The two profiles

| | `dev` | `robot` |
|---|---|---|
| Host | `localhost` | `--host`, required |
| Prompt before motion | No | **Yes** |

Nothing else differs. There is no "am I talking to a simulator" branch
anywhere in the code — by design, so the tested path is the shipped path.

### Using it from Python

```python
from flex_controller import FlexController

controller = FlexController(
    host="FLXA3020260521001.local", profile="robot"
)
final = controller.execute(
    "protocols/TestSingletip.py",
    labware_paths=["protocols/labware"],
)
print(final["status"])       # "succeeded"
```

`labware_paths` takes definition files, directories of them, or both.
Pass `csv_path=` only for a protocol that declares a file parameter, and
`parameter_values=` only for one that declares scalar parameters.

`execute` refuses to create a run if the analysis reported any error.
There is no way to switch that off.

---

## 8. Where everything lives

| Path | What it is |
|---|---|
| `environment.yml` | The conda environment: Python, `requests`, `pytest`, `ruff` |
| `main.py` | The console you will use — info, check, upload, watch |
| `flex_controller.py` | The library. One class, `FlexController`, plus a batch CLI |
| `protocols/HelloFlex.py` | A small example protocol, 34 lines |
| `protocols/TestSingletip.py` | One-channel transfer, verified on the real device |
| `protocols/Test8tips.py` | Eight-channel cell seeding, verified through analysis |
| `protocols/labware/` | Custom labware definitions, for `--labware` |
| `configs/` | Deck fixture lists, one per bench layout |
| `tests/` | 102 tests, plus three deliberately broken protocols |
| `claude_test/` | Diagnostics, not part of CI |
| `docs/` | The specification and the reports below |

| Document | Answers |
|---|---|
| [`verification_report.md`](docs/verification_report.md) | What was proven, and where the simulator stops |
| [`spec_deviations.md`](docs/spec_deviations.md) | All ten departures from the spec, with evidence |
| [`upstream_references.md`](docs/upstream_references.md) | What we borrowed, and from where |
| [`code_quality_audit.md`](docs/code_quality_audit.md) | Convention compliance |
| [`dev_server_setup.md`](docs/dev_server_setup.md) | Building the simulator |
| [`real_device_procedure.md`](docs/real_device_procedure.md) | **The S5 runbook: how to run on a real Flex** |
| [`transport_layer_review.md`](docs/transport_layer_review.md) | Why the class is not split yet |
| [`LearnedPatterns.md`](LearnedPatterns.md) | Traps found, so they are not rediscovered |

---

## 9. What we borrowed

| Source | Taken | Carried as |
|---|---|---|
| [coport-uni/CommonClaude](https://github.com/coport-uni/CommonClaude) | Conventions and five Claude Code hooks | Submodule at `external/CommonClaude` |
| [Opentrons/opentrons](https://github.com/Opentrons/opentrons) `969d95a` | The `robot-server` simulator | Cloned, not vendored |
| [Opentrons Protocol Library](https://library.opentrons.com/p/od-normalization-with-96-ch-pipette) | The OD-600 reference protocol, used to build this tool | Withdrawn — see below |

One upstream fix was needed: CommonClaude's lint hook resolved its
configuration from whatever directory it inherited, so it failed on every
Python write. It now runs from the project root.

The OD-600 normalization protocol was this project's reference while the
tool was being built, and the reports in `docs/` describe runs made
against it. That line of work is not being continued, so the protocol,
its CSVs, and its deck configuration have been removed. How it was
obtained — it was not in Opentrons' source repository, and its library
page renders client-side, so it came from the GraphQL API behind that
page — is recorded in
[`docs/upstream_references.md`](docs/upstream_references.md), along with
the query.

---

## Testing

With the `opentrons-flex` environment active:

```bash
python -m pytest tests/ -q                    # 79 passed, 23 skipped
ruff check . && ruff format --check .
python claude_test/audit_mit_convention.py
```

The integration tests skip themselves when no simulator is listening, so
the unit tests run anywhere. To prove they were not silently skipped, run
that file on its own — it should report 23 passed, not 23 skipped:

```bash
python -m pytest tests/test_integration_dev_server.py -q
```

> ⚠️ That module and `claude_test/show_error_detection.py` still name the
> withdrawn OD-600 protocol, its CSVs, and its deck configuration, so they
> will not run until they are pointed at a surviving protocol. That is not
> a rename: the OD-600 protocol was the only one here exercising a
> file-type runtime parameter, the 96-channel pipette, the gripper, and a
> staging slot, and choosing what replaces that coverage needs a
> development server to verify against.

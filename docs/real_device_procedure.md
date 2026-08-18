# Running on a Real Opentrons Flex

The procedure for stage S5, where the machine actually moves.

> **Nothing in this repository has been run on an Opentrons Flex.**
> Every result recorded elsewhere came from a simulator. This document is
> the plan for the first hardware contact, not a report of one. TC-12 and
> TC-13 are open.

---

## Before you start

The two things you supply are the robot's address and a protocol. Everything
else has a safe default, and no data file is sent unless you name one.

```bash
conda activate opentrons-flex

python main.py --profile robot --host 192.168.1.50 \
  --protocol my_protocol.py
```

### What the `robot` profile does differently

| | `dev` | `robot` |
|---|---|---|
| Host | `localhost` | `--host`, required |
| Deck configuration | reference layout is **written** | **read only** |
| Before the run | starts immediately | you must answer `y` at a prompt |

Two of those matter enough to explain.

**The deck is not written.** A deck configuration tells the robot which
fixtures are bolted where. Writing our reference layout to your robot
would assert a waste chute at cutout D3 whether or not one is physically
installed — and the analysis does not check
([D-1](spec_deviations.md#d-1)), so the mismatch would first appear
mid-run, on a moving machine. Pass `--deck <file>` only when you know the
file describes the deck in front of you.

**Typing "yes" will not start it.** The prompt asks for the robot's own
name. Muscle memory types "yes"; it cannot type the name of a machine you
have not looked at.

---

## The procedure

### Step 0 — the physical checks nobody can do for you

Five of the twelve items in spec §10 are not observable over HTTP. The
console will not check them, and will not pretend to.

| Spec §10 | Check | Why software cannot |
|---|---|---|
| 5, 6, 7 | Pipette, gripper, and modules **fitted** | The API reports what is registered, not what is bolted on |
| 8 | Deck fixtures **physically installed** | A chute either exists or does not; HTTP cannot see it |
| 10 | Labware position calibration done | Requires the machine and an operator |

Also confirm before anything else:

- [ ] The deck is loaded as your protocol expects — labware in the right slots
- [ ] Tip racks are full
- [ ] The **e-stop is within reach** and you know where it is
- [ ] Nobody is reaching into the machine

### Step 1 — pre-flight, which touches nothing

```bash
python main.py --profile robot --host 192.168.1.50 \
  --expect-name flex-lab-01 \
  --protocol my_protocol.py \
  --verify-only
```

`--expect-name` is worth the typing. Without it the console can only ask
you whether the name it found is the one you meant; with it, reaching the
wrong machine stops the run.

The pre-flight table uses three marks:

| Mark | Meaning |
|---|---|
| `OK` | Checked and correct |
| `LOOK` | Reported for you to judge. The console cannot know what your protocol needs |
| `STOP` | Blocks. Nothing is uploaded, no run exists, the robot has not moved |

Only two things block: an unreachable robot, and the wrong robot.

### Step 2 — TC-12, the dry run

`--verify-only` uploads the protocol, waits for the analysis, prints the
planned steps, and **stops**. The robot does not move.

```bash
python main.py --profile robot --host 192.168.1.50 \
  --expect-name flex-lab-01 \
  --protocol my_protocol.py \
  --verify-only \
  --artifact-dir runs/tc12
```

TC-12 passes when:

- [ ] The analysis reports `result: ok` and zero errors
- [ ] **The robot did not move.** Watch it; this is the acceptance criterion
- [ ] The planned steps read like the experiment you meant to run
- [ ] `runs/tc12/analysis.json` exists

Read the planned steps properly. This is the last point at which a
mistake costs nothing. To walk them one at a time, add `--step`.

**Do not continue to TC-13 until TC-12 has passed.**

### Step 3 — TC-13, the real run

```bash
python main.py --profile robot --host 192.168.1.50 \
  --expect-name flex-lab-01 \
  --protocol my_protocol.py \
  --artifact-dir runs/tc13
```

The confirmation appears before anything moves:

```
  robot                    flex-lab-01 at 192.168.1.50
  protocol                 my_protocol.py
  csv                      none
  planned commands         41
  deck                     left as the robot has it

  The deck will move. Stand clear and keep the e-stop within reach.
  The robot named above is the one that will move -- check it is the one
  you mean.

  Proceed? [y/N]:
```

Anything other than `y` or `yes` declines and exits 2. The robot's name
is printed above the prompt rather than typed into it, so reading it is
the step that catches the wrong machine.

Then each command prints as the robot completes it:

```
    15  OK    pick up tip from opentrons_flex_96_filtertiprack_200ul[A1]
    16  OK    aspirate 100.0 uL at opentrons_24_tuberack_eppendorf[A1]
    17  RUN   dispense 100.0 uL at corning_96_wellplate_360ul_flat[A1]
```

Record, per spec §9 stage S5:

- [ ] Final status and wall-clock duration
- [ ] `runs/tc13/run.json` and `commands.json`
- [ ] Any timing that made the configured limits look wrong

---

## Stopping a run

**Physical emergency: hit the e-stop.** Nothing below is faster.

Ctrl-C stops *the console*, not the robot. The console says so, and
prints the exact command to stop the run it started:

```bash
curl -X POST -H 'Opentrons-Version: 3' -H 'Content-Type: application/json' \
  -d '{"data": {"actionType": "stop"}}' \
  http://192.168.1.50:31950/runs/<run-id>/actions
```

The Opentrons app can also stop a run.

---

## When something fails

A fault surfaces at one of three layers, and where it surfaces tells you
what happened.

| Where | Meaning | The robot |
|---|---|---|
| Upload, HTTP 422 | The file will not compile | Never started |
| Analysis `errors` | The robot refuses to plan it | Never started |
| During the run | Something the plan could not predict | **Was moving** — check the deck before retrying |

The third case is the one to treat carefully. A deck configuration that
does not match the hardware lands here, as
`AreaNotInDeckConfigurationError` naming the area it could not find. See
[D-1](spec_deviations.md#d-1).

---

## Timings to re-measure

Spec §6 sets every timing from simulator behaviour, where a 96-row run
finishes in about four seconds. On real hardware the same run takes tens
of minutes, so these are guesses until S5 measures them:

| Setting | Current | Constructor argument |
|---|---|---|
| Analysis polling limit | 600 s | `analysis_limit` |
| Run polling period | 3 s | `run_period` |
| Single request timeout | 10 s | `timeout` |
| Upload timeout | 120 s | `upload_timeout` |

None is a literal inside a method (spec §4.3 rule 3), so all can be
retuned from `FlexController(...)` without touching the logic.

---

## Full option list

| Option | For a real device |
|---|---|
| `--profile robot` | Required. Enables the confirmation |
| `--host <ip>` | Required. No default exists, deliberately |
| `--expect-name <name>` | Strongly recommended. Wrong robot then stops the run |
| `--protocol <file>` | Your protocol |
| `--csv <file>` | Your data, only if the protocol declares a file parameter |
| `--verify-only` | TC-12. Nothing moves |
| `--step` | Walk the plan by hand before committing to it |
| `--deck <file>` | **Only** if the file describes the deck in front of you |
| `--artifact-dir <dir>` | Keep the records. Do this |
| `--tick <seconds>` | Poll interval; raise it for a long run |

Exit status: `0` success · `1` failure or blocked pre-flight · `2` you
declined.

There is no flag to skip the confirmation, and none to bypass the
analysis gate. Spec §4.4 and §5.2 make both mandatory.

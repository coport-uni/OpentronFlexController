# Deviations from Specification v0.3

Every point where the delivered tool departs from
[`flex_controller_spec_v0.3.md`](flex_controller_spec_v0.3.md), or where
the specification's description of `robot-server` proved wrong. Each entry
records what the spec says, what was observed, the evidence, and what
should change.

Observed against a `robot-server` development server built from Opentrons
commit `969d95a`, 2026-08-13. **No Opentrons Flex was involved.**

## Summary

| # | Spec says | Reality | Severity | Action |
|---|---|---|---|---|
| [D-1](#d-1) | §7, TC-09: a missing deck fixture is caught by the analysis | Analysis is clean; the run fails | **Spec is wrong** | Revise §7 and TC-09 |
| [D-2](#d-2) | §7: a syntax error is an "analysis error" | Refused at upload with HTTP 422 | **Spec is wrong** | Revise §7 |
| [D-3](#d-3) | TC-07: look for `flex_96channel_1000` in the analysis | The robot reports `p1000_96` | **Spec is wrong** | Revise TC-07 |
| [D-4](#d-4) | §2.4: a 3-to-8 row CSV to start | The gripper needs more than 96 rows | **Spec is incomplete** | Revise §2.4 and TC-07 |
| [D-5](#d-5) | §2.4: CSV header `source,destination,...` | Official file uses `source_wells,dest_wells,...` | Cosmetic | Revise §2.4 |
| [D-6](#d-6) | §4.1: entry points are the class and one CLI function | `main.py` is a second entry point | **Our deviation** | Accepted, recorded |
| [D-7](#d-7) | §4.3 rule 5: reconsider splitting above 30 methods | 32 methods | **Our deviation** | Reconsidered, deferred |
| [D-8](#d-8) | §2.1: tiprack `opentrons_flex_96tiprack_200ul` | Real name has a second underscore | Typo | Revise §2.1 |
| [D-9](#d-9) | §3.1: `make setup` at the top level | Needs libsystemd headers first | Incomplete | Revise §3.1 |
| [D-10](#d-10) | §1.3: the protocol uses three modules | They are loaded and never actuated | Overstated | Note in §1.3 |

---

## D-1 {#d-1}

### Protocol analysis ignores the deck configuration

**Spec §7** lists "deck configuration error — chute or staging slot not
registered" with the handling "abort, report the required fixture", and
**TC-09** requires that "with `cutoutD3` unregistered, an analysis error is
detected".

**Observed:** the analysis is clean and the run is created successfully.
The fault appears only when the robot reaches the missing area.

Verified with a byte-unique copy of the protocol, so that upload
deduplication could not return an earlier analysis:

```
=== analysis under BROKEN deck (cutoutD3 = singleRightSlot) ===
result: ok errors: 0
=== now create a RUN under the broken deck ===
POST /runs HTTP=201
run status: idle
```

Playing that run:

```
FINAL status: failed
errors: 1
 - ExceptionInProtocolError : AreaNotInDeckConfigurationError [line 85]:
   Error 4000 GENERAL_ERROR (AreaNotInDeckConfigurationError):
   1ChannelWasteChute not provided by deck configuration.
```

**Why it matters.** A clean analysis is not evidence that the deck can
serve the protocol. The two are checked independently, and anything built
on the assumption that the gate covers deck configuration is unsound.

**Recommended wording for §7:** move deck configuration errors from the
"analysis error" row to a new "run error" row, handled by collecting run
errors and reporting the named area. **TC-09** should assert
`status == "failed"` and `AreaNotInDeckConfigurationError`, which is what
`test_tc09_missing_waste_chute_fails_the_run` now does.

---

## D-2 {#d-2}

### A Python syntax error is refused at upload, not at analysis

**Spec §7** files "syntax, undefined labware" together under "analysis
error — blocks run creation".

**Observed:** `POST /protocols` compiles the file during the request and
answers HTTP 422. No protocol, no analysis, and no run are created.

```
$ python3 main.py --profile dev --protocol tests/protocols/bad_syntax.py
Failed: TransportError
  POST /protocols returned 422
  ProtocolFilesInvalid: expected ':' (bad_syntax.py, line 16)
```

Undefined labware, by contrast, does reach the analysis, so §7's grouping
is right for half of its examples.

**Consequence for the tool:** a protocol fault must be handled at three
layers, not one. `verify_only` raises `TransportError` for the first and
returns a failed verdict for the second; the third is only visible from
the run.

---

## D-3 {#d-3}

### The pipette load name never appears in a robot response

**TC-07** verifies 96-channel pipette recognition by "`flex_96channel_1000`
appearing in the analysis result".

**Observed:** that string appears nowhere. It is the Python API load name
used inside the protocol. The robot reports:

| Source | Value |
|---|---|
| `GET /instruments` | `p1000_96_v3.7` |
| analysis `pipettes[].pipetteName` | `p1000_96` |
| analysis `loadPipette` command | `p1000_96` |

**Recommended wording for TC-07:** "the analysis reports `p1000_96`, the
robot-side name for the pipette the protocol loads as
`flex_96channel_1000`."

---

## D-4 {#d-4}

### TC-07's gripper check is unreachable with the CSV of §2.4

**Spec §2.4** says verification starts with 3 to 8 rows and expands to 96
after it passes. **TC-07** requires a `moveLabware` command using the
gripper.

**Observed:** with 3 rows, the analysis contains **zero** `moveLabware`
commands. The protocol swaps tipracks only when the first is exhausted,
and it consumes one tip for the diluent phase plus one per data row. Fewer
than 96 rows never triggers the swap, so the gripper is never used.

| CSV rows | Commands | `moveLabware` |
|---|---|---|
| 3 | 41 | 0 |
| 96 | 788 | 2, both `usingGripper` |
| 103 (official) | 1128 | 2, both `usingGripper` |

**Recommended:** TC-07 should state that the gripper check requires the
96-row CSV, and §2.4 should say the 3-row file exercises transfer logic
only.

---

## D-5 {#d-5}

### The official CSV header differs from §2.4

**Spec §2.4** gives `source,destination,diluent_volume,dna_volume`.

**Observed** in the example file linked from the protocol's own Protocol
Library description:

```
source_wells,dest_wells,dil_volumes,dna_volumes
A1,B1,100,10
```

Both work, because the protocol skips the first row rather than reading it
as a header. Three further differences are worth recording: the official
file has **103 rows**, uses **CRLF** line endings, and its source and
destination wells **differ** (`A1` → `B1`), where §2.4's example maps each
well to itself.

The official file is vendored at `data/od_normalization_reference.csv`.

---

## D-6 {#d-6}

### `main.py` is a second entry point

**Spec §4.1** states that the externally exposed entry points are the
`FlexController` class and one CLI function.

**Delivered:** `main.py` adds an operator console. It is a client of the
class, calls only public methods, and adds no robot behaviour, but it is a
second entry point and is recorded as a deviation rather than glossed.

**Justification:** the spec's CLI prints a verdict, which suits batch use
but not standing in front of a machine watching it work. The alternative —
folding a step display into `flex_controller.main` — would have put
presentation logic inside the module the spec constrains most tightly.

---

## D-7 {#d-7}

### `FlexController` holds 32 methods

**Spec §4.3 rule 5** requires reconsidering a transport-layer split above
30 methods. `get_instruments` and `get_modules`, needed so the console can
show what is physically attached, took the count to 32.

The rule is a review trigger, not a cap. The reconsideration it prescribes
is [`transport_layer_review.md`](transport_layer_review.md), which declines
the split for now and names the four conditions that would force it.
`tests/test_flex_controller.py` asserts the exact count and requires that
document to exist, so the next method has to be argued for.

---

## D-8 {#d-8}

### Tiprack load name typo in §2.1

Spec §2.1 lists `opentrons_flex_96tiprack_200ul`. The real definition is
`opentrons_flex_96_tiprack_200ul`, with an underscore between `96` and
`tiprack`, which is what the protocol loads and what the analysis reports.

---

## D-9 {#d-9}

### The development server build needs a system package

**Spec §3.1** lists `git clone`, `make setup`, `make -C robot-server
dev-flex`. On a clean Ubuntu 24.04 container `make setup` fails:

```
× Failed to build `systemd-python==234`
  Cannot find libsystemd or libsystemd-journal
```

`apt-get update && apt-get install -y libsystemd-dev pkg-config` is a real
prerequisite. The `apt-get update` matters: a stale index gives 404s.

Two further notes. Running `make setup` inside `robot-server/` is enough;
the top-level target also builds the JavaScript workspace, which nothing
here uses. And the deck configuration is lost on every restart, because
`dev-flex.env` sets
`OT_ROBOT_SERVER_persistence_directory=automatically_make_temporary`.

The working procedure is [`dev_server_setup.md`](dev_server_setup.md).

---

## D-10 {#d-10}

### The reference protocol loads three modules but never uses them

**Spec §1.3** selects this protocol partly because it "uses three modules".
Its published description likewise says it "requires implementation of
Thermocycler module, Temperature modules and Heatershaker module".

**Observed:** the analysis contains 3 `loadModule` commands and **zero**
module action commands — no temperature is set, nothing shakes, no lid
moves. The modules are declared and left idle. The published description
concedes as much in its own last line: "The protocol can be amended to
remove the modules."

**Consequence:** the protocol exercises module *loading* and deck fixture
mapping, which is real coverage, but it does not exercise module
*control*. Any part of the tool concerned with module commands remains
unverified by this protocol.

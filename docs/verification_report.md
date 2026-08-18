# Verification Report

What this project has and has not established, and where the boundary
falls. Written so the boundary is explicit: a simulator can prove a great
deal about software and almost nothing about a machine.

Run against a `robot-server` development server built from Opentrons
commit `969d95a`, 2026-08-13. **No Opentrons Flex was involved at any
point.**

---

## 1. The short version

| Question | Answer |
|---|---|
| Does the tool speak the robot's API correctly? | **Yes, proven.** |
| Does a Python protocol upload, analyse, and execute? | **Yes, proven.** |
| Are broken protocols caught before the robot moves? | **Yes, proven** — six fault types, three layers |
| Would this protocol work on a real Flex? | **Unknown.** Not established, and this project cannot establish it. |
| Is the deck physically set up correctly? | **Unknown.** Not observable from software. |
| Will the liquid handling produce correct results? | **Unknown.** The simulator does not model liquid. |

## 2. Test results

```
$ python3 -m pytest tests/ -q
84 passed in 18.60s

$ ruff check . && ruff format --check .
All checks passed!
6 files already formatted

$ python3 claude_test/audit_mit_convention.py
findings      : 0
```

| Suite | Count | Needs a server | Covers |
|---|---|---|---|
| `test_flex_controller.py` | 37 | No | TC-01, TC-02, the analysis gate, profiles, spec §4.3 constraints |
| `test_main_console.py` | 24 | No | Command rendering, name resolution, failure reporting |
| `test_integration_dev_server.py` | 23 | Yes | TC-03 to TC-11, fault injection, console artifacts |

### Specification test plan (§8)

| ID | Case | Result |
|---|---|---|
| TC-01 | Response parsing against stored fixtures | **Pass** |
| TC-02 | 3 retries on 5xx, 0 on 4xx, 0 on run actions | **Pass** |
| TC-03 | `health` returns `opentrons-dev` | **Pass** |
| TC-04 | 12 deck fixtures read back | **Pass** |
| TC-05 | CSV upload appears in `GET /dataFiles` | **Pass** |
| TC-06 | Upload returns protocol and analysis identifiers | **Pass** |
| TC-07 | Clean analysis, six sub-checks | **Pass**, see note |
| TC-08 | Undefined labware blocks the run | **Pass** |
| TC-09 | Missing `cutoutD3` detected | **Pass as amended** — see [D-1](spec_deviations.md#d-1) |
| TC-10 | Full run reaches `succeeded` | **Pass** |
| TC-11 | `stop` after `play` reaches `stopped` | **Pass** |
| TC-12 | Real device dry-run | **NOT RUN — no device** |
| TC-13 | Real device full run | **NOT RUN — no device** |

TC-07's six sub-checks, measured on the 96-row CSV, because the gripper is
unreachable with fewer rows ([D-4](spec_deviations.md#d-4)):

| Sub-check | Evidence |
|---|---|
| 96-channel pipette recognised | `pipettes[0].pipetteName == "p1000_96"`, mount `left` |
| Nozzle layout changed | 1 `configureNozzleLayout`, `SINGLE`, primary `A1` |
| Gripper transfer | 2 `moveLabware`, both `usingGripper`, one to `D4` |
| Three modules loaded | 3 `loadModule`: thermocycler, temperature, heater-shaker |
| Waste chute used | 97 `moveToAddressableArea`, all `96ChannelWasteChute` |
| CSV reflected in transfers | 192 aspirates = 96 rows × 2 |

## 3. Error detection — six faults, three layers

The single most important property: **a protocol the robot has rejected
never reaches the deck.** Verified by injecting each fault and reading
what the tool reports.

| # | Injected fault | Caught at | Reported |
|---|---|---|---|
| 1 | Undefined labware load name | analysis | `Labware "corning_96_wellplate_9999ul_flat" not found with version 1 in namespace "opentrons"` |
| 2 | Python syntax error | **upload, HTTP 422** | `ProtocolFilesInvalid: expected ':' (bad_syntax.py, line 16)` |
| 3 | Two labware in slot B2 | analysis | `LocationIsOccupiedError: Labware corning_96_wellplate_360ul_flat is already present at slotName=B2` |
| 4 | Missing CSV runtime parameter | analysis | `RuntimeParameterRequired: CSV parameter needs to be set to a file for full analysis or run` |
| 5 | Unknown run identifier | HTTP 404 | `RunNotFound`, no retry issued |
| 6 | `cutoutD3` without the waste chute | **run** | `AreaNotInDeckConfigurationError: 1ChannelWasteChute not provided by deck configuration` |

For faults 1, 3, and 4, `list_runs()` was unchanged: no run was created.

Reproduce with `python3 claude_test/show_error_detection.py`.

## 4. Agreement with the published procedure

The protocol's Protocol Library description was fetched and compared
against the observed command log, using the official example CSV linked
from that description.

| Published description | Observed |
|---|---|
| "requires Thermocycler, Temperature, Heatershaker modules" | 3 `loadModule` — but 0 module actions, [D-10](spec_deviations.md#d-10) |
| "reads the CSV to extract source wells, destination wells, diluent volumes, and DNA volumes" | Matches row for row |
| "transfers diluent from the reservoir to the normalization plate" | Step 116 comment, step 118 `Diluent Reservoir` → `Normalization Plate` |
| "followed by the transfer of DNA samples from the culture plate" | Step 610 comment, step 612 `Culture Plate` |
| "switching to the second tip rack when necessary" | Step 1086 comment, 2 gripper `moveLabware` |
| "optimized to use a trash bin or a waste chute" | Waste chute path exercised |

**The counts reconcile arithmetically**, which is stronger evidence than
the sequence matching:

| Quantity | Predicted from the CSV | Observed |
|---|---|---|
| Aspirates | 348 | **348** |
| Tip pickups | 104 | **104** |

The aspirate figure is not simply rows × 2: 82 of the 103 diluent volumes
exceed the 200 µL tip capacity, so `transfer()` splits them. Predicting
that correctly, and matching exactly, shows the tool is reporting the
robot's real plan rather than an approximation.

## 5. What the simulator cannot establish

This is the section to read before trusting anything above as evidence
about hardware.

### 5.1 It shares the software, not the machine

| Aspect | Development server | Real Flex |
|---|---|---|
| `robot-server` codebase | Same | Same |
| HTTP API, port, `Opentrons-Version` | Same | Same |
| Protocol analysis engine | Same | Same |
| Motion controller | `ENABLE_VIRTUAL_SMOOTHIE=true` | Real motors |
| `robot_serial` | `simulator` | Real serial |
| `fw_version` | `0` | Real firmware |
| `system_version` | `0.0.0` | 7.x / 8.x |
| Calibration offsets | All `0.0`, fabricated | Measured by LPC and pipette calibration |
| 96-row run duration | **4.2 s** | Tens of minutes |
| Door sensor, e-stop | Absent | Present |

### 5.2 It does not model physics — demonstrated

A protocol was written that is physically impossible, and the simulator
ran it to `succeeded` with zero errors:

- aspirates 200 µL, seven times, from a reservoir that was **never given
  any liquid**
- dispenses **1200 µL total into a 360 µL well**

```
analysis result: ok | errors: 0
     8  OK    aspirate 200.0 uL at nest_1_reservoir_195ml[A1]
     9  OK    dispense 200.0 uL at corning_96_wellplate_360ul_flat[A1]
     ...
  run succeeded
```

On real hardware the first aspirate draws air and the well overflows.

### 5.3 The boundary, stated plainly

| Category | Established here? |
|---|---|
| HTTP protocol correctness, retry policy, error handling | **Yes** |
| Protocol file compiles and analyses | **Yes** |
| Command sequence matches the protocol's intent | **Yes** |
| Deck fixture registration and staging-slot mapping | **Yes**, in software |
| Runtime parameter plumbing, including file-type CSV | **Yes** |
| Liquid volumes are physically achievable | **No** |
| Labware is where the protocol thinks it is | **No** — needs LPC |
| Pipette and gripper are calibrated | **No** — offsets are fabricated |
| Deck fixtures are physically installed | **No** — spec §10 items 8 and 9 |
| Timing and throughput | **No** — 4.2 s is not a measurement |
| Collision-free motion | **No** |
| Module control (temperature, shaking, lid) | **No** — never exercised, [D-10](spec_deviations.md#d-10) |

## 6. Before a real device

Spec §10's checklist, with what remains open. Items 1 to 4 are the only
ones software could close.

| # | Item | State |
|---|---|---|
| 1 | TC-01 to TC-11 pass | **Done** |
| 2 | Device reachable | Open |
| 3 | Robot software 7.0.0+, apiLevel 2.20 | Open |
| 4 | `health` name matches the intended device | Tool supports it; profile `robot` |
| 5 | 96-channel pipette fitted | Open |
| 6 | Gripper fitted | Open |
| 7 | Three modules connected | Open |
| 8 | Deck fixtures physically installed | Open — **not observable from software** |
| 9 | Deck configuration registered | Tool does this; physical match unverifiable |
| 10 | Labware position calibration complete | Open |
| 11 | Profile switched to `robot` | Supported, prompts before motion |
| 12 | Dry-run before the full run | Supported via `--verify-only` |

Given [D-1](spec_deviations.md#d-1), item 9 deserves particular care: the
analysis will not warn about a deck configuration that does not match the
protocol. The mismatch appears mid-run, on a machine that is already
moving.

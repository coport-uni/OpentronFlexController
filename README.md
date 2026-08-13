# OpentronFlexController

Python control tool for the **Opentrons Flex** liquid handler. It uploads
a protocol, gates on the pre-run analysis, drives the run, and collects
robot state and errors by calling the `robot-server` HTTP API directly.

The development specification is
[`docs/flex_controller_spec_v0.3.md`](docs/flex_controller_spec_v0.3.md).

| Item | Value |
|---|---|
| Device | Opentrons Flex (`ot3`) |
| Transport | `robot-server` HTTP API, port 31950 |
| Required header | `Opentrons-Version: 3` |
| Language | Python 3.10+ |
| Runtime dependency | `requests` |

## Install

```bash
pip install requests
```

## What actually runs where

`main.py` and `flex_controller.py` run **on your computer**. What goes to
the robot is the **protocol** — an ordinary Python file — which the Flex
compiles into a list of commands and executes:

```
your_protocol.py  ──POST /protocols──▶  Flex analyses it
                                            │
                                            ▼
                                    a list of commands
                                            │
                          POST /runs/{id}/actions {"play"}
                                            ▼
                                   the robot executes them
```

`protocols/hello_flex.py` is a twenty-line example. Uploading it produces
twelve robot commands, one per API call in the file.

## Use

### Watch it run, step by step

`main.py` is the operator console: it reads the robot's information,
verifies the protocol, uploads it, and prints each command as the robot
completes it.

```bash
python3 main.py --profile dev
```

```
     1  OK    home the gantry
     5  OK    load labware Culture Plate at temperatureModuleV2
    11  OK    configure nozzles to SINGLE, starting A1
    17  OK    pick up tip from Tiprack 1[H12]
    18  OK    aspirate 90.0 uL at Diluent Reservoir[A1]
    19  OK    dispense 90.0 uL at Normalization Plate[A1]
    24  OK    move to 96ChannelWasteChute
```

Upload your own protocol, and stop before anything moves:

```bash
python3 main.py --profile dev --protocol protocols/hello_flex.py \
  --csv "" --verify-only
```

Walk the planned steps one at a time, pressing Enter between each:

```bash
python3 main.py --profile dev --verify-only --step
```

| Option | Effect |
|---|---|
| `--verify-only` | stop after the analysis gate; nothing moves |
| `--step` | advance the planned steps by hand |
| `--no-plan` | skip the plan listing, which is long |
| `--tick` | seconds between reads while the run is in flight |
| `--csv ""` | for a protocol with no file parameter |

Exit status is 0 on success, 1 on a reported failure, 2 if the operator
declined the run.

### Batch use

Analyse a protocol without running it:

```bash
python3 flex_controller.py --profile dev --verify-only \
  --protocol protocols/OD_Normalization.py \
  --csv data/od_normalization.csv \
  --deck configs/deck_od_normalization.json \
  --params '{"dry_run": true, "waste_type": 1}'
```

Run it:

```bash
python3 flex_controller.py --profile dev \
  --protocol protocols/OD_Normalization.py \
  --csv data/od_normalization.csv \
  --deck configs/deck_od_normalization.json \
  --params '{"dry_run": true, "waste_type": 1}'
```

From Python:

```python
from flex_controller import FlexController

controller = FlexController(profile="dev")
final = controller.execute(
    "protocols/OD_Normalization.py",
    csv_path="data/od_normalization.csv",
    parameter_values={"dry_run": True, "waste_type": 1},
)
print(final["status"])
```

### Profiles

| Profile | Host | Confirmation | Use |
|---|---|---|---|
| `dev` | `localhost` | not required | development server |
| `robot` | `--host`, required | required before the robot moves | real device |

The two differ only in host and confirmation. No behaviour keys off
"is this the development server".

## The analysis gate

`execute` polls the analysis until it completes and refuses to create a
run if the analysis reported any error. The gate applies to both
profiles and has no bypass option — a protocol the robot has rejected
never reaches the deck.

A protocol fault surfaces at one of three layers, so all three are
handled:

| Fault | Where it surfaces | What the tool raises |
|---|---|---|
| Python syntax error | `POST /protocols`, HTTP 422 | `TransportError` with the file and line |
| Undefined labware, slot collision, missing runtime parameter | analysis `errors` | `AnalysisError` |
| Deck fixture missing | during the run | run reaches `failed`; `get_errors` names the area |

The third row is a documented deviation from spec §7, which expects the
analysis to catch it. robot-server analyses a protocol without reference
to the deck configuration; see
[`LearnedPatterns.md`](LearnedPatterns.md) §3.

## Development server

No real device is used before the S5 acceptance stage (spec §1.2). The
recorded build procedure is
[`docs/dev_server_setup.md`](docs/dev_server_setup.md).

## Tests

```bash
python3 -m pytest tests/ -v
```

`tests/test_flex_controller.py` substitutes `_request` and needs no
server. `tests/test_integration_dev_server.py` drives a real development
server and skips itself when none is listening.

To see what the tool reports for each deliberately broken protocol:

```bash
python3 claude_test/show_error_detection.py
```

## Layout

| Path | Contents |
|---|---|
| `main.py` | Operator console: robot info, verify, upload, step-by-step run |
| `flex_controller.py` | The `FlexController` class and the batch CLI |
| `protocols/` | The reference protocol, plus `hello_flex.py` as a minimal example |
| `data/` | Verification CSVs, 3-row and 96-row |
| `configs/` | The deck fixture list of spec §3.4 |
| `tests/` | Unit and integration tests, fixtures, fault protocols |
| `claude_test/` | Diagnostic scripts, not part of CI |
| `external/CommonClaude` | Shared conventions, as a submodule |

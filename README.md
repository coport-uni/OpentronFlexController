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

## Use

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
| `flex_controller.py` | The `FlexController` class and the CLI |
| `protocols/` | The reference protocol, OD-600 normalization |
| `data/` | Verification CSVs, 3-row and 96-row |
| `configs/` | The deck fixture list of spec §3.4 |
| `tests/` | Unit and integration tests, fixtures, fault protocols |
| `claude_test/` | Diagnostic scripts, not part of CI |
| `external/CommonClaude` | Shared conventions, as a submodule |

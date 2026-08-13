# Flex Development Server Setup

The procedure actually used to bring up the `robot-server` development
server this repository is verified against, on Ubuntu 24.04 in a Docker
container. It records what was run, not what was planned; where it
departs from spec §3.1, the departure is called out.

Verified on 2026-08-13 against Opentrons commit `969d95a`.

## 1. Prerequisites

`robot-server` depends on `systemd-python`, which is built from source
and needs the libsystemd headers. Without them `make setup` fails while
building the wheel, with `Package 'libsystemd' was not found in the
pkg-config search path`.

```bash
apt-get update
apt-get install -y libsystemd-dev pkg-config
```

> **Deviation from spec §3.1.** The spec lists `git clone`, `make setup`,
> `make -C robot-server dev-flex` and no system packages. The libsystemd
> headers are a real prerequisite on a clean container.

## 2. Clone and sync

```bash
git clone --depth 1 https://github.com/Opentrons/opentrons.git
cd opentrons/robot-server
make setup
```

`make setup` drives `uv sync`, which builds an isolated environment for
the server. The top-level `make setup` of spec §3.1 also builds the
JavaScript workspace, which nothing in this project uses; running the
`robot-server` target alone is enough and much faster.

## 3. Install the simulator configuration

The simulator configuration is under configuration management in this
repository at [`sim-od-normalization.json`](sim-od-normalization.json)
(spec §11). Copy it into the server tree and point the environment file
at it:

```bash
cp docs/sim-od-normalization.json \
   <opentrons>/robot-server/simulators/
sed -i \
  's|simulator_configuration_file_path=simulators/test-flex.json|simulator_configuration_file_path=simulators/sim-od-normalization.json|' \
  <opentrons>/robot-server/dev-flex.env
```

## 4. Start the server

```bash
make -C robot-server dev-flex
```

## 5. Confirm the simulated hardware

The server is only useful if it presents the instruments spec §2.1
requires. Check all three, not just health:

```bash
curl -H "Opentrons-Version: 3" http://localhost:31950/health
curl -H "Opentrons-Version: 3" http://localhost:31950/instruments
curl -H "Opentrons-Version: 3" http://localhost:31950/modules
```

Expected, and observed on 2026-08-13:

| Endpoint | Expected |
|---|---|
| `/health` | `name` is `opentrons-dev`, `robot_model` is `OT-3 Standard` |
| `/instruments` | `p1000_96_v3.7` on `left`, `gripperV1` on `extension` |
| `/modules` | `thermocyclerModuleV2`, `temperatureModuleV2`, `heaterShakerModuleV1` |

Note that the pipette is reported as `p1000_96_v3.7` and appears in
analyses as `p1000_96`. The protocol loads it as `flex_96channel_1000`;
that string is the Python API load name and does not appear in any
robot response.

## 6. Apply the deck configuration

The persistence directory is temporary (`automatically_make_temporary`),
so **the deck configuration is lost on every restart** and must be
reapplied. This is the risk spec §11 anticipates. The tool applies it as
step 3 of `execute`, so the file is the only thing that needs to survive:

```bash
python3 flex_controller.py --profile dev --verify-only \
  --protocol protocols/OD_Normalization.py \
  --csv data/od_normalization.csv \
  --deck configs/deck_od_normalization.json \
  --params '{"dry_run": true, "waste_type": 1}'
```

## 7. Run the verification suite

```bash
python3 -m pytest tests/ -v
```

The integration module skips itself when nothing is listening on
port 31950, so the unit tests still run without a server.

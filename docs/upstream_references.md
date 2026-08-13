# Upstream References

Every external source this project draws on: what was taken, from where,
and why. Recorded so a later reader can tell our work from other people's,
and can re-fetch anything that changes upstream.

## Summary

| Source | How it is carried | What it gives us |
|---|---|---|
| [coport-uni/CommonClaude](https://github.com/coport-uni/CommonClaude) | Git submodule, `external/CommonClaude` | Development conventions and Claude Code hooks |
| [Opentrons/opentrons](https://github.com/Opentrons/opentrons) | Cloned outside the repo, not vendored | The `robot-server` development server |
| [Opentrons Protocol Library](https://library.opentrons.com) | Two files vendored | The reference protocol and its official CSV |

---

## 1. CommonClaude — conventions

**Repository:** `https://github.com/coport-uni/CommonClaude`
**Carried as:** a submodule at `external/CommonClaude`, so the upstream
version is pinned and updatable.

### What was taken

| Item | Destination | Modified? |
|---|---|---|
| `CLAUDE.md` §1–§17 | `CLAUDE.md`, below a project-specific header | No — copied verbatim |
| `.claude/settings.json` | `.claude/settings.json` | No |
| `pre-write-guard.sh` | `.claude/hooks/` | No |
| `pre-bash-secret-scan.sh` | `.claude/hooks/` | No |
| `pre-read-env-guard.sh` | `.claude/hooks/` | No |
| `post-write-debug-remind.sh` | `.claude/hooks/` | No |
| `post-write-lint.sh` | `.claude/hooks/` | **Yes — one fix** |

### The one modification

`post-write-lint.sh` failed on every Python write with a TOML parse error
pointing at an unrelated `/tmp/ruff.toml`. Ruff resolves its configuration
starting from the working directory, and the hook was using whatever
directory it happened to inherit. Added before the ruff calls:

```bash
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$file_path")}"
```

This is a candidate to send upstream: any project whose hook runs from an
unexpected directory hits the same fault.

### Rules that shaped the work

| Rule | Effect here |
|---|---|
| §2 MIT convention | 80 columns, verb-shaped functions, Google docstrings — audited in [`code_quality_audit.md`](code_quality_audit.md) |
| §4 Task management | Every task has a `ToDo.md` entry, a GitHub issue, a branch, and a PR |
| §5.1 Verification gate | Why TC-12 and TC-13 remain unrun and nothing is described as hardware-verified |
| §6 Ruff | `ruff.toml` at 80 columns, enforced by the write hook |
| §8 Exceptions | `claude_test/` waivers encoded as `per-file-ignores` rather than left in prose |
| §10 Learned patterns | [`LearnedPatterns.md`](../LearnedPatterns.md) bootstrapped from completed items |

---

## 2. Opentrons/opentrons — the development server

**Repository:** `https://github.com/Opentrons/opentrons`
**Commit used:** `969d95a`
**Carried as:** cloned outside this repository. Nothing is vendored — it
is a build dependency, not source we ship.

### What it provides

The `robot-server` package, run with the `dev-flex` target, which serves
the same HTTP API as a real Flex on port 31950. This is what makes spec
§1.2 workable: design, implementation, and integration test all run
against it without a device.

### What was read from the source, and why

Rather than guess at the API, these files were read before writing code
against them:

| Path | Question it answered |
|---|---|
| `robot-server/Makefile` | How `dev-flex` starts; that `uv` drives the build |
| `robot-server/dev-flex.env` | Which environment variables define the simulator, and that persistence is temporary |
| `robot-server/simulators/test-flex.json` | The shape our `sim-od-normalization.json` had to match |
| `robot-server/robot_server/deck_configuration/` | The `PUT /deck_configuration` body, and `opentronsModuleSerialNumber` |
| `shared-data/deck/definitions/5/ot3_standard.json` | Which `cutoutFixtureId` values are legal for each cutout |

That last file confirmed all twelve fixture identifiers in spec §3.4 are
valid, including
`stagingAreaSlotWithWasteChuteRightAdapterNoCover` for `cutoutD3`.

### What was changed in the clone

Neither change belongs to this repository; both are recorded in
[`dev_server_setup.md`](dev_server_setup.md) so the environment can be
rebuilt.

1. `docs/sim-od-normalization.json` copied into `robot-server/simulators/`
2. `dev-flex.env` pointed at that file instead of `test-flex.json`

### Build prerequisite not in the spec

`make setup` fails on a clean Ubuntu 24.04 container without libsystemd
headers, because `systemd-python` is built from source. See
[D-9](spec_deviations.md#d-9).

---

## 3. Opentrons Protocol Library — the reference protocol

**Page:** `https://library.opentrons.com/p/od-normalization-with-96-ch-pipette`
**Protocol:** OD-600 Normalization using 96-channel pipette
**Author:** Anurag Kanase, Opentrons
**API level:** 2.20

### How it was obtained

Not from the source repository — it is not there. The library page renders
entirely on the client, so its HTML carries no code. The protocol is
served by a GraphQL API behind the page:

```bash
curl -X POST https://library.opentrons.com/api/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"query($slug:String!){getProtocolBySlug(slug:$slug){name filename protocolText}}",
       "variables":{"slug":"od-normalization-with-96-ch-pipette"}}'
```

`protocolText` holds the source. The same query returns `description`,
which was used for the procedure comparison in
[`verification_report.md`](verification_report.md) §4.

### What was vendored

| File | Source | Modified? |
|---|---|---|
| `protocols/OD_Normalization.py` | `protocolText` | **No** — byte-exact, and excluded from ruff so it stays that way |
| `data/od_normalization_reference.csv` | Google Drive link in the description | **No** — 103 rows, CRLF preserved |

The protocol is excluded from linting deliberately: reformatting it would
make it a different protocol from the one the spec names as the single
integration-test reference.

### Why this protocol

Spec §1.3 chooses it because one run exercises the 96-channel pipette, the
gripper, three modules, a staging slot, the waste chute, and a file-type
runtime parameter — most of the API surface the tool must handle. That
holds, with one correction: the modules are loaded but never actuated, so
module *control* is not covered. See [D-10](spec_deviations.md#d-10).

---

## 4. Written here, not taken

To keep the boundary clear, these are ours:

| File | What it is |
|---|---|
| `flex_controller.py` | The `FlexController` class and batch CLI |
| `main.py` | The operator console |
| `protocols/hello_flex.py` | A minimal example protocol |
| `tests/protocols/*.py` | Three deliberately broken protocols |
| `data/od_normalization.csv`, `data/od_normalization_96.csv` | Verification CSVs per spec §2.4 |
| `configs/deck_od_normalization.json` | The twelve deck fixtures of spec §3.4 |
| `tests/**` | 84 tests |
| `claude_test/*.py` | Diagnostic scripts |
| `docs/*.md` except the spec | This document and its siblings |

`docs/flex_controller_spec_v0.3.md` and `docs/sim-od-normalization.json`
were supplied with the project.

## 5. Re-fetching

```bash
# Conventions
git submodule update --remote external/CommonClaude

# Development server
git clone https://github.com/Opentrons/opentrons.git

# Reference protocol
curl -X POST https://library.opentrons.com/api/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"query($slug:String!){getProtocolBySlug(slug:$slug){protocolText}}",
       "variables":{"slug":"od-normalization-with-96-ch-pipette"}}'
```

Re-fetching the protocol or the simulator configuration means re-running
TC-03 through TC-11, per spec §11.

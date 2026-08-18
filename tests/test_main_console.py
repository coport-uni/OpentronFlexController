"""Unit tests for the operator console.

The console's job is to turn robot documents into lines a person can
read, so these tests check the rendering rather than the transport.
They need no server.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from flex_controller import AnalysisError, TransportError  # noqa: E402
from main import check_before_running  # noqa: E402

pipette_id = "pipette-1"
tiprack_id = "tiprack-1"
plate_id = "plate-1"
module_id = "module-1"

# A run and its analysis assign different identifiers to the same
# labware, which is the trap these tests exist to guard.
run_document = {
    "status": "running",
    "labware": [
        {
            "id": tiprack_id,
            "loadName": "opentrons_flex_96_tiprack_200ul",
            "displayName": "Tiprack 1",
        },
        {
            "id": plate_id,
            "loadName": "corning_96_wellplate_360ul_flat",
            "displayName": "Normalization Plate",
        },
    ],
    "modules": [{"id": module_id, "model": "temperatureModuleV2"}],
    "pipettes": [{"id": pipette_id, "pipetteName": "p1000_96"}],
}


@pytest.fixture
def names() -> dict[str, str]:
    """Provide the identifier-to-name map built from the run.

    Returns:
        Identifier to display name.
    """
    return main.build_name_map(run_document)


# ---- Name resolution --------------------------------------------------


def test_name_map_prefers_the_label_the_protocol_chose(names):
    """A protocol's own label is more use than a catalogue name."""
    assert names[tiprack_id] == "Tiprack 1"
    assert names[plate_id] == "Normalization Plate"


def test_name_map_falls_back_to_the_load_name():
    """Labware loaded without a label still gets a name."""
    document = {"labware": [{"id": "x", "loadName": "nest_1_reservoir_195ml"}]}

    assert main.build_name_map(document)["x"] == "nest_1_reservoir_195ml"


def test_name_map_covers_modules_and_pipettes(names):
    """Commands name modules and pipettes by identifier too."""
    assert names[module_id] == "temperatureModuleV2"
    assert names[pipette_id] == "p1000_96"


def test_name_map_handles_a_document_with_nothing_loaded_yet():
    """A run reports no labware until the load commands execute."""
    assert main.build_name_map({"status": "idle"}) == {}


# ---- Locations --------------------------------------------------------


def test_slot_location_reads_as_a_slot(names):
    """A deck slot is named directly."""
    assert main.describe_location({"slotName": "B2"}, names) == "slot B2"


def test_staging_location_reads_as_an_area(names):
    """A staging slot is an addressable area, not a deck slot."""
    assert main.describe_location({"addressableAreaName": "A4"}, names) == (
        "area A4"
    )


def test_module_location_resolves_to_the_module(names):
    """Labware on a module is located by the module, not a slot."""
    assert main.describe_location({"moduleId": module_id}, names) == (
        "temperatureModuleV2"
    )


def test_unknown_location_shape_does_not_raise(names):
    """An unfamiliar location is skipped, not fatal."""
    assert main.describe_location({"somethingNew": "?"}, names) == ""
    assert main.describe_location(None, names) == ""


# ---- Command rendering ------------------------------------------------


def test_aspirate_names_its_volume_and_well(names):
    """The line an operator reads most often must be exact."""
    command = {
        "commandType": "aspirate",
        "params": {
            "labwareId": plate_id,
            "wellName": "A1",
            "volume": 90.0,
        },
    }

    assert main.describe_command(command, names) == (
        "aspirate 90.0 uL at Normalization Plate[A1]"
    )


def test_gripper_move_is_called_a_gripper_move(names):
    """The gripper is the point of a moveLabware; say so."""
    command = {
        "commandType": "moveLabware",
        "params": {
            "labwareId": tiprack_id,
            "newLocation": {"addressableAreaName": "D4"},
            "strategy": "usingGripper",
        },
    }

    assert main.describe_command(command, names) == (
        "move Tiprack 1 to area D4 using the gripper"
    )


def test_comment_is_shown_verbatim(names):
    """A protocol's comment is the author speaking to the operator."""
    command = {
        "commandType": "comment",
        "params": {"message": "Transferring Diluent"},
    }

    assert main.describe_command(command, names) == (
        "comment: Transferring Diluent"
    )


def test_nozzle_configuration_names_the_style(names):
    """The 96-channel pipette's nozzle mode changes what it does."""
    command = {
        "commandType": "configureNozzleLayout",
        "params": {
            "configurationParams": {"style": "SINGLE", "primaryNozzle": "A1"}
        },
    }

    assert main.describe_command(command, names) == (
        "configure nozzles to SINGLE, starting A1"
    )


def test_an_unknown_command_still_renders(names):
    """A command this console has not met is shown, not swallowed.

    The robot's vocabulary grows; a console that hid what it did not
    recognise would quietly under-report what the machine did.
    """
    command = {"commandType": "somethingNew", "params": {"detail": 1}}

    rendered = main.describe_command(command, names)

    assert rendered.startswith("somethingNew")
    assert "detail" in rendered


def test_a_command_without_a_resolvable_labware_still_renders(names):
    """A blank name must not become a crash."""
    command = {
        "commandType": "pickUpTip",
        "params": {"labwareId": "unknown-id", "wellName": "A1"},
    }

    assert main.describe_command(command, names) == "pick up tip from "


# ---- Step lines -------------------------------------------------------


def test_step_lines_are_numbered_from_one(names):
    """Operators count from one; the list is zero-based."""
    command = {"commandType": "home", "params": {}, "status": "succeeded"}

    assert main.format_step(0, command, names).split()[0] == "1"


def test_a_failed_step_is_marked_as_failed(names):
    """The one line that must never be missed."""
    command = {"commandType": "home", "params": {}, "status": "failed"}

    assert "FAIL" in main.format_step(3, command, names)


def test_a_planned_step_carries_no_status_mark(names):
    """Analysis commands have not run, so they claim nothing."""
    command = {"commandType": "home", "params": {}}

    line = main.format_step(0, command, names)

    assert "OK" not in line and "FAIL" not in line


# ---- Incremental printing --------------------------------------------


def test_only_unseen_steps_are_printed(names, capsys):
    """The stream prints each command once, as it appears."""
    commands = [
        {"commandType": "home", "params": {}, "status": "succeeded"},
        {"commandType": "dropTipInPlace", "params": {}, "status": "succeeded"},
    ]

    shown = main.print_new_steps(commands, 1, names)
    captured = capsys.readouterr().out

    assert shown == 2
    assert "drop tip" in captured
    assert "home" not in captured


def test_printing_with_nothing_new_prints_nothing(names, capsys):
    """A quiet tick stays quiet."""
    commands = [{"commandType": "home", "params": {}}]

    assert main.print_new_steps(commands, 1, names) == 1
    assert capsys.readouterr().out == ""


# ---- Failure reporting ------------------------------------------------


def test_transport_failure_shows_the_robot_explanation():
    """A 422 without the robot's reason is not worth printing."""
    error = TransportError(
        "POST /protocols returned 422",
        status_code=422,
        body={
            "errors": [
                {
                    "id": "ProtocolFilesInvalid",
                    "detail": "expected ':' (bad_syntax.py, line 16)",
                }
            ]
        },
    )

    lines = main.describe_failure(error)

    assert lines[0] == "POST /protocols returned 422"
    assert "bad_syntax.py, line 16" in lines[1]


def test_analysis_failure_shows_every_error():
    """An analysis can reject a protocol for more than one reason."""
    error = AnalysisError(
        "analysis reported 2 error(s)",
        errors=[
            {"errorType": "ExceptionInProtocolError", "detail": "first"},
            {"errorType": "ExceptionInProtocolError", "detail": "second"},
        ],
    )

    lines = main.describe_failure(error)

    assert len(lines) == 3
    assert "first" in lines[1]
    assert "second" in lines[2]


def test_a_failure_carrying_no_detail_still_reports_its_summary():
    """A connection failure has no body; it still has a message."""
    assert main.describe_failure(TransportError("connection refused")) == [
        "connection refused"
    ]


# ---- Argument handling ------------------------------------------------


def test_defaults_target_the_reference_protocol():
    """Running the console bare should do the documented thing."""
    args = main.build_parser().parse_args([])

    assert args.profile == "dev"
    assert Path(args.protocol).name == "OD_Normalization.py"
    assert Path(args.csv).name == "od_normalization.csv"
    assert args.verify_only is False


def test_the_csv_can_be_switched_off():
    """A protocol without a file parameter needs no CSV."""
    args = main.build_parser().parse_args(["--csv", ""])

    assert args.csv == ""


# ---- Pre-flight, spec section 10 --------------------------------------


class StubController:
    """A controller that answers pre-flight without a network.

    Attributes:
        base_url: Where it claims to be.
        writes: Deck configurations it was asked to store, so a test can
            prove the robot profile wrote none.
    """

    def __init__(self, name="flex-01", instruments=None, modules=None):
        self.base_url = "http://10.0.0.5:31950"
        self.writes: list = []
        self._name = name
        self._instruments = instruments if instruments is not None else []
        self._modules = modules if modules is not None else []

    def health(self):
        """Report the identity pre-flight asks for."""
        return {
            "name": self._name,
            "api_version": "8.2.0",
            "system_version": "8.2.0",
        }

    def get_instruments(self):
        """Report the attached pipettes and gripper."""
        return self._instruments

    def get_modules(self):
        """Report the attached modules."""
        return self._modules

    def get_deck_configuration(self):
        """Report one registered fixture, enough to be counted."""
        return [{"cutoutId": "cutoutA1", "cutoutFixtureId": "singleLeftSlot"}]

    def set_deck_configuration(self, fixtures):
        """Record a write so a test can prove one did not happen.

        Args:
            fixtures: The fixture list the caller asked to store.

        Returns:
            The same list, as the real endpoint does.
        """
        self.writes.append(fixtures)
        return fixtures


class UnreachableController(StubController):
    """A controller whose robot does not answer."""

    def health(self):
        """Fail the way an unreachable robot does.

        Raises:
            TransportError: Always; that is the point of this stub.
        """
        raise TransportError("connection refused")


def read_verdicts(results):
    """Map each checked item to its verdict.

    Args:
        results: Output of ``check_before_running``.

    Returns:
        Item name to verdict.
    """
    return {item: verdict for verdict, item, _ in results}


def test_preflight_stops_when_the_robot_does_not_answer(tmp_path):
    """An unreachable robot is the one fault worth stopping everything for."""
    protocol = tmp_path / "p.py"
    protocol.write_text('requirements = {"apiLevel": "2.20"}', encoding="utf-8")

    results = check_before_running(UnreachableController(), protocol, None)

    assert read_verdicts(results) == {"reachable": "stop"}


def test_preflight_stops_on_the_wrong_robot(tmp_path):
    """Reaching the wrong machine must not become a run on it.

    Spec section 10 item 4 asks the operator to confirm the target. Given
    a name to expect, the console can confirm it for them.
    """
    protocol = tmp_path / "p.py"
    protocol.write_text('requirements = {"apiLevel": "2.20"}', encoding="utf-8")

    results = check_before_running(StubController(), protocol, "flex-99")

    assert read_verdicts(results)["robot name"] == "stop"


def test_preflight_accepts_the_expected_robot(tmp_path):
    """The name matching is the point; it must not stop a correct one."""
    protocol = tmp_path / "p.py"
    protocol.write_text('requirements = {"apiLevel": "2.20"}', encoding="utf-8")

    results = check_before_running(StubController(), protocol, "flex-01")

    assert read_verdicts(results)["robot name"] == "ok"


def test_preflight_only_looks_at_hardware_it_cannot_judge(tmp_path):
    """Attached hardware is reported, never used to block.

    The console cannot know what an arbitrary protocol needs, so deciding
    for the operator would be guessing. The analysis gate does the real
    refusing.
    """
    protocol = tmp_path / "p.py"
    protocol.write_text('requirements = {"apiLevel": "2.20"}', encoding="utf-8")

    results = check_before_running(StubController(), protocol, "flex-01")

    for item in ("pipette", "gripper", "modules", "deck configuration"):
        assert read_verdicts(results)[item] == "look"
    assert not [row for row in results if row[0] == "stop"]


def test_preflight_reports_a_robot_with_nothing_attached(tmp_path):
    """An empty robot is a fact to show, not a crash."""
    protocol = tmp_path / "p.py"
    protocol.write_text('requirements = {"apiLevel": "2.20"}', encoding="utf-8")

    results = check_before_running(StubController(), protocol, "flex-01")

    assert ("look", "pipette", "none attached") in results
    assert ("look", "gripper", "none attached") in results


def test_show_preflight_blocks_only_on_a_stop_row(capsys):
    """The gate reads its own table the way the operator does."""
    assert main.show_preflight([("ok", "reachable", "x")]) is True
    assert main.show_preflight([("look", "pipette", "x")]) is True
    assert main.show_preflight([("stop", "robot name", "x")]) is False
    assert "Blocked" in capsys.readouterr().out


# ---- apiLevel is read, never executed ---------------------------------


def test_api_level_is_read_as_text(tmp_path):
    """A protocol is parsed, not imported.

    Importing it to inspect it would run its module-level code on the
    computer driving the robot.
    """
    protocol = tmp_path / "p.py"
    protocol.write_text(
        'requirements = {"robotType": "Flex", "apiLevel": "2.20"}\n'
        "raise SystemExit('this must never execute')\n",
        encoding="utf-8",
    )

    assert main.read_declared_api_level(protocol) == (2, 20)


def test_a_protocol_without_an_api_level_is_not_an_error(tmp_path):
    """Saying so beats guessing."""
    protocol = tmp_path / "p.py"
    protocol.write_text("# nothing declared\n", encoding="utf-8")

    assert main.read_declared_api_level(protocol) is None


def test_version_parsing_survives_odd_strings():
    """Robot software versions are not always three clean numbers."""
    assert main.parse_version("8.2.0") == (8, 2, 0)
    assert main.parse_version("0.0.0.dev0") == (0, 0, 0)
    assert main.parse_version("unknown") == ()


# ---- The deck default, which is a safety decision ---------------------


def test_deck_is_unset_by_default_so_a_profile_can_decide():
    """`--deck` must not carry a path that would be written to a robot."""
    assert main.build_parser().parse_args([]).deck is None


def test_only_the_dev_profile_writes_a_deck_without_being_asked():
    """Writing a deck asserts which fixtures are physically bolted on.

    On a real robot that assertion may be false, and per
    docs/spec_deviations.md D-1 the analysis will not object -- the run
    fails mid-motion instead. So the reference layout is applied only on
    the profile it describes.
    """
    assert "dev" in main.deck_written_by_default
    assert "robot" not in main.deck_written_by_default

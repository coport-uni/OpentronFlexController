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

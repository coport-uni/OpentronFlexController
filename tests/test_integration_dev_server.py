"""Integration tests against a Flex robot-server development server.

Covers TC-03 through TC-11 of spec section 8, plus the deliberate fault
injections of spec section 7. Every test here talks to a real server on
``localhost``; the whole module is skipped when none is listening, so
the unit suite still runs on a machine without one.

Per spec section 1.2 no real device is involved. Nothing in this file
may be read as evidence about hardware.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flex_controller import (  # noqa: E402
    AnalysisError,
    FlexController,
    TransportError,
)

repository_root = Path(__file__).resolve().parents[1]
protocol_path = repository_root / "protocols" / "OD_Normalization.py"
fault_dir = Path(__file__).parent / "protocols"
deck_path = repository_root / "configs" / "deck_od_normalization.json"
small_csv = repository_root / "data" / "od_normalization.csv"
full_csv = repository_root / "data" / "od_normalization_96.csv"

# Spec section 2.3 fixes these for the whole verification campaign.
# waste_type 1 selects the chute; 2 would put a trash bin in A3 and the
# tiprack switch would then have no staging slot to use.
reference_parameters = {"dry_run": True, "waste_type": 1}

expected_fixture_count = 12
expected_module_count = 3
expected_dev_robot_name = "opentrons-dev"

# The robot reports the 96-channel pipette by its internal name; the
# protocol loads it as "flex_96channel_1000".
expected_pipette_name = "p1000_96"
waste_chute_area = "96ChannelWasteChute"

# The staging column, enabled by the cutoutA3 and cutoutD3 fixtures.
staging_slots = {"A4", "B4", "C4", "D4"}

# The protocol transfers diluent and then DNA, so each CSV row produces
# two aspirates.
aspirates_per_row = 2

# A run is stopped shortly after it starts, before it can finish.
stop_delay_s = 1.0


def read_deck_fixtures() -> list[dict]:
    """Read the deck fixture list of spec section 3.4.

    Returns:
        The twelve fixture entries.
    """
    return json.loads(deck_path.read_text(encoding="utf-8"))


def count_csv_rows(path: Path) -> int:
    """Count the data rows of a CSV, excluding its header.

    Args:
        path: CSV to measure.

    Returns:
        The number of data rows.
    """
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return len(lines) - 1


def unique_copy(source: Path, destination_dir: Path) -> Path:
    """Copy a protocol, giving it content no upload has carried before.

    The robot stores one protocol per distinct file and reuses the
    existing record when the bytes match, which would otherwise let a
    test read an analysis produced under different conditions. A trailing
    comment makes the file new without changing what it does.

    Args:
        source: Protocol to copy.
        destination_dir: Directory to write the copy into.

    Returns:
        Path to the copy.
    """
    marker = destination_dir.name
    destination = destination_dir / source.name
    body = source.read_text(encoding="utf-8")
    destination.write_text(
        f"{body}\n# unique upload marker: {marker}\n", encoding="utf-8"
    )
    return destination


def build_controller(tmp_path: Path) -> FlexController:
    """Build a controller aimed at the development server.

    Args:
        tmp_path: Directory for saved artifacts.

    Returns:
        A controller on the ``dev`` profile.
    """
    return FlexController(
        profile="dev", artifact_dir=tmp_path, allow_mutations=True
    )


def server_is_up() -> bool:
    """Report whether a development server is listening.

    Returns:
        ``True`` when the health endpoint answers.
    """
    probe = FlexController(profile="dev", timeout=2.0, retry_limit=0)
    return probe.is_reachable()


pytestmark = pytest.mark.skipif(
    not server_is_up(),
    reason="no robot-server development server on localhost:31950",
)


@pytest.fixture
def controller(tmp_path) -> FlexController:
    """Provide a controller for one test.

    Args:
        tmp_path: pytest-provided artifact directory.

    Returns:
        A controller on the ``dev`` profile.
    """
    return build_controller(tmp_path)


@pytest.fixture
def deck_ready(controller) -> FlexController:
    """Register the reference deck, and restore it afterwards.

    Tests that deliberately break the deck configuration must not leave
    it broken for whatever runs next.

    Args:
        controller: The controller under test.

    Yields:
        The same controller, with the reference deck applied.
    """
    controller.set_deck_configuration(read_deck_fixtures())
    yield controller
    controller.set_deck_configuration(read_deck_fixtures())


@pytest.fixture(scope="module")
def reference_analysis(tmp_path_factory) -> dict:
    """Analyse the reference protocol once for the whole module.

    The 96-row CSV is used because the tiprack switch -- and with it the
    gripper -- only happens once the first tiprack is exhausted, which
    takes more than 96 pickups.

    Args:
        tmp_path_factory: pytest-provided directory factory.

    Returns:
        The completed analysis document.
    """
    workspace = tmp_path_factory.mktemp("reference")
    controller = build_controller(workspace)
    controller.set_deck_configuration(read_deck_fixtures())
    controller.upload_data_file(full_csv, variable_name="csv_data")
    controller.upload_protocol(
        protocol_path, parameter_values=reference_parameters
    )
    return controller.wait_for_analysis()


# ---- TC-03: health ----------------------------------------------------


def test_tc03_health_identifies_the_development_server(controller):
    """TC-03: health returns the name ``opentrons-dev``."""
    identity = controller.health()

    assert identity["name"] == expected_dev_robot_name
    assert identity["api_version"]
    assert controller.is_reachable() is True


# ---- TC-04: deck configuration ---------------------------------------


def test_tc04_deck_configuration_reads_back(controller):
    """TC-04: the twelve fixtures of spec 3.4 survive a round trip."""
    requested = read_deck_fixtures()

    controller.set_deck_configuration(requested)
    stored = controller.get_deck_configuration()

    assert len(stored) == expected_fixture_count
    stored_by_cutout = {
        entry["cutoutId"]: entry["cutoutFixtureId"] for entry in stored
    }
    for entry in requested:
        assert stored_by_cutout[entry["cutoutId"]] == entry["cutoutFixtureId"]

    assert stored_by_cutout["cutoutA3"] == "stagingAreaRightSlot"
    assert (
        stored_by_cutout["cutoutD3"]
        == "stagingAreaSlotWithWasteChuteRightAdapterNoCover"
    )


# ---- TC-05: data files -----------------------------------------------


def test_tc05_csv_upload_is_listed_by_the_robot(controller):
    """TC-05: an uploaded CSV gets an identifier the robot knows."""
    file_id = controller.upload_data_file(small_csv, variable_name="csv_data")

    assert file_id
    assert controller._data_file_ids["csv_data"] == file_id
    assert file_id in {entry["id"] for entry in controller.list_data_files()}


# ---- TC-06: protocol upload ------------------------------------------


def test_tc06_protocol_upload_returns_both_identifiers(deck_ready):
    """TC-06: an upload yields a protocol and an analysis to wait on."""
    controller = deck_ready
    controller.upload_data_file(small_csv, variable_name="csv_data")

    protocol_id, analysis_id = controller.upload_protocol(
        protocol_path, parameter_values=reference_parameters
    )

    assert protocol_id and analysis_id
    assert protocol_id in {entry["id"] for entry in controller.list_protocols()}


# ---- TC-07: clean analysis -------------------------------------------


def test_tc07_analysis_reports_no_errors(reference_analysis):
    """TC-07: the reference protocol analyses cleanly."""
    assert reference_analysis["status"] == "completed"
    assert reference_analysis["result"] == "ok"
    assert reference_analysis["errors"] == []


def test_tc07_ninety_six_channel_pipette_is_recognised(reference_analysis):
    """TC-07: the analysis loads the 96-channel pipette."""
    pipettes = reference_analysis["pipettes"]

    assert [item["pipetteName"] for item in pipettes] == [expected_pipette_name]
    assert pipettes[0]["mount"] == "left"


def test_tc07_nozzle_layout_is_reconfigured(reference_analysis):
    """TC-07: the protocol switches the pipette to single-nozzle mode."""
    configures = [
        command
        for command in reference_analysis["commands"]
        if command["commandType"] == "configureNozzleLayout"
    ]

    assert len(configures) == 1
    params = configures[0]["params"]["configurationParams"]
    assert params["style"] == "SINGLE"
    assert params["primaryNozzle"] == "A1"


def test_tc07_gripper_moves_the_tipracks(reference_analysis):
    """TC-07: the tiprack switch is carried out by the gripper."""
    moves = [
        command
        for command in reference_analysis["commands"]
        if command["commandType"] == "moveLabware"
    ]

    assert moves, "no labware was moved; the tiprack was never exhausted"
    assert all(
        command["params"]["strategy"] == "usingGripper" for command in moves
    )
    destinations = {
        json.dumps(command["params"]["newLocation"], sort_keys=True)
        for command in moves
    }
    assert any("D4" in item for item in destinations)


def test_tc07_three_modules_are_loaded(reference_analysis):
    """TC-07: the thermocycler, temperature module, and shaker load."""
    loads = [
        command
        for command in reference_analysis["commands"]
        if command["commandType"] == "loadModule"
    ]

    assert len(loads) == expected_module_count
    assert {command["params"]["model"] for command in loads} == {
        "thermocyclerModuleV2",
        "temperatureModuleV2",
        "heaterShakerModuleV1",
    }


def test_tc07_tips_are_discarded_into_the_waste_chute(reference_analysis):
    """TC-07: tip disposal targets the chute, not a trash bin."""
    areas = {
        command["params"].get("addressableAreaName")
        for command in reference_analysis["commands"]
        if command["commandType"] == "moveToAddressableArea"
    }

    assert areas == {waste_chute_area}


def test_tc07_transfer_count_follows_the_csv(reference_analysis):
    """TC-07: the robot plans one pair of transfers per CSV row."""
    aspirates = [
        command
        for command in reference_analysis["commands"]
        if command["commandType"] == "aspirate"
    ]

    assert len(aspirates) == count_csv_rows(full_csv) * aspirates_per_row


def test_tc07_staging_slots_are_used(reference_analysis):
    """TC-07: a tiprack occupies a staging slot.

    The analysis reports where each labware ends up, not where it began,
    so after the gripper swap the tiprack that started on A4 is on A2
    and the one that started on A2 is on staging slot D4. Either way a
    staging slot is in use, which is what the deck fixture of cutoutA3
    and cutoutD3 exists to provide.
    """
    locations = [item["location"] for item in reference_analysis["labware"]]
    staging = {
        location.get("addressableAreaName")
        for location in locations
        if location.get("addressableAreaName") in staging_slots
    }

    assert staging, f"no staging slot in use; locations were {locations}"


# ---- TC-08: the analysis gate rejects a bad protocol -----------------


def test_tc08_undefined_labware_blocks_the_run(deck_ready):
    """TC-08: an undefined labware is caught and no run is created."""
    controller = deck_ready
    runs_before = len(controller.list_runs())

    verdict = controller.verify_only(fault_dir / "bad_labware.py")

    assert verdict["passed"] is False
    assert len(verdict["errors"]) >= 1
    assert "corning_96_wellplate_9999ul_flat" in json.dumps(verdict["errors"])

    with pytest.raises(AnalysisError):
        controller.assert_analysis_clean({"errors": verdict["errors"]})
    assert len(controller.list_runs()) == runs_before


def test_tc08_execute_refuses_a_rejected_protocol(deck_ready):
    """TC-08: the gate stops ``execute`` before it creates a run."""
    controller = deck_ready
    runs_before = len(controller.list_runs())

    with pytest.raises(AnalysisError) as caught:
        controller.execute(fault_dir / "bad_labware.py")

    assert caught.value.errors
    assert controller._run_id is None
    assert len(controller.list_runs()) == runs_before


# ---- TC-09: a deck configuration that cannot serve the protocol ------


def test_tc09_missing_waste_chute_fails_the_run(deck_ready, tmp_path):
    """TC-09: without the chute fixture the run fails, naming the gap.

    Spec section 8 expects the analysis to catch this. It does not:
    robot-server analyses a protocol without reference to the deck
    configuration, so the analysis is clean and the run is created.
    The gap surfaces when the robot reaches the missing area, as an
    ``AreaNotInDeckConfigurationError`` that names it. The tool still
    reports the fault, one stage later than the spec predicted.
    """
    controller = deck_ready
    broken = [
        entry
        for entry in read_deck_fixtures()
        if entry["cutoutId"] != "cutoutD3"
    ]
    broken.append(
        {"cutoutId": "cutoutD3", "cutoutFixtureId": "singleRightSlot"}
    )
    controller.set_deck_configuration(broken)

    controller.upload_data_file(small_csv, variable_name="csv_data")
    controller.upload_protocol(
        unique_copy(protocol_path, tmp_path),
        parameter_values=reference_parameters,
    )
    analysis = controller.wait_for_analysis()

    # Recorded, not endorsed: this is the spec deviation described above.
    assert analysis["errors"] == []

    controller.create_run(parameter_values=reference_parameters)
    controller.play()
    final = controller.monitor()

    assert final["status"] == "failed"
    detail = json.dumps(controller.get_errors())
    assert "AreaNotInDeckConfigurationError" in detail
    assert "WasteChute" in detail


# ---- TC-10: a complete run -------------------------------------------


def test_tc10_full_run_succeeds(deck_ready):
    """TC-10: the reference protocol runs through to ``succeeded``."""
    controller = deck_ready

    final = controller.execute(
        protocol_path,
        csv_path=small_csv,
        parameter_values=reference_parameters,
    )

    assert final["status"] == "succeeded"
    assert controller.get_errors() == []
    assert controller.get_commands()


# ---- TC-11: stopping a run -------------------------------------------


def test_tc11_stop_reaches_the_stopped_state(deck_ready):
    """TC-11: a run stopped after ``play`` ends in ``stopped``.

    The long CSV is used so the run is still going when the stop
    arrives; against the short one the race is not worth running.
    """
    controller = deck_ready
    controller.upload_data_file(full_csv, variable_name="csv_data")
    controller.upload_protocol(
        protocol_path, parameter_values=reference_parameters
    )
    controller.assert_analysis_clean(controller.wait_for_analysis())

    controller.create_run(parameter_values=reference_parameters)
    controller.play()
    time.sleep(stop_delay_s)
    controller.stop()

    final = controller.monitor()

    assert final["status"] == "stopped"


# ---- Fault injection, spec section 7 ---------------------------------


def test_syntax_error_is_reported_and_blocks_the_run(deck_ready):
    """A file that will not compile is refused at upload.

    Spec section 7 files a syntax error under "analysis error". The
    robot is stricter than that: it compiles the file during the upload
    request and answers 422 ``ProtocolFilesInvalid``, so no protocol,
    no analysis, and no run are ever created. The report still names the
    file and the offending line.
    """
    controller = deck_ready
    runs_before = len(controller.list_runs())

    with pytest.raises(TransportError) as caught:
        controller.verify_only(fault_dir / "bad_syntax.py")

    assert caught.value.status_code == 422
    detail = json.dumps(caught.value.body)
    assert "ProtocolFilesInvalid" in detail
    assert "bad_syntax.py" in detail
    assert controller._protocol_id is None
    assert len(controller.list_runs()) == runs_before


def test_layout_collision_is_reported(deck_ready):
    """Two labware in one slot are rejected by the analysis."""
    controller = deck_ready

    verdict = controller.verify_only(fault_dir / "bad_layout.py")

    assert verdict["passed"] is False
    assert len(verdict["errors"]) >= 1


def test_missing_runtime_parameter_file_is_reported(deck_ready):
    """Omitting the CSV leaves a required parameter unsatisfied."""
    controller = deck_ready

    controller.upload_protocol(
        protocol_path,
        parameter_values=reference_parameters,
        parameter_files={},
    )
    analysis = controller.wait_for_analysis()

    assert analysis["errors"], "a missing CSV parameter went unnoticed"


def test_unknown_run_id_fails_without_retrying(controller):
    """A 4xx names a mistake in the request, so it is not repeated."""
    with pytest.raises(TransportError) as caught:
        controller.get_run("00000000-0000-0000-0000-000000000000")

    assert caught.value.status_code == 404

"""Unit tests for FlexController, covering TC-01 and TC-02.

Every test substitutes ``_request`` rather than starting a server, per
spec section 4.3 rule 4, so the suite runs without a robot or a
development server present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import flex_controller  # noqa: E402
from flex_controller import (  # noqa: E402
    AnalysisError,
    FlexController,
    RunError,
    TransportError,
    terminal_run_states,
)

fixture_dir = Path(__file__).parent / "fixtures"

# A 5xx is transient and earns the full retry budget; a 4xx describes
# the request itself and must be surrendered on the first attempt.
server_error_status = 503
client_error_status = 422

# One first attempt plus the three retries of spec section 6.
expected_attempts_on_server_error = 4
expected_attempts_on_client_error = 1

# Spec section 4.3 rule 5. Thirty is where the rule asks us to
# reconsider splitting out the transport layer; the class stands above
# it since get_instruments and get_modules were added for the operator
# console. The reconsideration is docs/transport_layer_review.md.
review_threshold = 30
documented_method_count = 32


def load_fixture(name: str) -> dict:
    """Read one stored robot response.

    Args:
        name: File name below ``tests/fixtures``.

    Returns:
        The decoded document.
    """
    return json.loads((fixture_dir / name).read_text(encoding="utf-8"))


class RecordingTransport:
    """A stand-in for ``_request`` that logs calls and replays answers.

    Attributes:
        calls: One entry per call, holding the method and path.
        responses: Queued bodies or exceptions, consumed in order. The
            last entry repeats once the queue is down to it, so a retry
            test can declare a single persistent fault.
    """

    def __init__(self, responses: list) -> None:
        self.calls: list[tuple[str, str]] = []
        self.responses = list(responses)

    def __call__(self, method: str, path: str, **kwargs) -> dict:
        """Record one call and return or raise the queued answer.

        Args:
            method: HTTP verb the controller asked for.
            path: Path the controller asked for.
            **kwargs: Ignored; accepted so the signature matches.

        Returns:
            The queued response body.

        Raises:
            BaseException: If the queued entry is an exception.
        """
        self.calls.append((method, path))
        answer = (
            self.responses.pop(0)
            if len(self.responses) > 1
            else self.responses[0]
        )
        if isinstance(answer, BaseException):
            raise answer
        return answer


@pytest.fixture
def controller(tmp_path) -> FlexController:
    """Build a controller that never sleeps between retries.

    Args:
        tmp_path: pytest-provided directory for saved artifacts.

    Returns:
        A controller configured for fast, offline tests.
    """
    return FlexController(
        profile="dev",
        backoff_base=0.0,
        analysis_period=0.0,
        run_period=0.0,
        artifact_dir=tmp_path,
    )


# ---- TC-01: response parsing ------------------------------------------


def test_health_parses_identity(controller):
    """TC-01: health reports the robot's name and versions."""
    controller._request = RecordingTransport([load_fixture("health.json")])

    identity = controller.health()

    assert identity["name"] == "opentrons-dev"
    assert identity["api_version"] == "0.0.0.dev0"
    assert identity["system_version"] == "0.0.0"


def test_deck_configuration_parses_fixtures(controller):
    """TC-01: the deck reader returns the stored fixture list."""
    controller._request = RecordingTransport(
        [load_fixture("deck_configuration.json")]
    )

    fixtures = controller.get_deck_configuration()

    assert len(fixtures) == 12
    assert {"cutoutId": "cutoutD3"}.items() <= fixtures[-1].items()


def test_analysis_clean_fixture_parses(controller):
    """TC-01: a completed analysis yields its commands and no errors."""
    controller._request = RecordingTransport(
        [load_fixture("analysis_clean.json")]
    )
    controller._protocol_id = "protocol-1"
    controller._analysis_id = "analysis-1"

    analysis = controller.get_analysis()

    assert analysis["status"] == "completed"
    assert analysis["errors"] == []
    assert len(analysis["commands"]) == 2


def test_analysis_error_fixture_parses(controller):
    """TC-01: a rejected analysis yields the robot's error entries."""
    controller._request = RecordingTransport(
        [load_fixture("analysis_error.json")]
    )
    controller._protocol_id = "protocol-1"
    controller._analysis_id = "analysis-1"

    analysis = controller.get_analysis()

    assert analysis["result"] == "not-ok"
    assert len(analysis["errors"]) == 1
    assert analysis["errors"][0]["errorType"] == "ExceptionInProtocolError"


def test_upload_protocol_parses_ids(controller, tmp_path):
    """TC-01: an upload yields the protocol and analysis identifiers."""
    protocol = tmp_path / "protocol.py"
    protocol.write_text("# empty", encoding="utf-8")
    controller._request = RecordingTransport(
        [load_fixture("protocol_upload.json")]
    )

    protocol_id, analysis_id = controller.upload_protocol(protocol)

    assert protocol_id == "protocol-1"
    assert analysis_id == "analysis-1"


def test_get_commands_follows_pagination(controller):
    """TC-01: the command reader concatenates every page."""
    controller._run_id = "run-1"
    controller._request = RecordingTransport(
        [
            {
                "data": [{"id": "c1"}, {"id": "c2"}],
                "meta": {"totalLength": 3},
            },
            {"data": [{"id": "c3"}], "meta": {"totalLength": 3}},
        ]
    )

    commands = controller.get_commands(page_length=2)

    assert [item["id"] for item in commands] == ["c1", "c2", "c3"]


# ---- TC-02: retry policy ----------------------------------------------


def test_retries_three_times_on_server_error(controller):
    """TC-02: a 5xx is attempted once and retried three times."""
    transport = RecordingTransport(
        [TransportError("boom", status_code=server_error_status)]
    )
    controller._request = transport

    with pytest.raises(TransportError):
        controller.health()

    assert len(transport.calls) == expected_attempts_on_server_error


def test_does_not_retry_on_client_error(controller):
    """TC-02: a 4xx is surrendered without a retry."""
    transport = RecordingTransport(
        [TransportError("bad id", status_code=client_error_status)]
    )
    controller._request = transport

    with pytest.raises(TransportError):
        controller.get_run("missing-run")

    assert len(transport.calls) == expected_attempts_on_client_error


def test_retries_on_connection_failure(controller):
    """TC-02: a request that never arrived is retried."""
    transport = RecordingTransport([TransportError("connection refused")])
    controller._request = transport

    with pytest.raises(TransportError):
        controller.health()

    assert len(transport.calls) == expected_attempts_on_server_error


def test_recovers_when_a_retry_succeeds(controller):
    """TC-02: a transient fault does not fail the call."""
    transport = RecordingTransport(
        [
            TransportError("boom", status_code=server_error_status),
            load_fixture("health.json"),
        ]
    )
    controller._request = transport

    identity = controller.health()

    assert identity["name"] == "opentrons-dev"
    assert len(transport.calls) == 2


def test_run_actions_are_never_retried(controller):
    """TC-02: a run action is not repeated, even on a 5xx.

    A duplicate play or stop is a second instruction to the machine
    rather than a second attempt at the first, so spec section 6 keeps
    actions out of the retry policy.
    """
    transport = RecordingTransport(
        [TransportError("boom", status_code=server_error_status)]
    )
    controller._request = transport
    controller._run_id = "run-1"

    with pytest.raises(TransportError):
        controller.play()

    assert len(transport.calls) == expected_attempts_on_client_error


def test_is_reachable_reports_false_without_raising(controller):
    """TC-02: reachability is a question, not an error."""
    controller._request = RecordingTransport(
        [TransportError("connection refused")]
    )

    assert controller.is_reachable() is False


# ---- Analysis gate, spec section 5.2 ----------------------------------


def test_gate_raises_when_analysis_has_errors(controller):
    """The gate rejects an analysis that reported errors."""
    analysis = load_fixture("analysis_error.json")["data"]

    with pytest.raises(AnalysisError) as caught:
        controller.assert_analysis_clean(analysis)

    assert len(caught.value.errors) == 1


def test_gate_passes_a_clean_analysis(controller):
    """The gate lets a clean analysis through."""
    analysis = load_fixture("analysis_clean.json")["data"]

    assert controller.assert_analysis_clean(analysis) is None


def test_gate_blocks_run_creation(controller, tmp_path):
    """A rejected analysis stops the workflow before any run exists.

    This is the property that matters in spec section 5.2: not that an
    exception is raised, but that the robot is never asked to run.
    """
    protocol = tmp_path / "protocol.py"
    protocol.write_text("# empty", encoding="utf-8")
    transport = RecordingTransport(
        [
            load_fixture("health.json"),
            load_fixture("protocol_upload.json"),
            load_fixture("analysis_error.json"),
        ]
    )
    controller._request = transport

    with pytest.raises(AnalysisError):
        controller.execute(protocol)

    assert not any(path == "/runs" for _, path in transport.calls)


# ---- Run states, spec section 5.3 -------------------------------------


def test_terminal_states_match_the_specification():
    """The terminal set is exactly the three states of spec 5.3."""
    assert set(terminal_run_states) == {"succeeded", "stopped", "failed"}


def test_monitor_stops_at_a_terminal_state(controller):
    """Polling ends once the run can no longer change."""
    controller._run_id = "run-1"
    controller._request = RecordingTransport(
        [
            {"data": {"status": "idle"}},
            {"data": {"status": "running"}},
            {"data": {"status": "succeeded"}},
        ]
    )

    final = controller.monitor()

    assert final["status"] == "succeeded"


def test_monitor_warns_but_continues_on_an_unknown_state(controller, caplog):
    """An unrecognised state is logged, never raised.

    The robot's vocabulary may grow; a state this tool has not heard of
    is not by itself a failure (spec section 5.3).
    """
    controller._run_id = "run-1"
    controller._request = RecordingTransport(
        [
            {"data": {"status": "recalibrating-gantry"}},
            {"data": {"status": "succeeded"}},
        ]
    )

    with caplog.at_level("WARNING", logger="flex_controller"):
        final = controller.monitor()

    assert final["status"] == "succeeded"
    assert "unknown run state" in caplog.text


# ---- Profiles, spec section 4.4 ---------------------------------------


def test_dev_profile_needs_no_confirmation():
    """The dev profile targets localhost and does not prompt."""
    controller = FlexController(profile="dev")

    assert controller.host == "localhost"
    assert controller.requires_confirmation is False


def test_robot_profile_requires_a_host_and_confirmation():
    """The robot profile has no default host and always prompts."""
    controller = FlexController(profile="robot", host="10.0.0.5")

    assert controller.host == "10.0.0.5"
    assert controller.requires_confirmation is True

    with pytest.raises(ValueError):
        FlexController(profile="robot")


def test_unknown_profile_is_rejected():
    """An unknown profile fails at construction, not mid-run."""
    with pytest.raises(ValueError):
        FlexController(profile="staging")


def test_profiles_differ_only_in_host_and_confirmation():
    """No behaviour keys off "is this the development server".

    Spec section 4.4 forbids a development-server branch, so the two
    profiles must agree on every setting except these two.
    """
    dev = FlexController(profile="dev")
    robot = FlexController(profile="robot", host="10.0.0.5")

    ignored = {"host", "profile", "requires_confirmation", "base_url"}
    for name, value in vars(dev).items():
        if name.startswith("_") or name in ignored:
            continue
        assert vars(robot)[name] == value, name


# ---- Constructor arguments, spec section 4.3 rule 3 -------------------


def test_timing_values_come_from_the_constructor():
    """Timing is configuration, so a caller can retune it."""
    controller = FlexController(
        profile="dev",
        timeout=1.5,
        upload_timeout=15.0,
        analysis_period=0.25,
        analysis_limit=30.0,
        run_period=0.5,
    )

    assert controller.timeout == 1.5
    assert controller.upload_timeout == 15.0
    assert controller.analysis_period == 0.25
    assert controller.analysis_limit == 30.0
    assert controller.run_period == 0.5


def test_instance_state_matches_the_specification():
    """Only the five attributes of spec section 4.1 are mutable state."""
    controller = FlexController(profile="dev")

    private = {name for name in vars(controller) if name.startswith("_")}

    assert private == {
        "_session",
        "_protocol_id",
        "_analysis_id",
        "_run_id",
        "_data_file_ids",
    }


def count_methods() -> int:
    """Count the methods defined on the controller.

    Returns:
        The number of callables on the class.
    """
    return len(
        [
            name
            for name in vars(FlexController)
            if callable(vars(FlexController)[name])
            and not name.startswith("__init_subclass__")
        ]
    )


def test_method_count_is_the_documented_one():
    """The class holds exactly the methods that have been reviewed.

    Spec section 4.3 rule 5 makes thirty a review trigger, not a cap.
    Asserting equality rather than a bound means the next method added
    fails here and has to be argued for, which is what the rule is
    asking of us.
    """
    assert count_methods() == documented_method_count


def test_crossing_the_threshold_is_reconsidered_in_writing():
    """Rule 5 asks for a reconsideration; this checks one exists.

    The rule's obligation is to think again about splitting out the
    transport layer, not merely to notice the count. A recorded decision
    is the only evidence that happened.
    """
    if documented_method_count <= review_threshold:
        pytest.skip("below the threshold; no reconsideration is owed")

    review = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "transport_layer_review.md"
    )
    assert review.is_file(), (
        f"{count_methods()} methods exceeds {review_threshold}; "
        "spec 4.3 rule 5 requires a recorded transport-layer review"
    )
    assert "transport" in review.read_text(encoding="utf-8").lower()


# ---- Guards -----------------------------------------------------------


def test_deletion_requires_allow_mutations():
    """Destructive endpoints stay shut unless deliberately opened."""
    controller = FlexController(profile="dev")

    with pytest.raises(RunError):
        controller.delete_run("run-1")
    with pytest.raises(RunError):
        controller.delete_protocol("protocol-1")


def test_missing_files_are_reported_before_any_request(controller, tmp_path):
    """A missing local file fails without troubling the robot."""
    transport = RecordingTransport([{}])
    controller._request = transport

    with pytest.raises(FileNotFoundError):
        controller.upload_protocol(tmp_path / "absent.py")
    with pytest.raises(FileNotFoundError):
        controller.upload_data_file(tmp_path / "absent.csv")

    assert transport.calls == []


def test_wait_for_analysis_gives_up_at_the_limit(controller):
    """An analysis that never completes fails rather than hanging."""
    controller._protocol_id = "protocol-1"
    controller._analysis_id = "analysis-1"
    controller.analysis_limit = 0.0
    controller._request = RecordingTransport([{"data": {"status": "pending"}}])

    with pytest.raises(RunError):
        controller.wait_for_analysis()


def test_data_file_ids_feed_the_upload_form(controller, tmp_path):
    """An uploaded CSV is offered to the protocol by identifier."""
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("source,destination\nA1,A1\n", encoding="utf-8")
    controller._request = RecordingTransport(
        [
            {"data": {"id": "file-1"}},
            load_fixture("protocol_upload.json"),
        ]
    )

    controller.upload_data_file(csv_path, variable_name="csv_data")

    assert controller._data_file_ids == {"csv_data": "file-1"}


def test_artifacts_are_written_as_json(controller):
    """Saved records are readable JSON on disk."""
    written = controller.save_artifact("run.json", {"status": "succeeded"})

    assert json.loads(written.read_text(encoding="utf-8")) == {
        "status": "succeeded"
    }


def test_module_exposes_one_command_line_entry_point():
    """Spec section 4.1 allows the class and a single CLI function."""
    public = [
        name
        for name, value in vars(flex_controller).items()
        if callable(value)
        and not name.startswith("_")
        and getattr(value, "__module__", "") == "flex_controller"
    ]

    assert public == [
        "FlexError",
        "TransportError",
        "AnalysisError",
        "RunError",
        "FlexController",
        "main",
    ]


def test_transport_failure_detail_reaches_the_operator():
    """A rejected upload is explained, not just counted.

    The exception message names the request; the robot's reason -- the
    file and line of a syntax error -- travels on the body, so the CLI
    has to unpack it or the operator learns only that a 422 happened.
    """
    error = flex_controller.TransportError(
        "POST /protocols returned 422",
        status_code=422,
        body={
            "errors": [
                {
                    "id": "ProtocolFilesInvalid",
                    "title": "Protocol File(s) Invalid",
                    "detail": "expected ':' (bad_syntax.py, line 16)",
                }
            ]
        },
    )

    assert flex_controller._describe_failure(error) == [
        "Protocol File(s) Invalid: expected ':' (bad_syntax.py, line 16)"
    ]


def test_analysis_failure_detail_reaches_the_operator():
    """Every analysis error is listed, not only the first."""
    error = flex_controller.AnalysisError(
        "analysis reported 2 error(s)",
        errors=[
            {"errorType": "ExceptionInProtocolError", "detail": "no labware"},
            {"errorType": "LocationIsOccupiedError", "detail": "B2 taken"},
        ],
    )

    assert flex_controller._describe_failure(error) == [
        "ExceptionInProtocolError: no labware",
        "LocationIsOccupiedError: B2 taken",
    ]


def test_get_instruments_parses_attached_hardware(controller):
    """Attached pipettes and gripper are read from their endpoint."""
    controller._request = RecordingTransport(
        [
            {
                "data": [
                    {
                        "instrumentType": "pipette",
                        "instrumentModel": "p1000_96_v3.7",
                        "mount": "left",
                        "serialNumber": "96ch_sim_001",
                    },
                    {
                        "instrumentType": "gripper",
                        "instrumentModel": "gripperV1",
                        "mount": "extension",
                        "serialNumber": "gripper_sim_001",
                    },
                ]
            }
        ]
    )

    instruments = controller.get_instruments()

    assert [item["mount"] for item in instruments] == ["left", "extension"]


def test_get_modules_parses_attached_modules(controller):
    """Attached modules are read from their endpoint."""
    controller._request = RecordingTransport(
        [
            {
                "data": [
                    {
                        "moduleModel": "thermocyclerModuleV2",
                        "serialNumber": "therm-sim-001",
                    }
                ]
            }
        ]
    )

    modules = controller.get_modules()

    assert modules[0]["moduleModel"] == "thermocyclerModuleV2"


def test_hardware_readers_return_empty_lists_when_nothing_is_attached(
    controller,
):
    """An empty robot is a fact to report, not an error to raise."""
    controller._request = RecordingTransport([{"data": []}])

    assert controller.get_instruments() == []
    assert controller.get_modules() == []

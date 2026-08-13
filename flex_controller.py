"""Control an Opentrons Flex through the robot-server HTTP API.

The tool uploads a protocol, gates on the pre-run analysis, drives the
run, and collects robot state and errors. It speaks to robot-server
directly; there is no MCP layer. See ``docs/flex_controller_spec_v0.3.md``
for the specification this module implements.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

# The robot rejects requests that do not declare the API version it
# serves, so every call carries this header.
api_version_header = "3"

default_port = 31950
default_request_timeout = 10.0
default_upload_timeout = 120.0
default_analysis_period = 2.0
default_analysis_limit = 600.0
default_run_period = 3.0
default_retry_limit = 3
default_backoff_base = 1.0

# Spec section 5.3. A run that reaches one of these states will not
# leave it, so polling stops here.
terminal_run_states = ("succeeded", "stopped", "failed")

# Spec section 6. Only connection failures and server-side faults are
# worth repeating; a 4xx will fail identically however often it is sent.
server_error_floor = 500

# Spec section 4.4. A profile fixes the host and says whether the
# operator must confirm before the robot is allowed to move.
profile_hosts = {"dev": "localhost", "robot": None}
confirming_profiles = ("robot",)

logger = logging.getLogger("flex_controller")


class FlexError(Exception):
    """Base class for every failure this tool reports."""


class TransportError(FlexError):
    """A request did not produce a usable response.

    Attributes:
        status_code: HTTP status returned by the robot, or ``None`` when
            the request never reached it.
        body: Decoded response body, kept so the caller can print the
            robot's own explanation rather than a generic message.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class AnalysisError(FlexError):
    """The pre-run analysis reported at least one error.

    Raised by the gate of spec section 5.2, which blocks run creation.

    Attributes:
        errors: The ``errors`` array of the analysis document.
    """

    def __init__(self, message: str, errors: list[dict]) -> None:
        super().__init__(message)
        self.errors = errors


class RunError(FlexError):
    """A run could not be started, or ended in a non-success state."""


class FlexController:
    """A single connection to one Opentrons Flex.

    The class owns configuration, HTTP transport, endpoint calls,
    workflow assembly, and status monitoring, per spec section 4.1.
    Methods whose name begins with an underscore are internal and must
    not be called from outside the class.

    Instance state is limited to the five attributes named in spec
    section 4.1 -- ``_session``, ``_protocol_id``, ``_analysis_id``,
    ``_run_id``, and ``_data_file_ids``. Everything else is immutable
    configuration supplied to the constructor.
    """

    def __init__(
        self,
        host: str | None = None,
        profile: str = "dev",
        port: int = default_port,
        timeout: float = default_request_timeout,
        upload_timeout: float = default_upload_timeout,
        analysis_period: float = default_analysis_period,
        analysis_limit: float = default_analysis_limit,
        run_period: float = default_run_period,
        retry_limit: int = default_retry_limit,
        backoff_base: float = default_backoff_base,
        allow_mutations: bool = False,
        artifact_dir: str | Path | None = None,
    ) -> None:
        """Configure a controller without contacting the robot.

        Nothing is sent here, so constructing a controller against an
        unreachable host is safe; ``is_reachable`` is the cheapest way
        to find out whether the robot answers.

        Args:
            host: Robot hostname or IP. Defaults to the profile's host,
                which exists only for ``dev``; the ``robot`` profile has
                no default because the device address is site-specific.
            profile: ``dev`` or ``robot``. Per spec section 4.4 the two
                differ only in host and whether execution must be
                confirmed by the operator.
            port: robot-server port.
            timeout: Seconds allowed for one ordinary request.
            upload_timeout: Seconds allowed for a file upload, which
                takes far longer than a status call.
            analysis_period: Seconds between analysis polls.
            analysis_limit: Seconds to wait for an analysis in total.
            run_period: Seconds between run-status polls.
            retry_limit: Retries after the first attempt, for connection
                failures and 5xx responses only.
            backoff_base: Seconds before the first retry; each further
                retry doubles the wait.
            allow_mutations: Whether destructive endpoints -- protocol
                and run deletion -- may be called. Off by default so a
                mistyped identifier cannot erase robot history.
            artifact_dir: Directory for saved run records. Defaults to
                ``artifacts`` beside this module.

        Raises:
            ValueError: If the profile is unknown, or if it has no
                default host and none was supplied.
        """
        if profile not in profile_hosts:
            known = ", ".join(sorted(profile_hosts))
            raise ValueError(
                f"unknown profile {profile!r}; expected one of {known}"
            )

        resolved_host = host if host is not None else profile_hosts[profile]
        if not resolved_host:
            raise ValueError(
                f"profile {profile!r} has no default host; pass host="
            )

        self.profile = profile
        self.host = resolved_host
        self.port = port
        self.timeout = timeout
        self.upload_timeout = upload_timeout
        self.analysis_period = analysis_period
        self.analysis_limit = analysis_limit
        self.run_period = run_period
        self.retry_limit = retry_limit
        self.backoff_base = backoff_base
        self.allow_mutations = allow_mutations
        self.requires_confirmation = profile in confirming_profiles
        self.base_url = f"http://{resolved_host}:{port}"
        self.artifact_dir = Path(
            artifact_dir
            if artifact_dir is not None
            else Path(__file__).parent / "artifacts"
        )

        self._session = requests.Session()
        self._session.headers.update({"Opentrons-Version": api_version_header})
        self._protocol_id: str | None = None
        self._analysis_id: str | None = None
        self._run_id: str | None = None
        self._data_file_ids: dict[str, str] = {}

    # ---- Transport ----------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> dict:
        """Send one request and decode its body.

        This is the single seam through which the class reaches the
        network. Unit tests replace it, per spec section 4.3 rule 4, so
        it must contain no retry or workflow logic.

        Args:
            method: HTTP verb.
            path: Path below the base URL, beginning with a slash.
            timeout: Seconds for this call; the configured request
                timeout is used when omitted.
            **kwargs: Passed through to ``requests``.

        Returns:
            The decoded JSON body, or an empty dict for a response that
            carries none, such as a ``DELETE``.

        Raises:
            TransportError: On a connection failure, a timeout, an
                undecodable body, or any 4xx or 5xx status.
        """
        url = f"{self.base_url}{path}"
        call_timeout = self.timeout if timeout is None else timeout

        try:
            response = self._session.request(
                method, url, timeout=call_timeout, **kwargs
            )
        except requests.RequestException as error:
            raise TransportError(f"{method} {path} failed: {error}") from error

        if response.content:
            try:
                body = response.json()
            except ValueError:
                body = response.text
        else:
            body = {}

        if response.status_code >= 400:
            raise TransportError(
                f"{method} {path} returned {response.status_code}",
                status_code=response.status_code,
                body=body,
            )

        return body if isinstance(body, dict) else {"data": body}

    def _retry(
        self,
        method: str,
        path: str,
        retryable: bool = True,
        **kwargs: Any,
    ) -> dict:
        """Send a request, repeating it when the fault is transient.

        Connection failures and 5xx responses are retried because they
        describe the moment rather than the request. A 4xx is returned
        to the caller immediately, since resending an invalid request
        cannot make it valid.

        Args:
            method: HTTP verb.
            path: Path below the base URL.
            retryable: Set ``False`` for calls that must not be repeated
                even on a transient fault -- run actions, per spec
                section 6, because a duplicate play or stop is itself a
                hazard.
            **kwargs: Passed through to ``_request``.

        Returns:
            The decoded JSON body of the first successful attempt.

        Raises:
            TransportError: If every permitted attempt failed.
        """
        attempt = 0
        while True:
            try:
                return self._request(method, path, **kwargs)
            except TransportError as error:
                transient = (
                    error.status_code is None
                    or error.status_code >= server_error_floor
                )
                exhausted = attempt >= self.retry_limit
                if not retryable or not transient or exhausted:
                    raise
                delay = self.backoff_base * (2**attempt)
                attempt += 1
                self.log_event(
                    "retry",
                    method=method,
                    path=path,
                    attempt=attempt,
                    delay_s=delay,
                    reason=str(error),
                )
                time.sleep(delay)

    # ---- Status -------------------------------------------------------

    def health(self) -> dict:
        """Read the robot's identity and software versions.

        Returns:
            Mapping with keys ``name``, ``api_version``, and
            ``system_version``.

        Raises:
            TransportError: If the robot cannot be reached.
        """
        body = self._retry("GET", "/health")
        return {
            "name": body.get("name"),
            "api_version": body.get("api_version"),
            "system_version": body.get("system_version"),
        }

    def is_reachable(self) -> bool:
        """Report whether the robot answers a health check.

        Returns:
            ``True`` if the health endpoint responded, else ``False``.
        """
        try:
            self.health()
        except TransportError:
            return False
        return True

    def get_instruments(self) -> list[dict]:
        """Read the pipettes and gripper currently attached.

        What a protocol asks for and what is on the robot are separate
        facts, and the analysis checks only the first. Reading this
        before a run is how an operator catches the difference.

        Returns:
            One entry per attached instrument, each with
            ``instrumentType``, ``instrumentModel``, ``mount``, and
            ``serialNumber``.

        Raises:
            TransportError: If the robot cannot be reached.
        """
        body = self._retry("GET", "/instruments")
        return body.get("data", [])

    def get_modules(self) -> list[dict]:
        """Read the hardware modules currently attached.

        Returns:
            One entry per attached module, each with ``moduleModel`` and
            ``serialNumber``.

        Raises:
            TransportError: If the robot cannot be reached.
        """
        body = self._retry("GET", "/modules")
        return body.get("data", [])

    # ---- Deck ---------------------------------------------------------

    def get_deck_configuration(self) -> list[dict]:
        """Read the fixtures currently registered on the deck.

        Returns:
            The ``cutoutFixtures`` list, each entry naming a cutout and
            the fixture mounted there.

        Raises:
            TransportError: If the robot cannot be reached.
        """
        body = self._retry("GET", "/deck_configuration")
        return body.get("data", {}).get("cutoutFixtures", [])

    def set_deck_configuration(self, fixtures: list[dict]) -> list[dict]:
        """Register deck fixtures such as staging slots and the chute.

        The waste chute and staging slots are deck fixtures rather than
        labware, so a protocol that uses them fails analysis unless they
        are registered first (spec section 3.4).

        Args:
            fixtures: Entries with ``cutoutId`` and ``cutoutFixtureId``,
                plus ``opentronsModuleSerialNumber`` for module
                fixtures.

        Returns:
            The fixture list as the robot stored it.

        Raises:
            TransportError: If the robot rejected the configuration.
        """
        body = self._retry(
            "PUT",
            "/deck_configuration",
            json={"data": {"cutoutFixtures": fixtures}},
        )
        return body.get("data", {}).get("cutoutFixtures", [])

    # ---- Data files ---------------------------------------------------

    def upload_data_file(
        self, file_path: str | Path, variable_name: str | None = None
    ) -> str:
        """Upload a file for a file-type runtime parameter.

        A file-type parameter is passed to the protocol by identifier,
        so the file must exist on the robot before the protocol that
        refers to it is uploaded (spec section 2.3).

        Args:
            file_path: Local path to the file.
            variable_name: Protocol parameter this file supplies. When
                given, the returned identifier is remembered under this
                name so the workflow methods can assemble
                ``runTimeParameterFiles`` on their own.

        Returns:
            The robot-assigned file identifier.

        Raises:
            FileNotFoundError: If the local file does not exist.
            TransportError: If the upload was rejected.
        """
        source = Path(file_path)
        if not source.is_file():
            raise FileNotFoundError(f"data file not found: {source}")

        with source.open("rb") as handle:
            body = self._retry(
                "POST",
                "/dataFiles",
                timeout=self.upload_timeout,
                files={"file": (source.name, handle)},
            )

        file_id = body.get("data", {}).get("id")
        if not file_id:
            raise TransportError("upload returned no file id", body=body)

        if variable_name:
            self._data_file_ids[variable_name] = file_id
        self.log_event("data_file_uploaded", name=source.name, file_id=file_id)
        return file_id

    def list_data_files(self) -> list[dict]:
        """List the data files stored on the robot.

        Returns:
            One entry per file, each with ``id`` and ``name``.

        Raises:
            TransportError: If the robot cannot be reached.
        """
        body = self._retry("GET", "/dataFiles")
        return body.get("data", [])

    # ---- Protocol -----------------------------------------------------

    def upload_protocol(
        self,
        protocol_path: str | Path,
        parameter_values: dict | None = None,
        parameter_files: dict | None = None,
    ) -> tuple[str, str]:
        """Upload a protocol and start its analysis.

        The robot begins analysing as soon as the file lands, so the
        analysis identifier returned here is the handle for the gate of
        spec section 5.2.

        Args:
            protocol_path: Local path to the protocol file.
            parameter_values: Scalar runtime parameters by variable
                name.
            parameter_files: File-type runtime parameters by variable
                name, holding file identifiers. Defaults to the
                identifiers collected by ``upload_data_file``.

        Returns:
            The protocol identifier and the analysis identifier.

        Raises:
            FileNotFoundError: If the local protocol does not exist.
            TransportError: If the upload was rejected, or returned no
                analysis to wait on.
        """
        source = Path(protocol_path)
        if not source.is_file():
            raise FileNotFoundError(f"protocol not found: {source}")

        files = parameter_files
        if files is None:
            files = dict(self._data_file_ids)

        form: dict[str, str] = {}
        if parameter_values:
            form["runTimeParameterValues"] = json.dumps(parameter_values)
        if files:
            form["runTimeParameterFiles"] = json.dumps(files)

        with source.open("rb") as handle:
            body = self._retry(
                "POST",
                "/protocols",
                timeout=self.upload_timeout,
                files={"files": (source.name, handle)},
                data=form,
            )

        data = body.get("data", {})
        summaries = data.get("analysisSummaries") or []
        if not data.get("id") or not summaries:
            raise TransportError("upload returned no analysis", body=body)

        self._protocol_id = data["id"]
        self._analysis_id = summaries[-1].get("id")
        self.log_event(
            "protocol_uploaded",
            name=source.name,
            protocol_id=self._protocol_id,
            analysis_id=self._analysis_id,
        )
        return self._protocol_id, self._analysis_id

    def get_analysis(
        self, protocol_id: str | None = None, analysis_id: str | None = None
    ) -> dict:
        """Read one analysis document.

        Args:
            protocol_id: Protocol to read; defaults to the last upload.
            analysis_id: Analysis to read; defaults to the last upload.

        Returns:
            The analysis document, including ``status``, ``errors``, and
            ``commands`` once it has completed.

        Raises:
            RunError: If no protocol has been uploaded and none was
                named.
            TransportError: If the robot cannot be reached.
        """
        target_protocol = protocol_id or self._protocol_id
        target_analysis = analysis_id or self._analysis_id
        if not target_protocol or not target_analysis:
            raise RunError("no analysis to read; upload a protocol first")

        body = self._retry(
            "GET",
            f"/protocols/{target_protocol}/analyses/{target_analysis}",
        )
        return body.get("data", {})

    def wait_for_analysis(
        self, protocol_id: str | None = None, analysis_id: str | None = None
    ) -> dict:
        """Poll an analysis until the robot finishes it.

        Args:
            protocol_id: Protocol to poll; defaults to the last upload.
            analysis_id: Analysis to poll; defaults to the last upload.

        Returns:
            The completed analysis document.

        Raises:
            RunError: If the configured limit passed with the analysis
                still incomplete.
            TransportError: If the robot cannot be reached.
        """
        deadline = time.monotonic() + self.analysis_limit
        while True:
            document = self.get_analysis(protocol_id, analysis_id)
            status = document.get("status")
            if status == "completed":
                self.log_event(
                    "analysis_completed",
                    result=document.get("result"),
                    errors=len(document.get("errors") or []),
                )
                return document
            if time.monotonic() >= deadline:
                raise RunError(
                    f"analysis did not complete within "
                    f"{self.analysis_limit:g}s; last status {status!r}"
                )
            time.sleep(self.analysis_period)

    def assert_analysis_clean(self, analysis: dict) -> None:
        """Block the workflow when the analysis found errors.

        This is the gate of spec section 5.2. It applies to every
        profile and offers no bypass, because an analysis error means
        the robot has already decided the protocol cannot run.

        Args:
            analysis: A completed analysis document.

        Raises:
            AnalysisError: If the document lists one or more errors.
        """
        errors = analysis.get("errors") or []
        if errors:
            summary = "; ".join(
                f"{item.get('errorType', 'error')}: {item.get('detail', '')}"
                for item in errors
            )
            self.log_event("analysis_rejected", errors=len(errors))
            raise AnalysisError(
                f"analysis reported {len(errors)} error(s): {summary}",
                errors=errors,
            )

    def list_protocols(self) -> list[dict]:
        """List the protocols stored on the robot.

        Returns:
            One entry per stored protocol.

        Raises:
            TransportError: If the robot cannot be reached.
        """
        body = self._retry("GET", "/protocols")
        return body.get("data", [])

    def delete_protocol(self, protocol_id: str) -> None:
        """Delete one stored protocol.

        Args:
            protocol_id: Protocol to delete.

        Raises:
            RunError: If the controller was built without
                ``allow_mutations``.
            TransportError: If the robot rejected the deletion.
        """
        if not self.allow_mutations:
            raise RunError(
                "deletion requires a controller built with allow_mutations"
            )
        self._retry("DELETE", f"/protocols/{protocol_id}")
        self.log_event("protocol_deleted", protocol_id=protocol_id)

    # ---- Run ----------------------------------------------------------

    def create_run(
        self,
        protocol_id: str | None = None,
        parameter_values: dict | None = None,
        parameter_files: dict | None = None,
    ) -> str:
        """Create a run for an uploaded protocol.

        The runtime parameters given here must match those sent with the
        upload; a mismatch makes the robot re-analyse the protocol and
        the gate that was just passed no longer describes what will run
        (spec section 5.1).

        Args:
            protocol_id: Protocol to run; defaults to the last upload.
            parameter_values: Scalar runtime parameters by variable
                name.
            parameter_files: File-type runtime parameters by variable
                name. Defaults to the identifiers collected by
                ``upload_data_file``.

        Returns:
            The run identifier.

        Raises:
            RunError: If no protocol has been uploaded and none was
                named.
            TransportError: If the robot rejected the run.
        """
        target = protocol_id or self._protocol_id
        if not target:
            raise RunError("no protocol to run; upload one first")

        files = parameter_files
        if files is None:
            files = dict(self._data_file_ids)

        payload: dict[str, Any] = {"protocolId": target}
        if parameter_values:
            payload["runTimeParameterValues"] = parameter_values
        if files:
            payload["runTimeParameterFiles"] = files

        body = self._retry("POST", "/runs", json={"data": payload})
        run_id = body.get("data", {}).get("id")
        if not run_id:
            raise TransportError("run creation returned no id", body=body)

        self._run_id = run_id
        self.log_event("run_created", run_id=run_id, protocol_id=target)
        return run_id

    def play(self, run_id: str | None = None) -> None:
        """Start or resume a run.

        Args:
            run_id: Run to start; defaults to the last created run.

        Raises:
            RunError: If no run has been created and none was named.
            TransportError: If the robot rejected the action.
        """
        self._action("play", run_id)

    def pause(self, run_id: str | None = None) -> None:
        """Pause a running run.

        Args:
            run_id: Run to pause; defaults to the last created run.

        Raises:
            RunError: If no run has been created and none was named.
            TransportError: If the robot rejected the action.
        """
        self._action("pause", run_id)

    def stop(self, run_id: str | None = None) -> None:
        """Stop a run without resuming it.

        Args:
            run_id: Run to stop; defaults to the last created run.

        Raises:
            RunError: If no run has been created and none was named.
            TransportError: If the robot rejected the action.
        """
        self._action("stop", run_id)

    def _action(self, action: str, run_id: str | None = None) -> None:
        """Post one run action.

        Actions are not retried: a repeated play or stop is a second
        instruction to the machine, not a second attempt at the first
        (spec section 6).

        Args:
            action: ``play``, ``pause``, or ``stop``.
            run_id: Run to act on; defaults to the last created run.

        Raises:
            RunError: If no run has been created and none was named.
            TransportError: If the robot rejected the action.
        """
        target = run_id or self._run_id
        if not target:
            raise RunError(f"no run to {action}; create one first")

        self._retry(
            "POST",
            f"/runs/{target}/actions",
            retryable=False,
            json={"data": {"actionType": action}},
        )
        self.log_event("run_action", action=action, run_id=target)

    def get_run(self, run_id: str | None = None) -> dict:
        """Read one run document.

        Args:
            run_id: Run to read; defaults to the last created run.

        Returns:
            The run document, including ``status`` and ``errors``.

        Raises:
            RunError: If no run has been created and none was named.
            TransportError: If the robot cannot be reached.
        """
        target = run_id or self._run_id
        if not target:
            raise RunError("no run to read; create one first")
        body = self._retry("GET", f"/runs/{target}")
        return body.get("data", {})

    def get_commands(
        self, run_id: str | None = None, page_length: int = 100
    ) -> list[dict]:
        """Read the commands recorded for a run.

        Args:
            run_id: Run to read; defaults to the last created run.
            page_length: Commands requested per page.

        Returns:
            The command list in execution order.

        Raises:
            RunError: If no run has been created and none was named.
            TransportError: If the robot cannot be reached.
        """
        target = run_id or self._run_id
        if not target:
            raise RunError("no run to read; create one first")

        commands: list[dict] = []
        cursor = 0
        while True:
            body = self._retry(
                "GET",
                f"/runs/{target}/commands",
                params={"cursor": cursor, "pageLength": page_length},
            )
            page = body.get("data", [])
            commands.extend(page)
            total = body.get("meta", {}).get("totalLength", len(commands))
            cursor += len(page)
            if not page or cursor >= total:
                return commands

    def get_errors(self, run_id: str | None = None) -> list[dict]:
        """Read the errors a run reported.

        Args:
            run_id: Run to read; defaults to the last created run.

        Returns:
            The run's error array, empty when it reported none.

        Raises:
            RunError: If no run has been created and none was named.
            TransportError: If the robot cannot be reached.
        """
        return self.get_run(run_id).get("errors") or []

    def monitor(self, run_id: str | None = None) -> dict:
        """Poll a run until it reaches a terminal state.

        An unrecognised state is logged and polling continues, per spec
        section 5.3: the robot's vocabulary may grow, and a state this
        tool has not heard of is not by itself a failure.

        Args:
            run_id: Run to watch; defaults to the last created run.

        Returns:
            The final run document.

        Raises:
            RunError: If no run has been created and none was named.
            TransportError: If the robot cannot be reached.
        """
        seen = ""
        while True:
            document = self.get_run(run_id)
            status = document.get("status", "")

            if status != seen:
                self.log_event("run_status", status=status)
                known = status in terminal_run_states or status in (
                    "idle",
                    "running",
                    "paused",
                    "blocked-by-open-door",
                    "stop-requested",
                    "finishing",
                    "awaiting-recovery",
                )
                if not known:
                    logger.warning("unknown run state %r; continuing", status)
                seen = status

            if status in terminal_run_states:
                return document

            time.sleep(self.run_period)

    def list_runs(self) -> list[dict]:
        """List the runs stored on the robot.

        Returns:
            One entry per stored run.

        Raises:
            TransportError: If the robot cannot be reached.
        """
        body = self._retry("GET", "/runs")
        return body.get("data", [])

    def delete_run(self, run_id: str) -> None:
        """Delete one stored run.

        Args:
            run_id: Run to delete.

        Raises:
            RunError: If the controller was built without
                ``allow_mutations``.
            TransportError: If the robot rejected the deletion.
        """
        if not self.allow_mutations:
            raise RunError(
                "deletion requires a controller built with allow_mutations"
            )
        self._retry("DELETE", f"/runs/{run_id}")
        self.log_event("run_deleted", run_id=run_id)

    # ---- Workflows ----------------------------------------------------

    def verify_only(
        self,
        protocol_path: str | Path,
        csv_path: str | Path | None = None,
        csv_variable: str = "csv_data",
        parameter_values: dict | None = None,
        deck_fixtures: list[dict] | None = None,
    ) -> dict:
        """Upload a protocol and judge its analysis without running it.

        This is steps 1 through 7 of spec section 5 -- everything the
        robot can tell you about a protocol while standing still.

        Args:
            protocol_path: Local path to the protocol file.
            csv_path: Local path to the CSV for a file-type parameter.
            csv_variable: Parameter name the CSV supplies.
            parameter_values: Scalar runtime parameters by variable
                name.
            deck_fixtures: Deck fixtures to register before uploading.

        Returns:
            Mapping with ``passed``, ``protocol_id``, ``analysis_id``,
            ``errors``, and ``command_count``.

        Raises:
            TransportError: If the robot cannot be reached, or rejected
                a request.
            RunError: If the analysis did not complete in time.
        """
        identity = self.health()
        self.log_event("connected", **identity)

        if deck_fixtures is not None:
            self.log_event(
                "deck_before", fixtures=len(self.get_deck_configuration())
            )
            self.set_deck_configuration(deck_fixtures)
            self.log_event("deck_applied", fixtures=len(deck_fixtures))

        if csv_path is not None:
            self.upload_data_file(csv_path, variable_name=csv_variable)

        protocol_id, analysis_id = self.upload_protocol(
            protocol_path, parameter_values=parameter_values
        )
        analysis = self.wait_for_analysis()

        errors = analysis.get("errors") or []
        verdict = {
            "passed": not errors,
            "protocol_id": protocol_id,
            "analysis_id": analysis_id,
            "errors": errors,
            "command_count": len(analysis.get("commands") or []),
        }
        self.save_artifact("analysis.json", analysis)
        return verdict

    def execute(
        self,
        protocol_path: str | Path,
        csv_path: str | Path | None = None,
        csv_variable: str = "csv_data",
        parameter_values: dict | None = None,
        deck_fixtures: list[dict] | None = None,
    ) -> dict:
        """Run a protocol from upload through to a terminal state.

        Implements the twelve steps of spec section 5. The analysis gate
        of step 7 runs before any run is created, so a protocol the
        robot has rejected never reaches the deck.

        Args:
            protocol_path: Local path to the protocol file.
            csv_path: Local path to the CSV for a file-type parameter.
            csv_variable: Parameter name the CSV supplies.
            parameter_values: Scalar runtime parameters by variable
                name. The same values are sent with the run, since a
                mismatch would trigger re-analysis.
            deck_fixtures: Deck fixtures to register before uploading.

        Returns:
            The final run document.

        Raises:
            AnalysisError: If the analysis reported errors. No run is
                created in that case.
            RunError: If the operator declined the run, or the analysis
                did not complete in time.
            TransportError: If the robot cannot be reached, or rejected
                a request.
        """
        verdict = self.verify_only(
            protocol_path,
            csv_path=csv_path,
            csv_variable=csv_variable,
            parameter_values=parameter_values,
            deck_fixtures=deck_fixtures,
        )
        self.assert_analysis_clean({"errors": verdict["errors"]})

        if self.requires_confirmation:
            answer = input(
                f"About to run {Path(protocol_path).name} on "
                f"{self.host}. The robot will move. Type yes to proceed: "
            )
            if answer.strip().lower() != "yes":
                raise RunError("operator declined the run")

        self.create_run(parameter_values=parameter_values)
        self.play()
        final = self.monitor()

        errors = final.get("errors") or []
        self.log_event(
            "run_finished", status=final.get("status"), errors=len(errors)
        )
        self.save_artifact("run.json", final)
        self.save_artifact("commands.json", self.get_commands())
        return final

    # ---- Records ------------------------------------------------------

    def save_artifact(self, name: str, payload: Any) -> Path:
        """Write one record of this session to the artifact directory.

        Args:
            name: File name to write.
            payload: JSON-serialisable content.

        Returns:
            The path written.
        """
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        destination = self.artifact_dir / name
        destination.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        return destination

    def log_event(self, event: str, **fields: Any) -> None:
        """Record one structured event.

        Args:
            event: Short event name.
            **fields: Additional context, serialised alongside the name.
        """
        logger.info(json.dumps({"event": event, **fields}, default=str))


def _describe_failure(error: FlexError) -> list[str]:
    """Return the robot's own explanation of a failure, line by line.

    The exception message names the request that failed; the robot's
    reason for refusing it travels separately, on
    :attr:`TransportError.body` or :attr:`AnalysisError.errors`. An
    operator needs the reason -- the file and line of a syntax error,
    the labware that could not be resolved -- so the CLI prints both.

    Args:
        error: The failure to describe.

    Returns:
        Human-readable lines, empty when the error carries no detail.
    """
    lines: list[str] = []

    if isinstance(error, AnalysisError):
        for entry in error.errors:
            kind = entry.get("errorType", "Error")
            lines.append(f"{kind}: {entry.get('detail', '')}".strip())
        return lines

    if isinstance(error, TransportError):
        body = error.body
        if isinstance(body, dict):
            for entry in body.get("errors", []) or []:
                title = entry.get("title") or entry.get("id") or "Error"
                lines.append(f"{title}: {entry.get('detail', '')}".strip())
            if not lines and body:
                lines.append(json.dumps(body, default=str)[:500])
        elif body:
            lines.append(str(body)[:500])

    return lines


def main(argv: list[str] | None = None) -> int:
    """Run the controller from the command line.

    Args:
        argv: Argument list; ``sys.argv`` is used when omitted.

    Returns:
        Process exit status: 0 on success, 1 on a reported failure.
    """
    parser = argparse.ArgumentParser(
        description="Upload, verify, and run a protocol on an Opentrons Flex."
    )
    parser.add_argument(
        "--profile",
        default="dev",
        choices=sorted(profile_hosts),
        help="dev targets localhost; robot targets a device and asks first",
    )
    parser.add_argument("--host", help="override the profile's host")
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--protocol", required=True, help="protocol file")
    parser.add_argument("--csv", help="CSV for a file-type parameter")
    parser.add_argument(
        "--csv-variable",
        default="csv_data",
        help="parameter name the CSV supplies",
    )
    parser.add_argument(
        "--deck", help="JSON file holding the deck fixture list"
    )
    parser.add_argument(
        "--params", help="JSON object of scalar runtime parameters"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="upload and analyse, but do not run",
    )
    parser.add_argument("--artifact-dir", help="where to write run records")
    parser.add_argument(
        "--timeout", type=float, default=default_request_timeout
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    deck_fixtures = None
    if args.deck:
        deck_fixtures = json.loads(Path(args.deck).read_text("utf-8"))
        if isinstance(deck_fixtures, dict):
            deck_fixtures = deck_fixtures.get("data", deck_fixtures).get(
                "cutoutFixtures", []
            )

    parameter_values = json.loads(args.params) if args.params else None

    controller = FlexController(
        host=args.host,
        profile=args.profile,
        port=args.port,
        timeout=args.timeout,
        artifact_dir=args.artifact_dir,
    )

    try:
        if args.verify_only:
            verdict = controller.verify_only(
                args.protocol,
                csv_path=args.csv,
                csv_variable=args.csv_variable,
                parameter_values=parameter_values,
                deck_fixtures=deck_fixtures,
            )
            print(json.dumps(verdict, indent=2, default=str))
            return 0 if verdict["passed"] else 1

        final = controller.execute(
            args.protocol,
            csv_path=args.csv,
            csv_variable=args.csv_variable,
            parameter_values=parameter_values,
            deck_fixtures=deck_fixtures,
        )
        print(json.dumps({"status": final.get("status")}, indent=2))
        return 0 if final.get("status") == "succeeded" else 1
    except FlexError as error:
        logger.error("%s: %s", type(error).__name__, error)
        for line in _describe_failure(error):
            logger.error("  %s", line)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

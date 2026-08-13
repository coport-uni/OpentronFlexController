"""Operator console for watching a protocol run on an Opentrons Flex.

Reads the robot's information, applies the deck, verifies a protocol
through the analysis gate, and then shows the program executing one
command at a time. Where ``flex_controller.main`` is a batch entry point
that prints a verdict, this console is for standing in front of the
machine and watching what it does.

It is a client of :class:`flex_controller.FlexController` and adds no
robot behaviour of its own.

Run it against the development server:

    python3 main.py --profile dev

Stop after the analysis gate, without moving anything:

    python3 main.py --profile dev --verify-only

Walk the planned steps one at a time:

    python3 main.py --profile dev --verify-only --step
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from flex_controller import (
    FlexController,
    FlexError,
    default_port,
    profile_hosts,
    terminal_run_states,
)

repository_root = Path(__file__).parent

default_protocol = repository_root / "protocols" / "OD_Normalization.py"
default_csv = repository_root / "data" / "od_normalization.csv"
default_deck = repository_root / "configs" / "deck_od_normalization.json"
default_parameters = {"dry_run": True, "waste_type": 1}

# The console re-reads the command list on every tick, so one page must
# be able to hold a whole run; the reference protocol plans 788 commands
# for a 96-row CSV.
command_page_length = 2000

# Fast enough to follow a simulated run, which finishes in a few
# seconds, without hammering the robot.
default_tick = 0.3

banner_width = 72

# Commands that describe setup rather than motion. They are worth
# showing, but they are not what an operator is watching for.
setup_commands = (
    "home",
    "loadPipette",
    "loadModule",
    "loadLabware",
    "loadLiquid",
    "configureNozzleLayout",
)


def print_banner(title: str) -> None:
    """Print a stage heading.

    Args:
        title: Heading text.
    """
    print()
    print("=" * banner_width)
    print(title)
    print("=" * banner_width)


def print_row(label: str, value: Any) -> None:
    """Print one aligned label and value.

    Args:
        label: Left-hand label.
        value: Value to show.
    """
    print(f"  {label:<24} {value}")


def build_name_map(analysis: dict) -> dict[str, str]:
    """Map the identifiers in commands to names a person can read.

    Commands refer to labware, modules, and pipettes by identifier. The
    analysis document is the only place those identifiers are tied to
    load names, so the map is built from it once and reused.

    Args:
        analysis: A completed analysis document.

    Returns:
        Identifier to display name, for every entity the analysis names.
    """
    names: dict[str, str] = {}
    for item in analysis.get("labware", []):
        label = item.get("displayName") or item.get("loadName", "labware")
        names[item["id"]] = label
    for item in analysis.get("modules", []):
        names[item["id"]] = item.get("model", "module")
    for item in analysis.get("pipettes", []):
        names[item["id"]] = item.get("pipetteName", "pipette")
    return names


def describe_location(location: Any, names: dict[str, str]) -> str:
    """Render a command's location field as a short phrase.

    Args:
        location: The ``location`` or ``newLocation`` value.
        names: Identifier to display name.

    Returns:
        A readable location, or an empty string when there is none.
    """
    if not isinstance(location, dict):
        return str(location) if location else ""
    if "slotName" in location:
        return f"slot {location['slotName']}"
    if "addressableAreaName" in location:
        return f"area {location['addressableAreaName']}"
    if "moduleId" in location:
        return names.get(location["moduleId"], "module")
    if "labwareId" in location:
        return names.get(location["labwareId"], "labware")
    return ""


def describe_command(command: dict, names: dict[str, str]) -> str:
    """Render one command as a single readable line.

    Args:
        command: A command from an analysis or a run.
        names: Identifier to display name.

    Returns:
        A description of what the robot does, or is planning to do.
    """
    kind = command.get("commandType", "?")
    params = command.get("params", {})
    where = names.get(params.get("labwareId", ""), "")
    well = params.get("wellName", "")
    target = f"{where}[{well}]" if where and well else where

    if kind == "comment":
        return f"comment: {params.get('message', '')}"
    if kind == "home":
        return "home the gantry"
    if kind == "loadPipette":
        mount = params.get("mount", "?")
        return f"load pipette {params.get('pipetteName', '?')} on {mount}"
    if kind == "loadModule":
        place = describe_location(params.get("location"), names)
        return f"load module {params.get('model', '?')} at {place}"
    if kind == "loadLabware":
        place = describe_location(params.get("location"), names)
        label = params.get("displayName") or params.get("loadName", "?")
        return f"load labware {label} at {place}"
    if kind == "loadLiquid":
        volumes = params.get("volumeByWell", {})
        return f"load liquid into {len(volumes)} well(s)"
    if kind == "configureNozzleLayout":
        setup = params.get("configurationParams", {})
        style = setup.get("style", "?")
        nozzle = setup.get("primaryNozzle", "?")
        return f"configure nozzles to {style}, starting {nozzle}"
    if kind == "pickUpTip":
        return f"pick up tip from {target}"
    if kind in ("aspirate", "dispense"):
        volume = params.get("volume", "?")
        return f"{kind} {volume} uL at {target}"
    if kind == "moveToAddressableArea":
        return f"move to {params.get('addressableAreaName', '?')}"
    if kind == "dropTipInPlace":
        return "drop tip"
    if kind == "dropTip":
        return f"drop tip at {target}"
    if kind == "moveLabware":
        strategy = params.get("strategy", "?")
        place = describe_location(params.get("newLocation"), names)
        moved = names.get(params.get("labwareId", ""), "labware")
        carrier = "gripper" if strategy == "usingGripper" else strategy
        return f"move {moved} to {place} using the {carrier}"
    if kind == "waitForDuration":
        return f"wait {params.get('seconds', '?')} s"
    return f"{kind} {json.dumps(params, default=str)[:60]}"


def format_step(index: int, command: dict, names: dict[str, str]) -> str:
    """Render one numbered step line, with its status.

    Args:
        index: Zero-based position in the command list.
        command: The command to render.
        names: Identifier to display name.

    Returns:
        A line ready to print.
    """
    status = command.get("status", "planned")
    marks = {
        "succeeded": "OK  ",
        "failed": "FAIL",
        "running": "RUN ",
        "queued": "... ",
    }
    mark = marks.get(status, "    ")
    return f"  {index + 1:>4}  {mark}  {describe_command(command, names)}"


def show_robot(controller: FlexController) -> dict:
    """Print who the robot is and what is attached to it.

    Args:
        controller: The controller to ask.

    Returns:
        The health document.
    """
    print_banner("1. Robot")
    identity = controller.health()
    print_row("host", controller.base_url)
    print_row("profile", controller.profile)
    print_row("name", identity["name"])
    print_row("api version", identity["api_version"])
    print_row("system version", identity["system_version"])

    print("\n  Attached instruments")
    instruments = controller.get_instruments()
    if not instruments:
        print("    none")
    for item in instruments:
        model = item.get("instrumentModel", "?")
        mount = item.get("mount", "?")
        serial = item.get("serialNumber", "?")
        print(f"    {mount:<10} {model:<22} {serial}")

    print("\n  Attached modules")
    modules = controller.get_modules()
    if not modules:
        print("    none")
    for item in modules:
        model = item.get("moduleModel", "?")
        serial = item.get("serialNumber", "?")
        print(f"    {model:<32} {serial}")

    return identity


def show_deck(controller: FlexController, fixtures: list[dict]) -> None:
    """Apply the deck configuration and print what is now registered.

    Args:
        controller: The controller to ask.
        fixtures: Fixtures to register, or an empty list to only read.
    """
    print_banner("2. Deck configuration")
    if fixtures:
        controller.set_deck_configuration(fixtures)
    stored = controller.get_deck_configuration()
    for entry in sorted(stored, key=lambda item: item["cutoutId"]):
        serial = entry.get("opentronsModuleSerialNumber", "")
        cutout = entry["cutoutId"]
        print(f"  {cutout:<10} {entry['cutoutFixtureId']:<46} {serial}")
    print(f"\n  {len(stored)} fixture(s) registered")


def show_analysis(analysis: dict) -> None:
    """Print the analysis verdict and the parameters it ran under.

    Args:
        analysis: A completed analysis document.
    """
    print_banner("4. Analysis")
    errors = analysis.get("errors") or []
    print_row("status", analysis.get("status"))
    print_row("result", analysis.get("result"))
    print_row("planned commands", len(analysis.get("commands") or []))
    print_row("errors", len(errors))

    print("\n  Runtime parameters")
    for item in analysis.get("runTimeParameters", []):
        name = item.get("variableName", "?")
        if item.get("type") == "csv_file":
            value = (item.get("file") or {}).get("name", "?")
        else:
            value = item.get("value")
        print(f"    {name:<16} {value}")

    if errors:
        print("\n  The robot rejected this protocol:")
        for item in errors:
            print(f"    {item.get('errorType', 'error')}")
            print(f"      {item.get('detail', '')}")
        print("\n  No run will be created (spec section 5.2).")
    else:
        print("\n  Gate passed: the robot accepted this protocol.")


def show_plan(analysis: dict, names: dict[str, str], step: bool) -> None:
    """Print the steps the robot intends to carry out.

    The analysis holds the whole plan before anything moves, so this is
    the one place a protocol can be read step by step with nothing at
    risk. With ``step`` set, the reader advances it by hand.

    Args:
        analysis: A completed analysis document.
        names: Identifier to display name.
        step: Whether to pause after each step.
    """
    commands = analysis.get("commands") or []
    print_banner(f"5. Planned steps ({len(commands)})")
    if step:
        print("  Press Enter to advance, or type q then Enter to skip.\n")

    for index, command in enumerate(commands):
        print(format_step(index, command, names))
        if step and input().strip().lower() == "q":
            print("  ... skipping the rest of the plan")
            return


def print_new_steps(
    commands: list[dict], shown: int, names: dict[str, str]
) -> int:
    """Print the commands that have appeared since the last read.

    Args:
        commands: The command list as it stands now.
        shown: How many were printed already.
        names: Identifier to display name.

    Returns:
        The new count of printed commands.
    """
    for index in range(shown, len(commands)):
        print(format_step(index, commands[index], names))
    return len(commands)


def stream_run(controller: FlexController, tick: float) -> dict:
    """Start the run and print each command as the robot finishes it.

    The robot appends to its command list as it executes, so the console
    reads the list on every tick and prints whatever is new. A simulated
    run finishes in seconds, so this scrolls quickly; the summary that
    follows is what to read afterwards.

    Names are rebuilt from the run on every tick, and the run is read
    *after* the command list. A run assigns its own identifiers to the
    same labware, so a map built from the analysis resolves nothing here.
    The run also lists a labware only once it has been loaded, so names
    read before the commands lag them by a tick and wells print blank.

    Args:
        controller: The controller driving the run.
        tick: Seconds between reads.

    Returns:
        The final run document.
    """
    print_banner("6. Running")
    controller.play()
    print("  play sent; watching the robot work\n")

    shown = 0
    started = time.monotonic()
    while True:
        commands = controller.get_commands(page_length=command_page_length)
        run = controller.get_run()
        names = build_name_map(run)
        shown = print_new_steps(commands, shown, names)

        if run.get("status", "") in terminal_run_states:
            # The commands were read a moment before the run document, so
            # read them once more to catch anything that finished between.
            print_new_steps(
                controller.get_commands(page_length=command_page_length),
                shown,
                names,
            )
            elapsed = time.monotonic() - started
            print(f"\n  run {run['status']} after {elapsed:.1f}s")
            return run
        time.sleep(tick)


def show_summary(controller: FlexController, final: dict) -> None:
    """Print what the run actually did, and anything that went wrong.

    Args:
        controller: The controller that drove the run.
        final: The final run document.
    """
    print_banner("7. Summary")
    commands = controller.get_commands(page_length=command_page_length)
    counts: dict[str, int] = {}
    failed = []
    for command in commands:
        kind = command.get("commandType", "?")
        counts[kind] = counts.get(kind, 0) + 1
        if command.get("status") == "failed":
            failed.append(command)

    print_row("status", final.get("status"))
    print_row("commands executed", len(commands))
    print_row("setup commands", sum(counts.get(k, 0) for k in setup_commands))

    print("\n  Commands by type")
    for kind, count in sorted(counts.items(), key=lambda p: -p[1]):
        print(f"    {kind:<28} {count}")

    errors = controller.get_errors()
    if errors:
        print("\n  Errors reported by the robot")
        for item in errors:
            print(f"    {item.get('errorType', 'error')}")
            print(f"      {item.get('detail', '')}")
    if failed:
        print(f"\n  {len(failed)} command(s) failed")
    if not errors and not failed:
        print("\n  No errors.")


def describe_failure(error: FlexError) -> list[str]:
    """Unpack a failure into the lines an operator needs to see.

    The exception's message names the request that failed; the robot's
    own explanation of why lives on the exception's public attributes.
    Both belong on screen, since the second is the actionable half.

    Args:
        error: The failure to render.

    Returns:
        The summary line, followed by whatever the robot explained.
    """
    lines = [str(error)]
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        for item in body.get("errors", []):
            lines.append(f"{item.get('id', 'error')}: {item.get('detail', '')}")
    for item in getattr(error, "errors", None) or []:
        lines.append(
            f"{item.get('errorType', 'error')}: {item.get('detail', '')}"
        )
    return lines


def build_parser() -> argparse.ArgumentParser:
    """Define the console's command-line interface.

    Returns:
        The configured parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Read a Flex's information, verify a protocol, and watch it "
            "run step by step."
        )
    )
    parser.add_argument(
        "--profile",
        default="dev",
        choices=sorted(profile_hosts),
        help="dev targets localhost; robot targets a device and asks first",
    )
    parser.add_argument("--host", help="override the profile's host")
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument(
        "--protocol",
        default=str(default_protocol),
        help="protocol file; defaults to the reference protocol",
    )
    parser.add_argument(
        "--csv",
        default=str(default_csv),
        help="CSV for the file-type parameter; pass an empty string to omit",
    )
    parser.add_argument(
        "--deck",
        default=str(default_deck),
        help="deck fixture list; pass an empty string to leave the deck alone",
    )
    parser.add_argument(
        "--params",
        help="JSON object of scalar runtime parameters",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="stop after the analysis gate; nothing moves",
    )
    parser.add_argument(
        "--step",
        action="store_true",
        help="walk the planned steps one at a time, waiting for Enter",
    )
    parser.add_argument(
        "--no-plan",
        action="store_true",
        help="skip the planned-step listing, which is long",
    )
    parser.add_argument(
        "--tick",
        type=float,
        default=default_tick,
        help="seconds between reads while the run is in flight",
    )
    parser.add_argument("--artifact-dir", help="where to write run records")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the console.

    Args:
        argv: Argument list; ``sys.argv`` is used when omitted.

    Returns:
        Process exit status: 0 on success, 1 on a reported failure, and
        2 when the operator declined the run.
    """
    args = build_parser().parse_args(argv)

    fixtures: list[dict] = []
    if args.deck:
        loaded = json.loads(Path(args.deck).read_text("utf-8"))
        if isinstance(loaded, dict):
            loaded = loaded.get("data", loaded).get("cutoutFixtures", [])
        fixtures = loaded

    parameters = (
        json.loads(args.params) if args.params else dict(default_parameters)
    )

    controller = FlexController(
        host=args.host,
        profile=args.profile,
        port=args.port,
        artifact_dir=args.artifact_dir,
    )
    run_id = None

    try:
        show_robot(controller)
        show_deck(controller, fixtures)

        print_banner("3. Upload")
        if args.csv:
            file_id = controller.upload_data_file(args.csv, "csv_data")
            print_row("csv", Path(args.csv).name)
            print_row("file id", file_id)
        protocol_id, analysis_id = controller.upload_protocol(
            args.protocol, parameter_values=parameters
        )
        print_row("protocol", Path(args.protocol).name)
        print_row("protocol id", protocol_id)
        print_row("analysis id", analysis_id)

        analysis = controller.wait_for_analysis()
        names = build_name_map(analysis)
        show_analysis(analysis)

        # Saved here rather than after the run, so that a rejected or a
        # verify-only protocol still leaves the evidence behind. An
        # analysis the operator cannot re-read is an analysis they have
        # to run again to talk about.
        saved = controller.save_artifact("analysis.json", analysis)

        if analysis.get("errors"):
            print(f"\n  analysis written to {saved}")
            print("\nStopping here. Fix the protocol and run again.")
            return 1

        if not args.no_plan:
            show_plan(analysis, names, args.step)

        if args.verify_only:
            print_banner("Done: verified, nothing was run")
            print(f"  analysis written to {saved}")
            return 0

        if controller.requires_confirmation:
            print_banner("Confirm")
            answer = input(
                f"The robot at {controller.host} will move. "
                "Type yes to proceed: "
            )
            if answer.strip().lower() != "yes":
                print("Declined; nothing was run.")
                return 2

        run_id = controller.create_run(parameter_values=parameters)
        final = stream_run(controller, args.tick)
        show_summary(controller, final)

        controller.save_artifact("run.json", final)
        controller.save_artifact(
            "commands.json",
            controller.get_commands(page_length=command_page_length),
        )
        print(f"\n  records written to {controller.artifact_dir}")

        return 0 if final.get("status") == "succeeded" else 1
    except FlexError as error:
        print_banner(f"Failed: {type(error).__name__}")
        for line in describe_failure(error):
            print(f"  {line}")
        return 1
    except KeyboardInterrupt:
        # Ctrl-C stops the console, not the robot. Saying so matters:
        # an operator who assumes otherwise walks away from a live deck.
        print("\n\nInterrupted.")
        if run_id is not None:
            print(
                "  The console has stopped watching, but the run is still "
                "going.\n  To stop the robot, run:\n"
                f"    curl -X POST -H 'Opentrons-Version: 3' \\\n"
                f"      -H 'Content-Type: application/json' \\\n"
                f'      -d \'{{"data": {{"actionType": "stop"}}}}\' \\\n'
                f"      {controller.base_url}/runs/{run_id}/actions"
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

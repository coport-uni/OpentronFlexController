# Prints what the controller actually reports for each injected fault, so the
# detection can be read rather than inferred from a green test. Run against the
# development server: python3 claude_test/show_error_detection.py

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from flex_controller import (  # noqa: E402
    AnalysisError,
    FlexController,
    TransportError,
)

deck = json.loads((root / "configs" / "deck_od_normalization.json").read_text())
params = {"dry_run": True, "waste_type": 1}
faults = root / "tests" / "protocols"


def show(title, fn):
    print("=" * 72)
    print(title)
    print("=" * 72)
    try:
        fn()
        print("NO ERROR RAISED")
    except AnalysisError as e:
        print(f"AnalysisError, {len(e.errors)} entry/entries")
        for item in e.errors:
            print(f"  errorType : {item.get('errorType')}")
            print(f"  errorCode : {item.get('errorCode')}")
            print(f"  detail    : {item.get('detail')}")
    except TransportError as e:
        print(f"TransportError, HTTP {e.status_code}")
        for item in (e.body or {}).get("errors", []):
            print(f"  id     : {item.get('id')}")
            print(f"  detail : {item.get('detail')}")
    print()


def controller():
    c = FlexController(profile="dev", artifact_dir=root / "artifacts")
    c.set_deck_configuration(deck)
    return c


def undefined_labware():
    c = controller()
    c.assert_analysis_clean(
        {"errors": c.verify_only(faults / "bad_labware.py")["errors"]}
    )


def syntax_error():
    controller().verify_only(faults / "bad_syntax.py")


def layout_collision():
    c = controller()
    c.assert_analysis_clean(
        {"errors": c.verify_only(faults / "bad_layout.py")["errors"]}
    )


def missing_csv_parameter():
    c = controller()
    c.upload_protocol(
        root / "protocols" / "OD_Normalization.py",
        parameter_values=params,
        parameter_files={},
    )
    c.assert_analysis_clean(c.wait_for_analysis())


def unknown_run_id():
    controller().get_run("00000000-0000-0000-0000-000000000000")


def deck_fixture_missing():
    # The chute is a deck fixture, so this fault only shows at run time.
    c = controller()
    broken = [e for e in deck if e["cutoutId"] != "cutoutD3"]
    broken.append(
        {"cutoutId": "cutoutD3", "cutoutFixtureId": "singleRightSlot"}
    )
    c.set_deck_configuration(broken)
    try:
        source = root / "protocols" / "OD_Normalization.py"
        unique = root / "artifacts" / "deck_probe.py"
        unique.parent.mkdir(parents=True, exist_ok=True)
        unique.write_text(source.read_text() + "\n# deck probe\n")
        c.upload_data_file(root / "data" / "od_normalization.csv", "csv_data")
        c.upload_protocol(unique, parameter_values=params)
        analysis = c.wait_for_analysis()
        print(f"analysis errors: {len(analysis['errors'])} (clean; see note)")
        c.create_run(parameter_values=params)
        c.play()
        final = c.monitor()
        print(f"run status: {final['status']}")
        for item in c.get_errors():
            print(f"  errorType : {item.get('errorType')}")
            print(f"  detail    : {item.get('detail')}")
    finally:
        c.set_deck_configuration(deck)


show("1. Undefined labware load name (TC-08)", undefined_labware)
show("2. Python syntax error", syntax_error)
show("3. Deck layout collision, two labware in slot B2", layout_collision)
show("4. Missing CSV runtime parameter file", missing_csv_parameter)
show("5. Unknown run id, HTTP 4xx", unknown_run_id)
print("=" * 72)
print("6. Deck fixture missing: cutoutD3 has no waste chute (TC-09)")
print("=" * 72)
deck_fixture_missing()

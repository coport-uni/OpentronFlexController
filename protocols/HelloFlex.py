"""A minimal Flex protocol, to show what uploading a .py actually does.

Every command the console prints is derived by the robot from this file.
Change a volume or a well here, upload again, and the step list changes
to match.
"""

from opentrons import protocol_api

metadata = {"protocolName": "Hello Flex"}
requirements = {"robotType": "Flex", "apiLevel": "2.20"}


def run(protocol: protocol_api.ProtocolContext):
    """Pick up one tip, move 100 uL between two wells, discard the tip."""
    tiprack = protocol.load_labware(
        "opentrons_flex_96_tiprack_200ul", location="A2", label="Tips"
    )
    plate = protocol.load_labware(
        "corning_96_wellplate_360ul_flat", location="B2", label="Plate"
    )
    reservoir = protocol.load_labware(
        "nest_1_reservoir_195ml", location="B3", label="Reservoir"
    )
    chute = protocol.load_waste_chute()

    pipette = protocol.load_instrument("flex_96channel_1000")
    pipette.configure_nozzle_layout(style=protocol_api.SINGLE, start="A1")

    protocol.comment("Hello from a Python file uploaded to the Flex")
    pipette.pick_up_tip(tiprack.wells()[0])
    pipette.aspirate(100, reservoir.wells()[0])
    pipette.dispense(100, plate["A1"])
    pipette.drop_tip(chute)

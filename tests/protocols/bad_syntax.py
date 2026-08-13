"""Fault injection: a Python syntax error.

The ``for`` statement below is missing its colon, so the file cannot be
compiled. The analysis must report the failure before any run exists.
"""

from opentrons import protocol_api

metadata = {"protocolName": "Syntax error"}
requirements = {"robotType": "Flex", "apiLevel": "2.20"}


def run(protocol: protocol_api.ProtocolContext):
    """Fail to compile."""
    tiprack = protocol.load_labware("opentrons_flex_96_tiprack_200ul", "A2")
    for well in tiprack.wells()
        protocol.comment(str(well))

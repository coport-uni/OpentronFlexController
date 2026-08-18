"""Fault injection: a deck layout collision.

Two labware are loaded into slot B2. The slot can hold only one, so the
analysis must reject the layout.
"""

from opentrons import protocol_api

metadata = {"protocolName": "Layout collision"}
requirements = {"robotType": "Flex", "apiLevel": "2.20"}


def run(protocol: protocol_api.ProtocolContext):
    """Claim one slot twice."""
    protocol.load_labware("corning_96_wellplate_360ul_flat", location="B2")
    protocol.load_labware("nest_1_reservoir_195ml", location="B2")

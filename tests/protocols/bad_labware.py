"""Fault injection for TC-08: a labware load name that does not exist.

The robot cannot resolve ``corning_96_wellplate_9999ul_flat`` to a
definition, so the analysis must report an error and the controller must
refuse to create a run.
"""

from opentrons import protocol_api

metadata = {"protocolName": "TC-08 undefined labware"}
requirements = {"robotType": "Flex", "apiLevel": "2.20"}


def run(protocol: protocol_api.ProtocolContext):
    """Load a plate whose definition the robot does not have."""
    protocol.load_labware("corning_96_wellplate_9999ul_flat", location="B2")

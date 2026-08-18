from opentrons import protocol_api


metadata = {
    'protocolName': 'EP Tube + 12-Well Reservoir to D2 A1 Test',
}

requirements = {
    'robotType': 'Flex',
    'apiLevel': '2.21'
}

TRANSFER_VOLUME_UL = 100


def run(protocol: protocol_api.ProtocolContext):
    waste_chute = protocol.load_waste_chute()

    # Keep the existing full-deck module layout.
    # 레이아웃 배치
    thermocycler = protocol.load_module('thermocycler module gen2')
    mag_block = protocol.load_module('magneticBlockV1', 'C1')
    heater_shaker = protocol.load_module('heaterShakerModuleV1', 'D1')

    # Keep the existing labware positions.
    heater_shaker.load_labware(
        'thermo_fisher_nunclon_sphera_96_well_u_bottom_174925'
    )
    tube_rack = protocol.load_labware(
        'opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap',
        'C2'
    )
    reservoir = protocol.load_labware(
        'nest_12_reservoir_22ml',
        'C3'
    )
    destination_plate = protocol.load_labware(
        'corning_96_wellplate_360ul_flat',
        'D2'
    )

    # A2: 200 uL tips used by the left Flex 1-channel 1000 uL pipette.
    tiprack_200 = protocol.load_labware(
        'opentrons_flex_96_filtertiprack_200ul',
        'A2'
    )

    # Keep the existing B2/B3 labware represented on the deck, but do not use it.
    protocol.load_labware(
        'opentrons_flex_96_filtertiprack_1000ul',
        'B2'
    )
    protocol.load_labware(
        'opentrons_flex_96_filtertiprack_1000ul',
        'B3'
    )

    pipette_1ch = protocol.load_instrument(
        'flex_1channel_1000',
        'left',
        tip_racks=[tiprack_200]
    )

    heater_shaker.close_labware_latch()

    ep_tube_a1 = tube_rack['A1']
    reservoir_a1 = reservoir['A1']
    destination_a1 = destination_plate['A1']

    # Step 1: EP tube rack C2 A1 -> D2 plate A1.
    protocol.comment(
        'Step 1: Transferring 100 uL from EP tube C2 A1 to D2 A1.'
    )
    pipette_1ch.pick_up_tip(tiprack_200['A1'])
    pipette_1ch.aspirate(
        TRANSFER_VOLUME_UL,
        ep_tube_a1.bottom(z=1)
    )
    pipette_1ch.dispense(
        TRANSFER_VOLUME_UL,
        destination_a1.top(z=-2)
    )
    pipette_1ch.drop_tip(waste_chute)

    # Step 2: 12-well reservoir C3 A1 -> the same D2 plate A1 well.
    protocol.comment(
        'Step 2: Transferring 100 uL from reservoir C3 A1 to D2 A1.'
    )
    pipette_1ch.pick_up_tip(tiprack_200['B1'])
    pipette_1ch.aspirate(
        TRANSFER_VOLUME_UL,
        reservoir_a1.bottom(z=1)
    )
    pipette_1ch.dispense(
        TRANSFER_VOLUME_UL,
        destination_a1.top(z=-2)
    )
    pipette_1ch.drop_tip(waste_chute)

    heater_shaker.open_labware_latch()
    protocol.comment(
        'Completed: D2 A1 contains 100 uL from the EP tube and '
        '100 uL from the reservoir.'
    )

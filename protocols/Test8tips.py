from opentrons import protocol_api

metadata = {'protocolName': '3) Cell Seeding 2mm 8ch P1000_260818'}
requirements = {"robotType": "Flex", "apiLevel": "2.21"}

# Aspirate and mix 2 mm above the bottom of the Opentrons Tough 300 mL reservoir.
RESERVOIR_WORKING_HEIGHT_MM = 2

# Cell-suspension handling profile.
# This protocol uses API 2.21 direct pipetting commands, not an Opentrons
# verified liquid class. Low rates reduce shear stress and splashing.
CELL_SUSPENSION_MIX_FLOW_RATE_UL_S = 100
CELL_SUSPENSION_ASPIRATE_RATE = 0.10
CELL_SUSPENSION_DISPENSE_RATE = 0.05
POST_ASPIRATE_DELAY_SECONDS = 1
POST_DISPENSE_DELAY_SECONDS = 1

# Multi-dispense settings for the P1000 8-channel pipette.
# Batch 1: 9 columns x 100 uL + 20 uL residual = 920 uL per channel.
# Batch 2: 3 columns x 100 uL + 20 uL residual = 320 uL per channel.
MULTI_DISPENSE_COLUMNS_PER_BATCH = 9
DISPOSAL_VOLUME_UL = 20
POST_DISPENSE_AIR_GAP_UL = 20
AIR_GAP_HEIGHT_MM = 5


def add_parameters(parameters: protocol_api.Parameters):
    parameters.add_int(
        variable_name='start_tip_column',
        display_name='8채널 시작 팁 열',
        description=(
            '오른쪽 8채널 1000 uL 피펫이 첫 팁을 집을 열입니다. '
            '선택한 열의 A행 팁을 기준으로 8개 팁을 동시에 장착합니다.'
        ),
        default=6,
        minimum=1,
        maximum=12
    )
    parameters.add_bool(
        variable_name='demo_mode',
        display_name='Demo 버전',
        description=(
            '켜면 사용한 팁을 집었던 팁랙 위치로 되돌리고, '
            '끄면 사용한 팁을 폐기합니다.'
        ),
        default=False
    )


def run(protocol: protocol_api.ProtocolContext):
    trash = protocol.load_waste_chute()
    
    # Full deck modules
    thermocycler = protocol.load_module('thermocycler module gen2')
    mag_block = protocol.load_module('magneticBlockV1', 'C1')
    heater_shaker = protocol.load_module('heaterShakerModuleV1', 'D1')
    
    # Keep the existing deck setup. The destination cell-culture plate is at D2.
    heater_shaker.load_labware('corning_3590_96_wellplate_360ul_flat')
    media_reservoir = protocol.load_labware(
        'opentrons_tough_1_reservoir_300ml',
        'C2'
    )
    cell_plate = protocol.load_labware(
        'spl_96_well_cell_culture_plate_330ul_u_bottom',
        'D2'
    )
    
    # Two 1000 uL filtered tip racks placed directly on the deck.
    # Flex 1- and 8-channel pipettes do not use the 96-channel tip-rack adapter.
    tipracks_1000 = [
        protocol.load_labware(
            'opentrons_flex_96_filtertiprack_1000ul',
            slot
        )
        for slot in ['A2', 'B2']
    ]

    pipette_1ch = protocol.load_instrument(
        'flex_1channel_1000',
        'left',
        tip_racks=tipracks_1000
    )
    pipette_8ch = protocol.load_instrument(
        'flex_8channel_1000',
        'right',
        tip_racks=tipracks_1000
    )
    
    heater_shaker.close_labware_latch()
    
    media = media_reservoir['A1']
    destination_columns = cell_plate.rows()[0]
    start_tip = tipracks_1000[0].rows()[0][protocol.params.start_tip_column - 1]

    protocol.comment(
        'Step 1: Picking up 8 tips from column '
        f'{protocol.params.start_tip_column} of the A2 1000 uL tip rack.'
    )
    pipette_8ch.pick_up_tip(start_tip)

    # For an 8-channel pipette, 100 uL means 100 uL per channel.
    # Gently resuspend cells immediately before aspiration.
    # Mix and aspirate 2 mm above the reservoir bottom.
    protocol.comment(
        'Step 2: Resuspending cells in C2 at 2 mm above the bottom '
        'and 100 uL/sec.'
    )
    original_aspirate_flow_rate = pipette_8ch.flow_rate.aspirate
    original_dispense_flow_rate = pipette_8ch.flow_rate.dispense
    pipette_8ch.flow_rate.aspirate = CELL_SUSPENSION_MIX_FLOW_RATE_UL_S
    pipette_8ch.flow_rate.dispense = CELL_SUSPENSION_MIX_FLOW_RATE_UL_S
    pipette_8ch.mix(
        repetitions=3,
        volume=100,
        location=media.bottom(z=RESERVOIR_WORKING_HEIGHT_MM),
        rate=1.0
    )
    pipette_8ch.flow_rate.aspirate = original_aspirate_flow_rate
    pipette_8ch.flow_rate.dispense = original_dispense_flow_rate

    # Multi-dispense in two batches while keeping the same 8 tips attached.
    for batch_start in range(
        0,
        len(destination_columns),
        MULTI_DISPENSE_COLUMNS_PER_BATCH
    ):
        batch_destinations = destination_columns[
            batch_start:batch_start + MULTI_DISPENSE_COLUMNS_PER_BATCH
        ]
        batch_number = (
            batch_start // MULTI_DISPENSE_COLUMNS_PER_BATCH
        ) + 1
        batch_aspirate_volume = (
            len(batch_destinations) * 100 + DISPOSAL_VOLUME_UL
        )
        protocol.comment(
            f'Step 3.{batch_number}: Aspirating '
            f'{batch_aspirate_volume} uL per channel from C2 for '
            f'{len(batch_destinations)} destination columns.'
        )
        pipette_8ch.aspirate(
            volume=batch_aspirate_volume,
            location=media.bottom(z=RESERVOIR_WORKING_HEIGHT_MM),
            rate=CELL_SUSPENSION_ASPIRATE_RATE
        )
        protocol.delay(
            seconds=POST_ASPIRATE_DELAY_SECONDS,
            msg='Allowing the cell suspension to stabilize in the tips.'
        )

        for destination_offset, destination in enumerate(batch_destinations):
            column_number = batch_start + destination_offset + 1
            protocol.comment(
                f'Step 4.{column_number}: Dispensing 100 uL into D2 column '
                f'{column_number}.'
            )
            pipette_8ch.dispense(
                volume=100,
                location=destination.top(z=-4),
                rate=CELL_SUSPENSION_DISPENSE_RATE,
                push_out=0
            )
            protocol.delay(
                seconds=POST_DISPENSE_DELAY_SECONDS,
                msg=(
                    'Allowing dispensing to settle before moving to the '
                    'next column.'
                )
            )

        # Draw air above the last destination to pull any hanging droplet into
        # the tips. Move to the Waste Chute and clear both the 20 uL residual
        # liquid and the 20 uL air gap. The same tips remain attached for the
        # next batch.
        protocol.comment(
            f'Step 4.{batch_number} reset: Adding a '
            f'{POST_DISPENSE_AIR_GAP_UL} uL air gap, then clearing residual '
            'liquid and air in the Waste Chute.'
        )
        pipette_8ch.air_gap(
            volume=POST_DISPENSE_AIR_GAP_UL,
            height=AIR_GAP_HEIGHT_MM
        )
        pipette_8ch.blow_out(trash)

    if protocol.params.demo_mode:
        # Return the 8 tips to the same selected A2 column.
        protocol.comment(
            'Step 5: Returning the 8-tip set to its selected A2 column.'
        )
        pipette_8ch.return_tip()
    else:
        protocol.comment(
            'Step 5: Dropping tips into the Waste Chute. '
            'The Waste Chute cover must be removed.'
        )
        pipette_8ch.drop_tip(trash)
    
    heater_shaker.open_labware_latch()

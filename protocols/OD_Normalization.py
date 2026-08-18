from opentrons import protocol_api
from opentrons.protocol_api import COLUMN, ALL, SINGLE, ROW
import numpy as np


metadata = {
    'protocolName': 'OD-600 Normalization using 96-channel pipette',
    'author': 'Anurag Kanase <anurag.kanase@opentrons.com>',
    'description': "OD-600 Normalization Protocol using Custom CSV File.\nThe protocol normalizes Culture plate OD taken at 600nm.\n Note: With 96-ch pipette, the tips cannot be returned to the tiprack."
}

requirements = {"robotType": "Flex", "apiLevel": "2.20"}

def add_parameters(parameters):

    parameters.add_csv_file(
    variable_name="csv_data",
    display_name="Normalization CSV",
    description="Please use the template CSV from the plate reader "
)

    parameters.add_bool(
        variable_name="dry_run",
        display_name="Dry Run",
        description="This is held for later use. Does not affect the protocol.",
        default=True
    )

    parameters.add_int(
        variable_name="waste_type",
        display_name="Waste Type",
        description="Where to dispose of the waste.",
        default=1,
        choices=[
            {"display_name": "Waste Chute", "value": 1},
            {"display_name": "Trash bin", "value": 2},
        ]
    )
def run(protocol: protocol_api.ProtocolContext):
    dry_run = protocol.params.dry_run
    waste_type = protocol.params.waste_type

    def drop():
        if dry_run:
            pip.drop_tip()
        else:
            pip.drop_tip()

    
    #def fas_parse():
    #     """
    #     This function mimics the Opentrons CSV Parser format. 
    #     It reads the CSV file and returns the file contents and the CSVParameter object.
    #     file_csv : Raw file contents
    #     content_csv : CSVParameter object, can be further parsed using parse_as_csv() method and contents method.
    #     """
    #     from opentrons.protocols.api_support.types import APIVersion
    #     from opentrons import protocol_api
    #     LOCATION = "csv_template.csv" # I am reading a local file
    #     with open(LOCATION, "rb") as file:
    #         file_csv = file.read()
    #     content_csv = protocol_api.CSVParameter(contents=file_csv, api_version=APIVersion(2, 20))
    #     return file_csv, content_csv

    # file_csv, content_csv = fas_parse()
    content_csv = protocol.params.csv_data

    csv_data = content_csv.parse_as_csv()
    source_wells, dest_wells, dil_volumes, dna_volumes = zip(*csv_data)

    tc = protocol.load_module("thermocyclerModuleV2")
    temp_mod = protocol.load_module("temperature module gen2", 'C1')
    hs = protocol.load_module(module_name="heaterShakerModuleV1", location="D1")
    culture_plate = temp_mod.load_labware("corning_96_wellplate_360ul_flat", label="Culture Plate")
    tiprack = protocol.load_labware("opentrons_flex_96_tiprack_200ul", location="A2", label="Tiprack 1")
    tiprack2 = protocol.load_labware("opentrons_flex_96_tiprack_200ul", location="A4", label="Tiprack 2")


    normalization_plate = protocol.load_labware("corning_96_wellplate_360ul_flat",location="B2", label="Normalization Plate")
    reservoir = protocol.load_labware("nest_1_reservoir_195ml", location="B3", label="Diluent Reservoir")

    if waste_type == 2:
        trash = protocol.load_trash_bin("A3")
    else:
        trash = protocol.load_waste_chute()

    pip = protocol.load_instrument("flex_96channel_1000")

    pip.configure_nozzle_layout(
        style=SINGLE,
        start="A1"
    )
    global tips
    tips = tiprack.wells()[::-1]
    def pickup():
        global tips
        if tips == []:
            protocol.comment("----- Switching to Tiprack 2 -----")
            protocol.move_labware(tiprack, "D4", use_gripper=True)
            protocol.move_labware(tiprack2, "A2", use_gripper=True)
            tips = tiprack2.wells()[::-1]
            pip.pick_up_tip(tips.pop(0))
        else:
            pip.pick_up_tip(tips.pop(0))

    
    def add_liquid(name, color, well, volume):
        liquid = protocol.define_liquid(name = name, description = "generic", display_color = color)
        well.load_liquid(liquid=liquid, volume=volume)
        return liquid , well
    
    for well in source_wells[1:]:
        add_liquid("DNA sample", "#f08000", culture_plate[well], 200)
    
    add_liquid("Diluent", "#008000", reservoir.wells()[0], 10000)

    if dil_volumes[1] is not '':
        protocol.comment("Transferring Diluent to Normalization Plate")
        
        pickup()
        for vol, dest_well in zip(dil_volumes[1:], dest_wells[1:]):
            pip.transfer(float(vol), reservoir.wells()[0], normalization_plate[dest_well], new_tip="never")
        drop()

    if dna_volumes[1] is not '':
        protocol.comment("Transferring DNA to Normalization Plate")
        for vol, source_well, dest_well in zip(dna_volumes[1:], source_wells[1:], dest_wells[1:]):
            pickup()
            pip.transfer(float(vol), culture_plate[source_well], normalization_plate[dest_well], new_tip="never")
            drop()   






    


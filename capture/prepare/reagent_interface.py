"""
TODO Pendletoon, doc this whole module
"""

import logging
import pandas as pd

import capture.devconfig as config
from utils.data_handling import update_sheet_column
from utils import globals
from utils.globals import lab_safeget

modlog = logging.getLogger('capture.prepare.interface')


def _get_reagent_header_cells(column: str):
    """Get all cells in the rows that start each reagent for a given colum

    :param column: (str) in {A, B, ..., Z, AA, AB, ...}
    """
    startrow = lab_safeget(config.lab_vars, globals.get_lab(), 'reagent_interface_amount_startrow')
    reagent_interface_step = int(lab_safeget(config.lab_vars, globals.get_lab(), 'maxreagentchemicals')) + 1
    num_reagents = lab_safeget(config.lab_vars, globals.get_lab(), 'max_reagents')
    stoprow = startrow + reagent_interface_step * num_reagents
    result = [column + str(i) for i in range(startrow, stoprow, reagent_interface_step)]
    return result

def get_reagent_target_volumes(erdf, deadvolume):
    """Target volumes for reagent preparation as dictionary"""
    reagent_target_volumes = {}
    for reagent in erdf.columns:
        reagent_volume = erdf[reagent].sum() + deadvolume
        reagentname = reagent.split(' ')[0]
        reagent_target_volumes[reagentname] = reagent_volume
    return reagent_target_volumes


def build_nominals_df(rdict,
                      chemicalnamedf,
                      target_final_volume,
                      liquidlist,
                      maxreagentchemicals,
                      chemdf):
    ''' calculate the mass of each chemical return dataframe

    TODO: write out nominal molarity to google sheets, see issue#52

    :param chemdf:  Chemical data frame from google drive.
    :returns: a dataframe sized for export to version 2.x interface
    '''
    nominalsdf = pd.DataFrame()
    itemcount = 1
    chemicalnamedf.sort_index(inplace=True)
    for index, row in chemicalnamedf.iterrows():
        reagentname = row['reagentnames']
        chemabbr = row['chemabbr']
        if row['chemabbr'] ==  'Final Volume = ':
            formulavollist = []
            formulavol = 'null'
            itemcount = 1
            finalvolindex = index
            pass
        else:
            # stock solutions should be summed for final total volume
            if chemabbr in liquidlist or chemabbr == 'FAH':  # todo dejank
                formulavol = (target_final_volume[reagentname]/1000).round(2)
                formulavollist.append(formulavol)
                nominalsdf.loc[index, "nominal_amount"] = formulavol
                nominalsdf.loc[index, "Unit"] = 'milliliter'
                itemcount+=1
            elif chemabbr == 'null':
                nominalsdf.loc[index, "nominal_amount"] = 'null'
                nominalsdf.loc[index, "Unit"] = 'null'
                nominalsdf.loc[index, "actualsnull"] = 'null'
                itemcount+=1
                pass
            else:
                #calculate reagent amounts from formula
                reagentnum = str(reagentname.split('t')[1])
                nominalamount = (target_final_volume[reagentname]/1000/1000 * \
                    rdict[reagentnum].concs['conc_item%s' %(itemcount)] * \
                    float(chemdf.loc["%s" %chemabbr, "Molecular Weight (g/mol)"])
                    ).round(2)
                nominalsdf.loc[index, "nominal_amount"] =  nominalamount
                nominalsdf.loc[index, "Unit"] = 'gram'
                itemcount+=1
        if itemcount == (maxreagentchemicals+1):
            if len(formulavollist) > 0:
                nominalsdf.loc[finalvolindex, "nominal_amount"] = sum(formulavollist)
                nominalsdf.loc[finalvolindex, "Unit"] = 'milliliter'
            else: 
                nominalsdf.loc[finalvolindex, "nominal_amount"] = formulavol
                nominalsdf.loc[finalvolindex, "Unit"] = 'null'
                nominalsdf.loc[finalvolindex, "actualsnull"] = 'null'
            modlog.info((reagentname, "formula calculation complete"))
    nominalsdf.sort_index(inplace=True)
    return nominalsdf


def build_nominals_v1(rdict,
                      chemicalnamedf,
                      target_final_volume_dict,
                      liquidlist,
                      maxreagentchemicals,
                      chemdf):
    ''' calculate the mass of each chemical return dataframe

    Uses model 1 of the density calculation to get a better approximation
    for the contribution of solids to the final volume 
    TODO: write out nominal molarity to google sheets, see issue#52
    TODO: ensure column integrity of read in chemical dataframe

    :param chemdf:  Chemical data frame from google drive.
    :returns: a dataframe sized for export to version 2.x interface
    '''
    nominalsdf = pd.DataFrame()
    itemcount = 1
    chemicalnamedf.sort_index(inplace=True)
    reagentname = []
    for index, row in chemicalnamedf.iterrows():
        reagent_name_updater = row['reagentnames']
        if reagentname != reagent_name_updater:
            reagentname = row['reagentnames']
            reagentnum = str(reagentname.split('t')[1])
            total_remaining_volume = target_final_volume_dict[reagentname] / 1000 / 1000
            target_final_volume = target_final_volume_dict[reagentname] / 1000 / 1000

        chemabbr = row['chemabbr']
        # First iteration should always lead with this string (formatting)
        if row['chemabbr'] == 'Final Volume = ':
            formulavollist = []
            formulavol = 'null'
            itemcount = 1
            finalvolindex = index
        else:
            # stock solutions should be summed for final total volume
            # Returns nulls to the dataframe where no chemicals / information is expected
            if chemabbr == 'null':
                nominalsdf.loc[index, "nominal_amount"] = 'null'
                nominalsdf.loc[index, "Unit"] = 'null'
                nominalsdf.loc[index, "actualsnull"] = 'null'
                itemcount+=1
                pass
            else:
                # If the chemical being considered is the final the remaining volume is assigned
                if rdict[reagentnum].chemicals[-1] == chemabbr:
                    nominalsdf.loc[index, "nominal_amount"] = (total_remaining_volume * 1000).round(2)
                    nominalsdf.loc[index, "Unit"] = 'milliliter'
                    itemcount+=1
                elif chemabbr in liquidlist or chemabbr == 'FAH':  # todo dejank
                    myvariable = rdict[reagentnum].concs['conc_item%s' %(itemcount)]
                    needed_mol = target_final_volume * rdict[reagentnum].concs['conc_item%s' %(itemcount)]
                    chemical_volume = needed_mol * float(chemdf.loc["%s" %chemabbr, "Molecular Weight (g/mol)"])\
                                      / float(chemdf.loc["%s" %chemabbr, "Density            (g/mL)"])
                    total_remaining_volume = total_remaining_volume - chemical_volume / 1000
                    nominalsdf.loc[index, "nominal_amount"] =  chemical_volume.round(2)
                    nominalsdf.loc[index, "Unit"] = 'milliliter'
                    itemcount+=1

                else:
                    myvariable = rdict[reagentnum].concs['conc_item%s' %(itemcount)]
                    needed_mol = target_final_volume * (rdict[reagentnum].concs['conc_item%s' %(itemcount)])
                    chemical_mass_g = needed_mol * float(chemdf.loc["%s" %chemabbr, "Molecular Weight (g/mol)"])
                    chemical_volume = needed_mol * float(chemdf.loc["%s" %chemabbr, "Molecular Weight (g/mol)"])\
                                      / float(chemdf.loc["%s" %chemabbr, "Density            (g/mL)"])
                    total_remaining_volume = total_remaining_volume - chemical_volume / 1000
                    nominalsdf.loc[index, "nominal_amount"] =  chemical_mass_g.round(2)
                    nominalsdf.loc[index, "Unit"] = 'gram'
                    itemcount+=1

        if itemcount == (maxreagentchemicals+1):
            if total_remaining_volume == target_final_volume:
                nominalsdf.loc[finalvolindex, "nominal_amount"] = 'null'
                nominalsdf.loc[finalvolindex, "Unit"] = 'null'
                nominalsdf.loc[finalvolindex, "actualsnull"] = 'null'
            else:
                nominalsdf.loc[finalvolindex, "nominal_amount"] = (target_final_volume * 1000).round(2)
                nominalsdf.loc[finalvolindex, "Unit"] = 'milliliter'
            modlog.info((reagentname, "formula calculation complete"))
    nominalsdf.sort_index(inplace=True)
    return nominalsdf

def build_chemical_names_df(rdict, maxreagentchemicals):
    """generates a dataframe of chemical names for reagent interface

    :param chemdf:  Chemical data frame from google drive.  

    :returns: a dataframe sized for export to version:: 3.0 interface
    """
    chemicalnamelist = []
    reagentnamelist = []
    holdreagentnum = 1
    for reagentnum in sorted(rdict.keys()):
        #ensure any reagents not used have placeholders
        while int(reagentnum) > holdreagentnum:
            chemicalnamelist.append('Final Volume = ')
            chemicalnamelist.extend(['null'] * maxreagentchemicals)
            maxinterfaceslots = maxreagentchemicals + 1
            reagentnamelist.extend(['Reagent%s' %holdreagentnum] * maxinterfaceslots)
            holdreagentnum += 1
        else:
            count = 0
            holdreagentnum = int(reagentnum)+1
            chemicalnamelist.append('Final Volume = ')
            reagentnamelist.append('Reagent%s' %reagentnum)
            for chemical in rdict[reagentnum].chemicals:
                chemicalnamelist.append(chemical)
                reagentnamelist.append('Reagent%s' %reagentnum)
                count += 1
            while count < maxreagentchemicals:
                chemicalnamelist.append('null')
                reagentnamelist.append('Reagent%s' %reagentnum)
                count += 1
    chemicalnamedf = pd.DataFrame(chemicalnamelist, columns=['chemabbr'])
    reagentnamedf = pd.DataFrame(reagentnamelist, columns=['reagentnames'])
    chemicalnamedf = pd.concat([chemicalnamedf, reagentnamedf], axis=1)
    return chemicalnamedf

def build_reagent_spec_df(rxndict, vardict, erdf, rdict, chemdf):
    """Build the dataframe for the bottom portion of the reagent preparation_interface

    :param rxndict:
    :param vardict:
    :param erdf:
    :param rdict:
    :param chemdf:
    :return:
    """
    modlog.info('Starting reagent interface upload')
    chemical_names_df = build_chemical_names_df(rdict, lab_safeget(config.lab_vars, globals.get_lab(), 'maxreagentchemicals'))
    reagent_target_volumes = get_reagent_target_volumes(erdf, rxndict['reagent_dead_volume'] * 1000)
    nominals_df = build_nominals_v1(rdict, chemical_names_df, reagent_target_volumes,
                                    vardict['solventlist'], lab_safeget(config.lab_vars, globals.get_lab(), 'maxreagentchemicals'), chemdf)
    reagent_spec_df = pd.concat([chemical_names_df, nominals_df], axis=1)
    return reagent_spec_df


def upload_reagent_interface(rxndict, vardict, rdict, finalexportdf, gc, uid):
    sheet = gc.open_by_key(uid).sheet1
    upload_aliased_cells(sheet)
    upload_reagent_prep_info(rdict, sheet)
    upload_run_information(rxndict, vardict, sheet)
    upload_reagent_specifications(finalexportdf, sheet)


def upload_aliased_cells(sheet):
    """Upload cells containing reagent alias to the reagent interface"""

    # Value used in googlesheet as placeholder for reagent alias
    cell_alias_pat = '<Reagent>'

    # Cells in googlesheet containing reagent alias:
    aliased_cells = ['C1', 'C2']

    # Reagent<i> cells at bottom of sheet (all in col A, regularly spaced):
    aliased_cells.extend(_get_reagent_header_cells('A'))

    reagent_alias = lab_safeget(config.lab_vars, globals.get_lab(), 'reagent_alias')
    for cell in aliased_cells:
        current_value = sheet.acell(cell).value
        new_value = current_value.replace(cell_alias_pat, reagent_alias)
        sheet.update_acell(cell, new_value)

    return


def upload_run_information(rxndict, vardict, sheet):
    sheet.update_acell('B2', rxndict['date']) #row, column, replacement in experimental data entry form
    sheet.update_acell('B3', rxndict['time'])
    sheet.update_acell('B4', rxndict['lab'])
    sheet.update_acell('B6', rxndict['RunID'])
    sheet.update_acell('B7', rxndict['ExpWorkflowVer'])
    sheet.update_acell('B8', config.RoboVersion)
    sheet.update_acell('B9', rxndict['challengeproblem'])

    # Notes section - blank values as default
    sheet.update_acell('B12', 'null')
    sheet.update_acell('B13', 'null')
    sheet.update_acell('B14', 'null')

def upload_reagent_specifications(finalexportdf, sheet):
    """upload rxndict, finalexportdf to gc target, returns the used gsheets object

    :param finalexportdf: datframe containing pre-ordered and normalized abbreviations, nomial amounts and units \n
    :type finalexportdf: pandas dataframe object \n 
    :param sheet: google sheet string indicating the target file for uploading the finalexport df \n
    :type sheet: str \n

    :return: NONE - creates online object in run directory
    """

    # get lab-specific config variables
    reagent_interface_amount_startrow = lab_safeget(config.lab_vars, globals.get_lab(), 'reagent_interface_amount_startrow')
    max_reagents = lab_safeget(config.lab_vars, globals.get_lab(), 'max_reagents')

    update_sheet_column(sheet, finalexportdf['chemabbr'],
                        col_index='B', start_row=reagent_interface_amount_startrow)
    update_sheet_column(sheet, finalexportdf['nominal_amount'],
                        col_index='C', start_row=reagent_interface_amount_startrow)
    update_sheet_column(sheet, finalexportdf['Unit'],
                        col_index='E', start_row=reagent_interface_amount_startrow)

    # add in actual amount column for specified reagents
    # only adds null to rows where there is no chemical
    nulls = finalexportdf['actualsnull'].values.tolist()
    nulls = [val if val == 'null' else '' for val in nulls]
    update_sheet_column(sheet, nulls,
                        col_index='D', start_row=reagent_interface_amount_startrow)

    # add nulls to actual amount column for unspecified reagents
    null_start = reagent_interface_amount_startrow + len(finalexportdf)
    maxreagentchemicals = lab_safeget(config.lab_vars, globals.get_lab(), 'maxreagentchemicals')
    num_nulls = (max_reagents - len(finalexportdf.reagentnames.unique())) * (maxreagentchemicals + 1)
    nulls = ['null'] * num_nulls
   # update_sheet_column(sheet, nulls, col_index='D', start_row=null_start)

def upload_reagent_prep_info(rdict, sheetobject):
    uploadtarget = sheetobject.range('D3:F11')
    uploadlist = []
    reagentcount = 1
    for reagentnum, reagentobject in rdict.items():
        while int(reagentnum) > reagentcount:
            uploadlist.extend(['null']*3) #3 setby number of steps in reagent prep (see if section below)
            reagentcount += 1
        if int(reagentnum) == reagentcount:
            uploadlist.append(reagentobject.preptemperature)
            uploadlist.append(reagentobject.prepstirrate)
            uploadlist.append(reagentobject.prepduration)
            reagentcount += 1
    count = 0
    for cell in uploadtarget:
        try:
            cell.value = uploadlist[count]
            count += 1  
        except:
            count += 1
    sheetobject.update_cells(uploadtarget)

    # Upload prerxntemps
    prerxn_temp_cells = _get_reagent_header_cells(column='H')
    num_reagents = int(lab_safeget(config.lab_vars, globals.get_lab(), 'max_reagents')) + 1
    for i in range(1, num_reagents):
        try:
            payload = rdict[str(i)].prerxntemp
        except KeyError:
            payload = 'null'

        sheetobject.update_acell(prerxn_temp_cells[i-1], payload)


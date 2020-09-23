# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Copyright (c) 2020 by Patrick Rainsberry.                                   ~
#  :license: Apache2, see LICENSE for more details.                            ~
#  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  SampleCommand2.py                                                           ~
#  This file is a component of Project-Archiver.                               ~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import os

import adsk.core
import adsk.fusion
import adsk.cam

import apper
from apper import AppObjects

import config

SKIPPED_FILES = []


def export_folder(root_folder, output_folder, file_types, write_version, name_option, folder_preserve):
    ao = AppObjects()

    for folder in root_folder.dataFolders:

        if folder_preserve:
            new_folder = os.path.join(output_folder, folder.name, "")

            if not os.path.exists(new_folder):
                os.makedirs(new_folder)
        else:
            new_folder = output_folder

        export_folder(folder, new_folder, file_types, write_version, name_option, folder_preserve)

    for file in root_folder.dataFiles:
        if file.fileExtension == "f3d":
            open_doc(file)
            try:
                output_name = get_name(write_version, name_option)
                export_active_doc(output_folder, file_types, output_name)

            # TODO add handling
            except ValueError as e:
                ao.ui.messageBox(str(e))

            except AttributeError as e:
                ao.ui.messageBox(str(e))
                break


def open_doc(data_file):
    app = adsk.core.Application.get()

    try:
        document = app.documents.open(data_file, True)
        if document is not None:
            document.activate()
    except:
        pass
        # TODO add handling


def export_active_doc(folder, file_types, output_name):
    global SKIPPED_FILES

    ao = AppObjects()
    export_mgr = ao.export_manager

    export_functions = [export_mgr.createIGESExportOptions,
                        export_mgr.createSTEPExportOptions,
                        export_mgr.createSATExportOptions,
                        export_mgr.createSMTExportOptions,
                        export_mgr.createFusionArchiveExportOptions,
                        export_mgr.createSTLExportOptions]
    export_extensions = ['.igs', '.step', '.sat', '.smt', '.f3d', '.stl']

    for i in range(file_types.count-2):

        if file_types.item(i).isSelected:
            export_name = folder + output_name + export_extensions[i]
            export_name = dup_check(export_name)
            export_options = export_functions[i](export_name)
            export_mgr.execute(export_options)

    if file_types.item(file_types.count - 2).isSelected:

        if ao.document.allDocumentReferences.count > 0:
            SKIPPED_FILES.append(ao.document.name)

        else:
            export_name = folder + output_name + '.f3d'
            export_name = dup_check(export_name)
            export_options = export_mgr.createFusionArchiveExportOptions(export_name)
            export_mgr.execute(export_options)

    if file_types.item(file_types.count - 1).isSelected:
        stl_export_name = folder + output_name + '.stl'
        stl_options = export_mgr.createSTLExportOptions(ao.design.rootComponent, stl_export_name)
        export_mgr.execute(stl_options)


def dup_check(name):
    if os.path.exists(name):
        base, ext = os.path.splitext(name)
        base += '-dup'
        name = base + ext
        dup_check(name)
    return name


def get_name(write_version, option):
    ao = AppObjects()
    output_name = ''

    if option == 'Document Name':

        doc_name = ao.app.activeDocument.name

        if not write_version:
            doc_name = doc_name[:doc_name.rfind(' v')]
        output_name = doc_name

    elif option == 'Description':
        output_name = ao.root_comp.description

    elif option == 'Part Number':
        output_name = ao.root_comp.partNumber

    else:
        raise ValueError('Something strange happened')

    return output_name


def update_name_inputs(command_inputs, selection):
    command_inputs.itemById('write_version').isVisible = False

    if selection == 'Document Name':
        command_inputs.itemById('write_version').isVisible = True


class ExportCommand(apper.Fusion360CommandBase):

    def on_input_changed(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs,
                         changed_input, input_values):
        if changed_input.id == 'name_option_id':
            update_name_inputs(inputs, changed_input.selectedItem.name)

    def on_execute(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs, args, input_values):
        global SKIPPED_FILES
        ao = AppObjects()

        output_folder = input_values['output_folder']
        folder_preserve = input_values['folder_preserve_id']

        # TODO broken?????
        file_types = inputs.itemById('file_types_input').listItems

        write_version = input_values['write_version']
        name_option = input_values['name_option_id']
        root_folder = ao.app.data.activeProject.rootFolder

        # Make sure we have a folder not a file
        if not output_folder.endswith(os.path.sep):
            output_folder += os.path.sep

        # Create the base folder for this output if doesn't exist
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        export_folder(root_folder, output_folder, file_types, write_version, name_option, folder_preserve)

        if len(SKIPPED_FILES) > 0:
            ao.ui.messageBox(
                "The following files contained external references and could not be exported as f3d's: {}".format(
                    SKIPPED_FILES
                )
            )

        close_command = ao.ui.commandDefinitions.itemById(self.fusion_app.command_id_from_name(config.close_cmd_id))
        close_command.execute()

    def on_create(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs):
        global SKIPPED_FILES
        SKIPPED_FILES.clear()
        default_dir = apper.get_default_dir(config.app_name)

        inputs.addStringValueInput('output_folder', 'Output Folder:', default_dir)

        drop_input_list = inputs.addDropDownCommandInput('file_types_input', 'Export Types',
                                                         adsk.core.DropDownStyles.CheckBoxDropDownStyle)
        drop_input_list = drop_input_list.listItems
        drop_input_list.add('IGES', False)
        drop_input_list.add('STEP', True)
        drop_input_list.add('SAT', False)
        drop_input_list.add('SMT', False)
        drop_input_list.add('F3D', False)
        drop_input_list.add('STL', False)

        name_option_group = inputs.addDropDownCommandInput('name_option_id', 'File Name Option',
                                                                   adsk.core.DropDownStyles.TextListDropDownStyle)
        name_option_group.listItems.add('Document Name', True)
        name_option_group.listItems.add('Description', False)
        name_option_group.listItems.add('Part Number', False)
        name_option_group.isVisible = True

        preserve_input = inputs.addBoolValueInput('folder_preserve_id', 'Preserve folder structure?', True, '', True)
        preserve_input.isVisible = True

        version_input = inputs.addBoolValueInput('write_version', 'Write versions to output file names?', True, '', False)
        version_input.isVisible = False

        update_name_inputs(inputs, 'Document Name')

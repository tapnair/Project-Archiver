#  Copyright (c) 2020 by Patrick Rainsberry.
#  :license: Apache2, see LICENSE for more details.

# The export dialog shared by the export commands.

import html
import os

import adsk.core

from ... import config
from . import export_utils
from .file_utils import get_default_dir, sanitize_name
from .log_utils import LOG_FILE_NAME

app = adsk.core.Application.get()
ui = app.userInterface


def add_export_inputs(inputs: adsk.core.CommandInputs, location_label: str, location: str, project_name: str):
    """Add the export dialog's inputs.

    location_label and location describe what will be exported, such as the project name, and are
    shown read-only at the top since they come from the Data Panel.
    """
    export_utils.clear_export_messages()

    inputs.addTextBoxCommandInput('export_location', location_label, html.escape(location), 1, True)

    # Each project gets its own folder by default so archives of different projects don't mix
    default_dir = os.path.join(get_default_dir(config.user_dir_name), sanitize_name(project_name), '')
    inputs.addStringValueInput('output_folder', 'Output folder:', default_dir)

    browse_input = inputs.addBoolValueInput('browse_output_folder', 'Browse', False, '', False)
    browse_input.text = 'Browse...'
    browse_input.tooltip = 'Choose the folder to export to'

    file_types_input = inputs.addDropDownCommandInput('file_types_input', 'Design export types',
                                                      adsk.core.DropDownStyles.CheckBoxDropDownStyle)
    file_types_list = file_types_input.listItems
    file_types_list.add('IGES', False)
    file_types_list.add('STEP', True)
    file_types_list.add('SAT', False)
    file_types_list.add('SMT', False)
    file_types_list.add('F3D', False)
    file_types_list.add('STL', False)

    # Only offered when this version of Fusion supports exporting drawings
    drawing_types_input = inputs.addDropDownCommandInput('drawing_types_input', 'Drawing export types',
                                                         adsk.core.DropDownStyles.CheckBoxDropDownStyle)
    drawing_types_list = drawing_types_input.listItems
    drawing_types_list.add('PDF', True)
    drawing_types_list.add('DXF', False)
    drawing_types_list.add('DWG', False)
    drawing_types_input.isVisible = export_utils.HAS_DRAWING

    # Only offered when this version of Fusion supports exporting electronics documents
    electronics_input = inputs.addBoolValueInput('export_electronics', 'Export electronics documents?', True, '', True)
    electronics_input.tooltip = 'Exports boards, schematics and libraries as EAGLE .brd, .sch and .lbr files'
    electronics_input.isVisible = export_utils.HAS_ELECTRON

    name_option_input = inputs.addDropDownCommandInput('name_option_id', 'File name option',
                                                       adsk.core.DropDownStyles.TextListDropDownStyle)
    name_option_input.listItems.add('Document name', True)
    name_option_input.listItems.add('Description', False)
    name_option_input.listItems.add('Part number', False)
    name_option_input.isVisible = True

    # Options most users don't need to change, collapsed by default
    advanced_group = inputs.addGroupCommandInput('advanced_options', 'Advanced options')
    advanced_group.isExpanded = False
    advanced_inputs = advanced_group.children

    version_input = advanced_inputs.addBoolValueInput('write_version', 'Write versions to output file names?', True, '',
                                                      False)

    all_versions_input = advanced_inputs.addBoolValueInput('all_versions', 'Export all versions?', True, '', False)
    all_versions_input.tooltip = ('Export every version of each design and drawing, not only the latest. '
                                  'Output file names always include the version.')

    preserve_input = advanced_inputs.addBoolValueInput('folder_preserve_id', 'Preserve folder structure?', True, '',
                                                       True)
    preserve_input.isVisible = True

    existing_files_input = advanced_inputs.addDropDownCommandInput('existing_files', 'Existing files',
                                                                   adsk.core.DropDownStyles.TextListDropDownStyle)
    for option in export_utils.EXISTING_FILES_OPTIONS:
        existing_files_input.listItems.add(option, option == export_utils.EXISTING_FILES_RENAME)
    existing_files_input.tooltip = 'What to do when a file with the same name is already in the output folder'

    skip_used_input = advanced_inputs.addBoolValueInput('skip_used_designs', 'Skip designs used by other designs?',
                                                        True, '', False)
    skip_used_input.tooltip = ('Only export designs that aren\'t inserted into another design, '
                               'such as top-level assemblies')

    hidden_input = advanced_inputs.addBoolValueInput('include_hidden', 'Include hidden bodies and components?', True,
                                                     '', False)
    hidden_input.tooltip = ('Show every hidden body and component at every level before exporting, so they\'re '
                            'included. F3D files always include them, hidden as in the design.')

    text_commands_input = advanced_inputs.addBoolValueInput('open_text_commands', 'Open Text Commands?', True, '',
                                                            False)
    text_commands_input.tooltip = ('Open the Text Commands window to see each file as it\'s exported. '
                                   'The same details are written to {} in the output folder.'.format(LOG_FILE_NAME))



def run_export(inputs: adsk.core.CommandInputs, data_folder: adsk.core.DataFolder = None):
    """Export using the values in the dialog, then close the documents that were opened for export.

    Exports the whole active project, or data_folder and its subfolders if given.
    Close All shows the export summary when it finishes.
    """
    output_folder_input: adsk.core.StringValueCommandInput = inputs.itemById('output_folder')
    file_types_input: adsk.core.DropDownCommandInput = inputs.itemById('file_types_input')
    drawing_types_input: adsk.core.DropDownCommandInput = inputs.itemById('drawing_types_input')
    name_option_input: adsk.core.DropDownCommandInput = inputs.itemById('name_option_id')
    preserve_input: adsk.core.BoolValueCommandInput = inputs.itemById('folder_preserve_id')
    version_input: adsk.core.BoolValueCommandInput = inputs.itemById('write_version')
    electronics_input: adsk.core.BoolValueCommandInput = inputs.itemById('export_electronics')
    existing_files_input: adsk.core.DropDownCommandInput = inputs.itemById('existing_files')
    skip_used_input: adsk.core.BoolValueCommandInput = inputs.itemById('skip_used_designs')
    text_commands_input: adsk.core.BoolValueCommandInput = inputs.itemById('open_text_commands')
    hidden_input: adsk.core.BoolValueCommandInput = inputs.itemById('include_hidden')
    all_versions_input: adsk.core.BoolValueCommandInput = inputs.itemById('all_versions')

    if text_commands_input.value:
        text_commands = ui.palettes.itemById('TextCommands')
        if text_commands:
            text_commands.isVisible = True

    export_utils.export_project(
        output_folder_input.value,
        file_types_input.listItems,
        drawing_types_input.listItems,
        version_input.value,
        name_option_input.selectedItem.name,
        preserve_input.value,
        electronics_input.value,
        existing_files_input.selectedItem.name,
        skip_used_input.value,
        hidden_input.value,
        data_folder,
        all_versions_input.value
    )

    close_command = ui.commandDefinitions.itemById(config.close_all_cmd_id)
    close_command.execute()


def handle_input_changed(changed_input: adsk.core.CommandInput, inputs: adsk.core.CommandInputs):
    """Update the dialog when one of its inputs changes."""
    # For an input inside a group, inputs only holds the group's inputs, so use the whole dialog's
    inputs = changed_input.parentCommand.commandInputs

    if changed_input.id == 'all_versions':
        update_version_input(inputs)

    elif changed_input.id == 'browse_output_folder':
        output_folder_input: adsk.core.StringValueCommandInput = inputs.itemById('output_folder')
        folder = browse_for_folder(output_folder_input.value)
        if folder:
            output_folder_input.value = os.path.join(folder, '')


def inputs_are_valid(inputs: adsk.core.CommandInputs) -> bool:
    """Return True if there is something to export, which enables the OK button."""
    file_types_input: adsk.core.DropDownCommandInput = inputs.itemById('file_types_input')
    drawing_types_input: adsk.core.DropDownCommandInput = inputs.itemById('drawing_types_input')
    electronics_input: adsk.core.BoolValueCommandInput = inputs.itemById('export_electronics')

    return (export_utils.any_type_selected(file_types_input.listItems)
            or (drawing_types_input.isVisible and export_utils.any_type_selected(drawing_types_input.listItems))
            or (electronics_input.isVisible and electronics_input.value))


def browse_for_folder(current_folder: str) -> str:
    """Show a folder picker starting at the current output folder, and return the chosen folder or ''."""
    folder_dialog = ui.createFolderDialog()
    folder_dialog.title = 'Choose the folder to export to'

    # Start in the current output folder, or the closest parent that exists
    initial_folder = current_folder
    while initial_folder and not os.path.isdir(initial_folder):
        parent = os.path.dirname(initial_folder.rstrip(os.path.sep))
        if parent == initial_folder:
            break
        initial_folder = parent
    if initial_folder:
        folder_dialog.initialDirectory = initial_folder

    if folder_dialog.showDialog() == adsk.core.DialogResults.DialogOK:
        return folder_dialog.folder

    return ''


def update_version_input(command_inputs: adsk.core.CommandInputs):
    """Exporting all versions always writes versions to the file names, so turn that option on
    and don't let it be changed."""
    version_input: adsk.core.BoolValueCommandInput = command_inputs.itemById('write_version')
    all_versions_input: adsk.core.BoolValueCommandInput = command_inputs.itemById('all_versions')

    version_input.isEnabled = not all_versions_input.value
    if all_versions_input.value:
        version_input.value = True

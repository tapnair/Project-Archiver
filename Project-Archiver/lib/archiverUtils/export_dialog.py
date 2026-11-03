#  Copyright (c) 2019-2026 Patrick Rainsberry
#  Licensed under the Apache License, Version 2.0. See LICENSE for details.

"""The export dialog shared by the Export active project and Export active folder commands.

The commands call add_export_inputs when the dialog is created, handle_input_changed and
inputs_are_valid from their dialog events, and run_export when the user clicks OK.
"""

import html
import os

import adsk.core

from ... import config
from . import exporter
from .export_options import (DESIGN_EXTENSIONS, DRAWING_EXPORTS, EXISTING_FILES_OPTIONS, EXISTING_FILES_SKIP,
                             NAME_DOCUMENT, NAME_OPTIONS, ExportOptions)
from .file_utils import get_home_folder, get_output_folder, sanitize_name
from .log_utils import LOG_FILE_NAME

app = adsk.core.Application.get()
ui = app.userInterface

# Export types checked when the dialog opens
DEFAULT_DESIGN_TYPES = {'STEP'}
DEFAULT_DRAWING_TYPES = {'PDF'}

# Shown in the output path preview in place of the project name when exporting a hub
PROJECT_NAME_PLACEHOLDER = '<project name>'

# Rows shown in the hub export's projects table before it scrolls
PROJECT_ROWS_SHOWN = 10

# The hub, project and folder the open dialog exports, for the output path preview
preview_location = {}


def add_export_inputs(inputs: adsk.core.CommandInputs, location_label: str, location: str, hub_name: str,
                      project_name: str = None, folder_path=(), projects=None):
    """Add the export dialog's inputs.

    location_label and location describe what will be exported, such as the project name, and are
    shown read-only at the top since they come from the Data Panel. hub_name, project_name and
    folder_path are used to preview where the files go. When exporting a hub, project_name is None
    and projects is the hub's projects, offered in a dropdown with all of them checked.
    """
    preview_location.clear()
    preview_location.update(hub_name=hub_name, project_name=project_name, folder_path=list(folder_path))

    inputs.addTextBoxCommandInput('export_location', location_label, html.escape(location), 1, True)

    if projects is not None:
        add_projects_table(inputs, projects)

    # The output folder is a root: files go under <root>/<hub>/<project>/, whichever command exports them
    inputs.addStringValueInput('output_folder', 'Output folder:', get_home_folder(config.USER_DIR_NAME))

    browse_input = inputs.addBoolValueInput('browse_output_folder', 'Browse', False, '', False)
    browse_input.text = 'Browse...'
    browse_input.tooltip = 'Choose the folder to export to'

    # Shows the full path the files go to, updated as the output folder or folder structure option changes
    preview_input = inputs.addTextBoxCommandInput('output_preview', '', '', 1, True)
    preview_input.isFullWidth = True

    design_types_input = inputs.addDropDownCommandInput('design_types', 'Design export types',
                                                        adsk.core.DropDownStyles.CheckBoxDropDownStyle)
    for type_name in DESIGN_EXTENSIONS:
        design_types_input.listItems.add(type_name, type_name in DEFAULT_DESIGN_TYPES)

    # Only offered when this version of Fusion supports exporting drawings
    drawing_types_input = inputs.addDropDownCommandInput('drawing_types', 'Drawing export types',
                                                         adsk.core.DropDownStyles.CheckBoxDropDownStyle)
    for type_name in DRAWING_EXPORTS:
        drawing_types_input.listItems.add(type_name, type_name in DEFAULT_DRAWING_TYPES)
    drawing_types_input.isVisible = exporter.HAS_DRAWING

    # Only offered when this version of Fusion supports exporting electronics documents
    electronics_input = inputs.addBoolValueInput('export_electronics', 'Export electronics documents?', True, '', True)
    electronics_input.tooltip = 'Exports boards, schematics and libraries as EAGLE .brd, .sch and .lbr files'
    electronics_input.isVisible = exporter.HAS_ELECTRON

    name_option_input = inputs.addDropDownCommandInput('name_option', 'File name option',
                                                       adsk.core.DropDownStyles.TextListDropDownStyle)
    for option in NAME_OPTIONS:
        name_option_input.listItems.add(option, option == NAME_DOCUMENT)

    # Options most users don't need to change, collapsed by default
    advanced_group = inputs.addGroupCommandInput('advanced_options', 'Advanced options')
    advanced_group.isExpanded = False
    advanced_inputs = advanced_group.children

    advanced_inputs.addBoolValueInput('write_version', 'Write versions to output file names?', True, '', False)

    all_versions_input = advanced_inputs.addBoolValueInput('all_versions', 'Export all versions?', True, '', False)
    all_versions_input.tooltip = ('Export every version of each design and drawing, not only the latest. '
                                  'Output file names always include the version.')

    advanced_inputs.addBoolValueInput('preserve_folders', 'Preserve folder structure?', True, '', True)

    existing_files_input = advanced_inputs.addDropDownCommandInput('existing_files', 'Existing files',
                                                                   adsk.core.DropDownStyles.TextListDropDownStyle)
    for option in EXISTING_FILES_OPTIONS:
        existing_files_input.listItems.add(option, option == EXISTING_FILES_SKIP)
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
                                   'The same details are written to {} in each project\'s folder.'.format(LOG_FILE_NAME))

    update_output_preview(inputs)


def add_projects_table(inputs: adsk.core.CommandInputs, projects):
    """Add how many projects are selected, and a collapsed group with a table to choose them.

    The table has a check box for each project, all checked, and Select all and Select none
    buttons. A table scrolls when it has more rows than it shows, which a check box dropdown
    doesn't, so a hub with many projects still fits in the dialog.
    """
    inputs.addTextBoxCommandInput('projects_selected', 'Projects:', '', 1, True)

    group = inputs.addGroupCommandInput('project_selection', 'Select projects')
    group.isExpanded = False

    table = group.children.addTableCommandInput('projects', 'Projects', 2, '1:8')
    table.maximumVisibleRows = PROJECT_ROWS_SHOWN
    table.tooltip = 'The projects to export. All the hub\'s projects are checked to start with.'
    table_inputs = table.commandInputs

    for row, project in enumerate(projects):
        check_box = table_inputs.addBoolValueInput('project_{}'.format(row), '', True, '', True)
        name = table_inputs.addTextBoxCommandInput('project_name_{}'.format(row), '', html.escape(project.name), 1,
                                                   True)
        table.addCommandInput(check_box, row, 0)
        table.addCommandInput(name, row, 1)

    for button_id, text in (('select_all_projects', 'Select all'), ('select_no_projects', 'Select none')):
        button = table_inputs.addBoolValueInput(button_id, text, False, '', False)
        button.text = text
        table.addToolbarCommandInput(button)

    update_projects_selected(inputs)


def get_selected_project_rows(inputs: adsk.core.CommandInputs):
    """Return the row numbers of the projects checked in the projects table."""
    table: adsk.core.TableCommandInput = inputs.itemById('projects')
    return [row for row in range(table.rowCount) if inputs.itemById('project_{}'.format(row)).value]


def update_projects_selected(inputs: adsk.core.CommandInputs):
    """Show how many projects are checked."""
    table: adsk.core.TableCommandInput = inputs.itemById('projects')
    inputs.itemById('projects_selected').text = '{} of {} selected'.format(
        len(get_selected_project_rows(inputs)), table.rowCount)


def get_export_options(inputs: adsk.core.CommandInputs, data_folder: adsk.core.DataFolder = None) -> ExportOptions:
    """Read the dialog's inputs into ExportOptions."""
    def value(input_id):
        return inputs.itemById(input_id).value

    def selected(input_id):
        list_items = inputs.itemById(input_id).listItems
        return [list_items.item(i).name for i in range(list_items.count) if list_items.item(i).isSelected]

    def selected_one(input_id):
        return inputs.itemById(input_id).selectedItem.name

    return ExportOptions(
        output_folder=value('output_folder'),
        design_types=selected('design_types'),
        drawing_types=selected('drawing_types') if exporter.HAS_DRAWING else [],
        export_electronics=value('export_electronics'),
        name_option=selected_one('name_option'),
        write_version=value('write_version'),
        preserve_folders=value('preserve_folders'),
        existing_files=selected_one('existing_files'),
        skip_used_designs=value('skip_used_designs'),
        include_hidden=value('include_hidden'),
        all_versions=value('all_versions'),
        data_folder=data_folder,
    )


def run_export(inputs: adsk.core.CommandInputs, data_folder: adsk.core.DataFolder = None):
    """Export using the values in the dialog, then close the documents that were opened for export.

    Exports the whole active project, or data_folder and its subfolders if given.
    Close all documents shows the export summary when it finishes.
    """
    if inputs.itemById('open_text_commands').value:
        text_commands = ui.palettes.itemById('TextCommands')
        if text_commands:
            text_commands.isVisible = True

    exporter.export(get_export_options(inputs, data_folder))

    close_command = ui.commandDefinitions.itemById(config.CLOSE_ALL_CMD_ID)
    close_command.execute()


def run_hub_export(inputs: adsk.core.CommandInputs, projects):
    """Export the projects checked in the dialog, then close the documents that were opened for export.

    projects is the list the Projects dropdown was built from, in the same order.
    """
    if inputs.itemById('open_text_commands').value:
        text_commands = ui.palettes.itemById('TextCommands')
        if text_commands:
            text_commands.isVisible = True

    selected_projects = [projects[row] for row in get_selected_project_rows(inputs)]
    exporter.export_hub(get_export_options(inputs), selected_projects)

    close_command = ui.commandDefinitions.itemById(config.CLOSE_ALL_CMD_ID)
    close_command.execute()


def handle_input_changed(changed_input: adsk.core.CommandInput):
    """Update the dialog when one of its inputs changes."""
    # For an input inside a group, the event's inputs only hold the group's inputs, so use the whole dialog's
    inputs = changed_input.parentCommand.commandInputs

    if changed_input.id == 'all_versions':
        update_version_input(inputs)

    elif changed_input.id == 'browse_output_folder':
        output_folder_input: adsk.core.StringValueCommandInput = inputs.itemById('output_folder')
        folder = browse_for_folder(output_folder_input.value)
        if folder:
            output_folder_input.value = os.path.join(folder, '')
        update_output_preview(inputs)

    elif changed_input.id in ('output_folder', 'preserve_folders'):
        update_output_preview(inputs)

    elif changed_input.id in ('select_all_projects', 'select_no_projects'):
        table: adsk.core.TableCommandInput = inputs.itemById('projects')
        for row in range(table.rowCount):
            inputs.itemById('project_{}'.format(row)).value = changed_input.id == 'select_all_projects'
        update_projects_selected(inputs)

    elif changed_input.id.startswith('project_'):
        update_projects_selected(inputs)


def update_output_preview(inputs: adsk.core.CommandInputs):
    """Show the full path the files will go to, below the output folder."""
    location = preview_location
    root = inputs.itemById('output_folder').value
    preserve_folders = inputs.itemById('preserve_folders').value

    if location['project_name'] is None:
        path = os.path.join(get_output_folder(root, location['hub_name'], ''), PROJECT_NAME_PLACEHOLDER, '')
    else:
        path = get_output_folder(root, location['hub_name'], location['project_name'], location['folder_path'],
                                 preserve_folders)

    inputs.itemById('output_preview').formattedText = '<i>Files go to: {}</i>'.format(html.escape(path))


def inputs_are_valid(inputs: adsk.core.CommandInputs) -> bool:
    """Return True if there is something to export, which enables the OK button."""
    if inputs.itemById('projects') is not None and not get_selected_project_rows(inputs):
        return False

    options = get_export_options(inputs)
    return bool(options.design_types or options.drawing_types
                or (exporter.HAS_ELECTRON and options.export_electronics))


def update_version_input(inputs: adsk.core.CommandInputs):
    """Exporting all versions always writes versions to the file names, so turn that option on
    and don't let it be changed."""
    version_input: adsk.core.BoolValueCommandInput = inputs.itemById('write_version')
    all_versions = inputs.itemById('all_versions').value

    version_input.isEnabled = not all_versions
    if all_versions:
        version_input.value = True


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

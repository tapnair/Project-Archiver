#  Copyright (c) 2020 by Patrick Rainsberry.
#  :license: Apache2, see LICENSE for more details.

import adsk.core
import html
import os
from ...lib import fusionAddInUtils as futil
from ...lib import archiverUtils
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_exportProject'
CMD_NAME = 'Export Active Project'
CMD_Description = 'Exports all Fusion Documents in the currently active project'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the Archive panel on the Tools tab, creating it if necessary.
    panel = archiverUtils.get_archive_panel()

    # Create the button command control in the UI.
    control = panel.controls.addCommand(cmd_def)

    # Specify if the command is promoted to the main toolbar.
    control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    archiverUtils.remove_command(CMD_ID)


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Created Event')

    # The command exports the project selected in the Data Panel. In the rare case Fusion
    # can't provide one, open the Data Panel and don't show the dialog.
    project = archiverUtils.get_active_project()
    if project is None:
        app.data.isDataPanelVisible = True
        ui.messageBox('Fusion could not find an active project.\n\n'
                      'In the Data Panel, navigate to the project you want to archive, '
                      f'then run {CMD_NAME} again.', CMD_NAME)
        return

    archiverUtils.clear_export_messages()

    # Each project gets its own folder by default so archives of different projects don't mix
    default_dir = os.path.join(archiverUtils.get_default_dir(config.user_dir_name),
                               archiverUtils.sanitize_name(project.name), '')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # Show which project will be archived, since that's whatever is selected in the Data Panel
    inputs.addTextBoxCommandInput('project_name', 'Project:', html.escape(project.name), 1, True)

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
    drawing_types_input.isVisible = archiverUtils.HAS_DRAWING

    # Only offered when this version of Fusion supports exporting electronics documents
    electronics_input = inputs.addBoolValueInput('export_electronics', 'Export electronics documents?', True, '', False)
    electronics_input.tooltip = 'Exports boards, schematics and libraries as EAGLE .brd, .sch and .lbr files'
    electronics_input.isVisible = archiverUtils.HAS_ELECTRON

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
    version_input.isVisible = False

    preserve_input = advanced_inputs.addBoolValueInput('folder_preserve_id', 'Preserve folder structure?', True, '',
                                                       True)
    preserve_input.isVisible = True

    existing_files_input = advanced_inputs.addDropDownCommandInput('existing_files', 'Existing files',
                                                                   adsk.core.DropDownStyles.TextListDropDownStyle)
    for option in archiverUtils.EXISTING_FILES_OPTIONS:
        existing_files_input.listItems.add(option, option == archiverUtils.EXISTING_FILES_RENAME)
    existing_files_input.tooltip = 'What to do when a file with the same name is already in the output folder'

    update_name_inputs(inputs, 'Document name')

    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs
    output_folder_input: adsk.core.StringValueCommandInput = inputs.itemById('output_folder')
    file_types_input: adsk.core.DropDownCommandInput = inputs.itemById('file_types_input')
    drawing_types_input: adsk.core.DropDownCommandInput = inputs.itemById('drawing_types_input')
    name_option_input: adsk.core.DropDownCommandInput = inputs.itemById('name_option_id')
    preserve_input: adsk.core.BoolValueCommandInput = inputs.itemById('folder_preserve_id')
    version_input: adsk.core.BoolValueCommandInput = inputs.itemById('write_version')
    electronics_input: adsk.core.BoolValueCommandInput = inputs.itemById('export_electronics')
    existing_files_input: adsk.core.DropDownCommandInput = inputs.itemById('existing_files')

    archiverUtils.export_project(
        output_folder_input.value,
        file_types_input.listItems,
        drawing_types_input.listItems,
        version_input.value,
        name_option_input.selectedItem.name,
        preserve_input.value,
        electronics_input.value,
        existing_files_input.selectedItem.name
    )

    # Close the documents that were opened for export. Close All shows the export summary when it finishes.
    close_command = ui.commandDefinitions.itemById(config.close_all_cmd_id)
    close_command.execute()


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

    if changed_input.id == 'name_option_id':
        name_option_input: adsk.core.DropDownCommandInput = changed_input
        update_name_inputs(inputs, name_option_input.selectedItem.name)

    elif changed_input.id == 'browse_output_folder':
        output_folder_input: adsk.core.StringValueCommandInput = inputs.itemById('output_folder')
        folder = browse_for_folder(output_folder_input.value)
        if folder:
            output_folder_input.value = os.path.join(folder, '')


# Show a folder picker starting at the current output folder, and return the chosen folder or ''.
def browse_for_folder(current_folder: str) -> str:
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


# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    inputs = args.inputs
    file_types_input: adsk.core.DropDownCommandInput = inputs.itemById('file_types_input')
    drawing_types_input: adsk.core.DropDownCommandInput = inputs.itemById('drawing_types_input')
    electronics_input: adsk.core.BoolValueCommandInput = inputs.itemById('export_electronics')

    # Only allow OK when there is something to export
    args.areInputsValid = (archiverUtils.any_type_selected(file_types_input.listItems)
                           or (drawing_types_input.isVisible
                               and archiverUtils.any_type_selected(drawing_types_input.listItems))
                           or (electronics_input.isVisible and electronics_input.value))


# Only show the write version option when naming files by document name.
def update_name_inputs(command_inputs: adsk.core.CommandInputs, selection: str):
    command_inputs.itemById('write_version').isVisible = False

    if selection == 'Document name':
        command_inputs.itemById('write_version').isVisible = True


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []

#  Copyright (c) 2020 by Patrick Rainsberry.
#  :license: Apache2, see LICENSE for more details.

import adsk.core
import os
from ...lib import fusionAddInUtils as futil
from ...lib import archiverUtils
from ...lib.archiverUtils import export_dialog
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_exportFolder'
CMD_NAME = 'Export active folder'
CMD_Description = ('Exports the designs, drawings and electronics documents in the folder open in the Data Panel, '
                   'including its subfolders')

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

# The Data Panel folder shown in the dialog, which is the one exported
export_folder = None


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

    # The command exports the folder open in the Data Panel. In the rare case Fusion
    # can't provide one, open the Data Panel and don't show the dialog.
    global export_folder
    project = archiverUtils.get_active_project()
    export_folder = archiverUtils.get_active_folder()
    if project is None or export_folder is None:
        app.data.isDataPanelVisible = True
        ui.messageBox('Fusion could not find an active folder.\n\n'
                      'In the Data Panel, navigate to the folder you want to archive, '
                      f'then run {CMD_NAME} again.', CMD_NAME)
        return

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # Show which folder will be archived, since that's whatever is open in the Data Panel
    folder_path = archiverUtils.get_folder_path(export_folder)
    location = '/'.join([project.name] + folder_path) if folder_path else f'{project.name} (project root)'
    export_dialog.add_export_inputs(inputs, 'Folder:', location, project.name)

    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    export_dialog.run_export(args.command.commandInputs, export_folder)


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

    export_dialog.handle_input_changed(changed_input, inputs)


# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # Only allow OK when there is something to export
    args.areInputsValid = export_dialog.inputs_are_valid(args.inputs)


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers, export_folder
    local_handlers = []
    export_folder = None

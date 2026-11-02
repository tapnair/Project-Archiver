#  Copyright (c) 2020 by Patrick Rainsberry.
#  :license: Apache2, see LICENSE for more details.

import adsk.core
import os
from ...lib import fusionAddInUtils as futil
from ...lib import archiverUtils
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


CMD_ID = config.close_all_cmd_id
CMD_NAME = 'Close All Docs'
CMD_Description = 'Close All Docs'

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
# This command has no dialog, so it only connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Created Event')

    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called immediately after the created event since the command has no inputs.
# It closes the active document and then runs this command again until no saved documents remain.
# Once done, it reports any files from a previous export that could not be exported.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    document = app.activeDocument

    if document is not None and document.isSaved:
        document.close(False)

        close_command = ui.commandDefinitions.itemById(CMD_ID)
        close_command.execute()

    else:
        archiverUtils.show_export_summary()


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []

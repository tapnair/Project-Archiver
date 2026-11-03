#  Copyright (c) 2019-2026 Patrick Rainsberry
#  Licensed under the Apache License, Version 2.0. See LICENSE for details.

import adsk.core
import os
from ...lib import fusionAddInUtils as futil
from ...lib import archiverUtils
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


CMD_ID = config.CLOSE_ALL_CMD_ID
CMD_NAME = 'Close all documents'
CMD_Description = 'Closes all saved documents, including designs loaded in the background by an assembly'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Upper limit on close passes in one Close All run, in case a document reports closing but stays open
MAX_PASSES = 50
pass_count = 0

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
# Each run makes one pass closing saved documents, then runs this command again so Fusion can finish
# the closes before the next pass. Once a pass closes nothing, it reports the results of an export.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    global pass_count
    pass_count += 1

    # After an export, the documents the user already had open are left open
    if archiverUtils.close_documents_pass(archiverUtils.get_keep_version_ids()) and pass_count < MAX_PASSES:
        close_command = ui.commandDefinitions.itemById(CMD_ID)
        close_command.execute()

    else:
        pass_count = 0
        archiverUtils.finish_export()


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []

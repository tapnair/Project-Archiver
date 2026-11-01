# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Copyright (c) 2020 by Patrick Rainsberry.                                   ~
#  :license: Apache2, see LICENSE for more details.                            ~
#  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Project-Archiver.py                                                            ~
#  This file is a component of Project-Archiver.                                  ~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

import adsk.core
import apper


class CloseAllCommand(apper.Fusion360CommandBase):

    def on_execute(self, command, inputs, args, input_values):
        app = adsk.core.Application.get()
        ui = app.userInterface
        document = app.activeDocument

        if document is None:
            return

        # Closing a document activates the next one, so the command re-executes
        # itself until none are left open. Ask before discarding unsaved changes
        # rather than losing them, and stop when the user cancels - otherwise
        # this would re-execute forever on the document that stayed open.
        name = document.name
        try:
            closed = document.close(True)
        except Exception as e:
            ui.messageBox('Could not close {}:\n{}'.format(name, str(e)))
            return

        if not closed:
            return

        close_command = ui.commandDefinitions.itemById(self.cmd_id)
        if close_command is not None:
            close_command.execute()


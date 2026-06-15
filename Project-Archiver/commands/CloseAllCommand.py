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

        if document.isSaved:
            document.close(False)

            close_command = ui.commandDefinitions.itemById(self.cmd_id)
            close_command.execute()


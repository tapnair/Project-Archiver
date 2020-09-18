# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Copyright (c) 2020 by Patrick Rainsberry.                                   ~
#  :license: Apache2, see LICENSE for more details.                            ~
#  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Project-Archiver.py                                                            ~
#  This file is a component of Project-Archiver.                                  ~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

import os
import sys
import adsk.core
import traceback

app_path = os.path.dirname(__file__)

sys.path.insert(0, app_path)
sys.path.insert(0, os.path.join(app_path, 'apper'))

try:
    import config
    import apper

    from commands.ExportCommand import ExportCommand

    my_addin = apper.FusionApp(config.app_name, config.company_name, False)

    my_addin.add_command(
        'Export Active Project',
        ExportCommand,
        {
            'cmd_description': 'Exports all Fusion Documents in the currently active project',
            'cmd_id': 'export_cmd_1',
            'workspace': 'FusionSolidEnvironment',
            'toolbar_panel_id': 'Archive',
            'cmd_resources': 'command_icons',
            'command_visible': True,
            'command_promoted': True,

        }
    )

except:
    app = adsk.core.Application.get()
    ui = app.userInterface
    ui.messageBox('Initialization Failed: {}'.format(traceback.format_exc()))

debug = False


def run(context):
    my_addin.run_app()


def stop(context):
    my_addin.stop_app()
    sys.path.pop(0)
    sys.path.pop(0)

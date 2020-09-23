# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Copyright (c) 2020 by Patrick Rainsberry.                                   ~
#  :license: Apache2, see LICENSE for more details.                            ~
#  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Project-Archiver.py                                                            ~
#  This file is a component of Project-Archiver.                                  ~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

import os
import sys
from importlib import reload

import adsk.core
import traceback


from.startup import setup_app, cleanup_app, get_app_path
setup_app(__file__)

try:
    import config
    import apper

    from .commands.ExportCommand import ExportCommand
    from .commands.CloseAllCommand import CloseAllCommand

    my_addin = apper.FusionApp(config.app_name, config.company_name, False)
    my_addin.root_path = get_app_path(__file__)
    reload(config)

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

    my_addin.add_command(
        'Close All Docs',
        CloseAllCommand,
        {
            'cmd_description': 'Close All Docs',
            'cmd_id': config.close_cmd_id,
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
    cleanup_app(__file__)

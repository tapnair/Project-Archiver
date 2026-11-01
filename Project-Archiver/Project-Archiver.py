# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Copyright (c) 2020 by Patrick Rainsberry.                                   ~
#  :license: Apache2, see LICENSE for more details.                            ~
#  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Project-Archiver.py                                                            ~
#  This file is a component of Project-Archiver.                                  ~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

import traceback

import adsk.core


from.startup import setup_app, cleanup_app, get_app_path, apper_available
setup_app(__file__)

my_addin = None

try:
    if not apper_available(__file__):
        raise RuntimeError(
            'The bundled "apper" framework is missing from this installation.\n\n'
            'This normally happens when the add-in was downloaded as a plain zip '
            'of the source repository, which does not contain the apper '
            'submodule. Install the distribution zip from the dist folder, or '
            'clone with "git clone --recurse-submodules".'
        )

    import config
    import apper

    from .commands.ExportCommand import ExportCommand
    from .commands.CloseAllCommand import CloseAllCommand

    my_addin = apper.FusionApp(config.app_name, config.company_name, False)
    my_addin.root_path = get_app_path(__file__)

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


def run(context):
    # Initialization failed and already reported the reason; nothing to start.
    if my_addin is None:
        return

    my_addin.run_app()


def stop(context):
    if my_addin is not None:
        my_addin.stop_app()

    cleanup_app(__file__)

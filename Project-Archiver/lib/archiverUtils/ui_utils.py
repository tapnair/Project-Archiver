#  Copyright (c) 2020 by Patrick Rainsberry.
#  :license: Apache2, see LICENSE for more details.

import adsk.core

from ... import config

app = adsk.core.Application.get()
ui = app.userInterface


def get_archive_panel() -> adsk.core.ToolbarPanel:
    """Get the Archive panel on the Tools tab of the Design workspace, creating it if necessary."""
    workspace = ui.workspaces.itemById(config.design_workspace)
    toolbar_tab = workspace.toolbarTabs.itemById(config.tools_tab_id)

    panel = toolbar_tab.toolbarPanels.itemById(config.archive_panel_id)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(config.archive_panel_id, config.archive_panel_name)

    return panel


def remove_command(cmd_id: str):
    """Delete a command's control and definition, and delete the Archive panel once it is empty."""
    workspace = ui.workspaces.itemById(config.design_workspace)
    panel = workspace.toolbarPanels.itemById(config.archive_panel_id)

    if panel:
        command_control = panel.controls.itemById(cmd_id)
        if command_control:
            command_control.deleteMe()

        if panel.controls.count == 0:
            panel.deleteMe()

    command_definition = ui.commandDefinitions.itemById(cmd_id)
    if command_definition:
        command_definition.deleteMe()

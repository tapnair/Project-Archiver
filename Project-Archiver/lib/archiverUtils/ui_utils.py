#  Copyright (c) 2019-2026 Patrick Rainsberry
#  Licensed under the Apache License, Version 2.0. See LICENSE for details.

"""Adds and removes the Archive panel and its command buttons."""

import adsk.core

from ... import config

app = adsk.core.Application.get()
ui = app.userInterface


def get_archive_panel() -> adsk.core.ToolbarPanel:
    """Get the Archive panel on the Tools tab of the Design workspace, creating it if necessary."""
    workspace = ui.workspaces.itemById(config.DESIGN_WORKSPACE_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(config.TOOLS_TAB_ID)

    panel = toolbar_tab.toolbarPanels.itemById(config.ARCHIVE_PANEL_ID)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(config.ARCHIVE_PANEL_ID, config.ARCHIVE_PANEL_NAME)

    return panel


def remove_command(cmd_id: str):
    """Delete a command's control and definition, and delete the Archive panel once it is empty."""
    workspace = ui.workspaces.itemById(config.DESIGN_WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(config.ARCHIVE_PANEL_ID)

    if panel:
        command_control = panel.controls.itemById(cmd_id)
        if command_control:
            command_control.deleteMe()

        if panel.controls.count == 0:
            panel.deleteMe()

    command_definition = ui.commandDefinitions.itemById(cmd_id)
    if command_definition:
        command_definition.deleteMe()

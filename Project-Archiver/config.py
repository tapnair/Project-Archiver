#  Copyright (c) 2020 by Patrick Rainsberry.
#  :license: Apache2, see LICENSE for more details.

# Application Global Variables
# This module serves as a way to share variables across different
# modules (global variables).

import os

# Flag that indicates to run in Debug mode or not. When running in Debug mode
# more information is written to the Text Command window. Generally, it's useful
# to set this to True while developing an add-in and set it to False when you
# are ready to distribute it.
DEBUG = False

# Gets the name of the add-in from the name of the folder the py file is in.
# This is used when defining unique internal names for various UI elements
# that need a unique name. It's also recommended to use a company name as
# part of the ID to better ensure the ID is unique.
ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
COMPANY_NAME = 'Autodesk'

# Name of the folder created in the user's home directory as the default export location
user_dir_name = 'ProjectArchiver'

# Location of the Archive panel shared by all commands
design_workspace = 'FusionSolidEnvironment'
tools_tab_id = 'ToolsTab'
archive_panel_id = f'{COMPANY_NAME}_{ADDIN_NAME}_archive_panel'
archive_panel_name = 'Archive'

# Command IDs that are referenced by more than one command
close_all_cmd_id = f'{COMPANY_NAME}_{ADDIN_NAME}_closeAll'

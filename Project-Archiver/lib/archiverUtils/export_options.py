#  Copyright (c) 2019-2026 Patrick Rainsberry
#  Licensed under the Apache License, Version 2.0. See LICENSE for details.

"""The choices made in the export dialog, and the results of an export."""

from dataclasses import dataclass, field

import adsk.core

# File name options. The values are the File name option dropdown items.
NAME_DOCUMENT = 'Document name'
NAME_DESCRIPTION = 'Description'
NAME_PART_NUMBER = 'Part number'
NAME_OPTIONS = [NAME_DOCUMENT, NAME_DESCRIPTION, NAME_PART_NUMBER]

# What to do when an export file already exists. The values are the Existing files dropdown items.
EXISTING_FILES_SKIP = 'Skip existing files'
EXISTING_FILES_RENAME = 'Rename with -dup'
EXISTING_FILES_OVERWRITE = 'Overwrite'
EXISTING_FILES_OPTIONS = [EXISTING_FILES_RENAME, EXISTING_FILES_SKIP, EXISTING_FILES_OVERWRITE]

# Design export type -> file extension
DESIGN_EXTENSIONS = {'IGES': '.igs', 'STEP': '.step', 'SAT': '.sat', 'SMT': '.smt', 'F3D': '.f3d', 'STL': '.stl'}

# Drawing export type -> (factory method on the DrawingExportManager, file extension).
# DXF and DWG export are preview APIs, so each factory is checked before it's used.
DRAWING_EXPORTS = {
    'PDF': ('createPDFExportOptions', '.pdf'),
    'DXF': ('createDXFExportOptions', '.dxf'),
    'DWG': ('createDWGExportOptions', '.dwg'),
}

# Electronics data file extension -> (factory method on the ElectronicsExportManager, file extension).
# Each electronics document type has exactly one export format. An electronics design (fprj) isn't
# exported on its own: its schematic and board are separate fsch and fbrd files in the same folder.
ELECTRONICS_EXPORTS = {
    'fsch': ('createEagleSchExportOptions', '.sch'),
    'fbrd': ('createEagleBrdExportOptions', '.brd'),
    'flbr': ('createEagleLbrExportOptions', '.lbr'),
}

# Data file extensions this add-in can export
DESIGN_FILE_EXTENSION = 'f3d'
DRAWING_FILE_EXTENSION = 'f2d'
EXPORTED_FILE_EXTENSIONS = {DESIGN_FILE_EXTENSION, DRAWING_FILE_EXTENSION} | set(ELECTRONICS_EXPORTS)


@dataclass
class ExportOptions:
    """Everything chosen in the export dialog."""

    output_folder: str     # root folder; files go to <root>/<hub>/<project>/...
    design_types: list = field(default_factory=list)    # names from DESIGN_EXTENSIONS, such as 'STEP'
    drawing_types: list = field(default_factory=list)   # names from DRAWING_EXPORTS, such as 'PDF'
    export_electronics: bool = True
    name_option: str = NAME_DOCUMENT
    write_version: bool = False
    preserve_folders: bool = True
    existing_files: str = EXISTING_FILES_SKIP
    skip_used_designs: bool = False
    include_hidden: bool = False
    all_versions: bool = False

    # The project to export, or None for the active project
    project: adsk.core.DataProject = None

    # The folder in the project to export, or None for the whole project
    data_folder: adsk.core.DataFolder = None


@dataclass
class ExportResults:
    """What happened during an export, for the summary at the end."""

    exported_files: int = 0                                # files written
    existing_skipped: list = field(default_factory=list)   # paths that already existed
    used_designs_skipped: set = field(default_factory=set)  # data file ids, so versions count once
    f3d_skipped: list = field(default_factory=list)        # project paths of designs that reference others
    failed: list = field(default_factory=list)             # "<file>: <reason>" lines
    cancelled: tuple = None                                 # (files done, files to export) if cancelled
    declined: bool = False                                  # the all-versions confirmation was declined

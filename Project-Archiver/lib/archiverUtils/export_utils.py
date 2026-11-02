#  Copyright (c) 2020 by Patrick Rainsberry.
#  :license: Apache2, see LICENSE for more details.

import os

import adsk.core
import adsk.fusion
import adsk.cam

# Feature-detect the Electronics API. It only exists on newer Fusion builds
# (preview API, introduced May 2026) and may be absent on the many older
# installs this widely-used add-in still runs on. Importing it unconditionally
# at module load would break add-in initialization (and therefore the existing
# STEP/IGES/etc. export) on those installs, so we guard it.
try:
    import adsk.electron
    HAS_ELECTRON = True
except ImportError:
    HAS_ELECTRON = False

from .file_utils import dup_check, sanitize_name

app = adsk.core.Application.get()
ui = app.userInterface

SKIPPED_FILES = []
FAILED_FILES = []
ELECTRONICS_ERRORS = []

# Electronics export type name -> (factory method name on the ElectronicsExportManager, file extension)
ELECTRONICS_EXPORTS = {
    'BRD': ('createEagleBrdExportOptions', '.brd'),
    'SCH': ('createEagleSchExportOptions', '.sch'),
    'LBR': ('createEagleLbrExportOptions', '.lbr'),
}

# Fusion-native data-panel extensions for electronics documents:
# fprj = electronics design (umbrella), fsch = schematic, fbrd = 2D PCB board,
# flbr = library. These are the document extensions in the hub, distinct from
# the EAGLE export extensions (.sch/.brd/.lbr) produced on export.
ELECTRONICS_EXTENSIONS = {'fprj', 'fsch', 'fbrd', 'flbr'}


def get_active_project():
    """Return the project selected in the Data Panel, or None if Fusion can't provide one.

    There is normally always an active project, but in rare cases Fusion raises an
    InternalValidationError instead, for example before the Data Panel has loaded.
    """
    try:
        return app.data.activeProject
    except RuntimeError:
        return None


def get_active_design():
    """Return the Design product of the active document, or None if it has no design."""
    document = app.activeDocument
    return adsk.fusion.Design.cast(document.products.itemByProductType('DesignProductType'))


def clear_export_messages():
    SKIPPED_FILES.clear()
    FAILED_FILES.clear()
    ELECTRONICS_ERRORS.clear()


def export_project(output_folder, file_types, write_version, name_option, folder_preserve):
    """Export every document in the active project.

    Files that could not be exported are collected and reported by show_export_summary
    once the opened documents have been closed.
    """
    root_folder = get_active_project().rootFolder

    # Make sure we have a folder not a file
    if not output_folder.endswith(os.path.sep):
        output_folder += os.path.sep

    # Create the base folder for this output if doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    export_folder(root_folder, output_folder, file_types, write_version, name_option, folder_preserve)


def show_export_summary():
    """Report any files that could not be exported, then clear the list.

    Showing a message box while the exported documents are still open can fail with
    "failed to find product", so this is called after they have been closed.
    """
    messages = []

    if len(SKIPPED_FILES) > 0:
        messages.append(
            "The following files contained external references and could not be exported as f3d's: {}".format(
                SKIPPED_FILES
            )
        )

    if len(FAILED_FILES) > 0:
        messages.append(
            "The following files could not be exported:\n{}".format(
                "\n".join(FAILED_FILES)
            )
        )

    if len(ELECTRONICS_ERRORS) > 0:
        messages.append(
            "Some electronics documents could not be exported:\n{}".format(
                "\n".join(ELECTRONICS_ERRORS)
            )
        )

    clear_export_messages()

    for message in messages:
        ui.messageBox(message)


def export_folder(root_folder, output_folder, file_types, write_version, name_option, folder_preserve):
    for folder in root_folder.dataFolders:

        if folder_preserve:
            new_folder = os.path.join(output_folder, sanitize_name(folder.name), "")

            if not os.path.exists(new_folder):
                os.makedirs(new_folder)
        else:
            new_folder = output_folder

        export_folder(folder, new_folder, file_types, write_version, name_option, folder_preserve)

    for file in root_folder.dataFiles:
        if file.fileExtension == "f3d":
            export_data_file(file, output_folder, file_types, write_version, name_option)

        elif (HAS_ELECTRON and any_electronics_selected(file_types)
                and file.fileExtension in ELECTRONICS_EXTENSIONS):
            # Only open Fusion-native electronics documents (fprj/fsch/fbrd/flbr).
            # Opening unrelated hub files (drawings, etc.) and reading product
            # data on them raises Fusion's "failed to find product" error.
            export_electronics_file(file, output_folder, file_types, write_version)


def export_data_file(data_file, output_folder, file_types, write_version, name_option):
    """Open a design and export it to the selected types.

    A file that fails is recorded and skipped so the rest of the project is still exported.
    """
    document = open_doc(data_file)

    if document is None:
        FAILED_FILES.append("{}: could not be opened".format(data_file.name))
        return

    try:
        output_name = get_name(write_version, name_option)
        export_active_doc(output_folder, file_types, output_name)

    except Exception as e:
        FAILED_FILES.append("{}: {}".format(data_file.name, str(e)))


def export_electronics_file(data_file, output_folder, file_types, write_version):
    """Open an electronics document and export it to the selected EAGLE formats."""
    document = open_doc(data_file)

    if document is None:
        ELECTRONICS_ERRORS.append("{}: could not be opened".format(data_file.name))
        return

    try:
        # Electronics docs are not design products, so the root_comp
        # based name options in get_name would fail. Use the document
        # name directly (optionally stripped of its version suffix).
        output_name = get_document_name(write_version)
        export_electronics_doc(output_folder, file_types, output_name)
    except Exception as e:
        ELECTRONICS_ERRORS.append("{}: {}".format(data_file.name, str(e)))


def get_data_file_id(document):
    """Return the id of the data file a document was opened from, or None for an unsaved document."""
    try:
        data_file = document.dataFile
        return data_file.id if data_file else None
    except RuntimeError:
        return None


def open_doc(data_file):
    """Open and activate a data file, returning its document, or None if it didn't open.

    Fusion sometimes raises "failed to find product" even though the document opened,
    so success is judged by whether the requested document ended up active.
    """
    try:
        document = app.documents.open(data_file, True)
        if document is not None:
            # A design that can't be loaded, such as an upload that never finished
            # processing, opens as an empty unsaved placeholder instead
            if not document.isSaved:
                document.close(False)
                return None
            document.activate()
    except RuntimeError:
        pass

    document = app.activeDocument
    if document is not None and get_data_file_id(document) == data_file.id:
        return document

    return None


def is_type_selected(file_types, type_name):
    """Return True if the named export type is checked in the dropdown.

    Selecting by name keeps the export logic independent of the order/number of
    items in the dropdown, so new types can be added without shifting handling.
    """
    for i in range(file_types.count):
        item = file_types.item(i)
        if item.name == type_name:
            return item.isSelected
    return False


def any_electronics_selected(file_types):
    """Return True if any electronics export type is checked in the dropdown."""
    return any(is_type_selected(file_types, type_name) for type_name in ELECTRONICS_EXPORTS)


def export_active_doc(folder, file_types, output_name):
    document = app.activeDocument
    design = get_active_design()
    export_mgr = design.exportManager

    # Simple solid-body export types, keyed by the dropdown item name.
    solid_export_functions = {
        'IGES': (export_mgr.createIGESExportOptions, '.igs'),
        'STEP': (export_mgr.createSTEPExportOptions, '.step'),
        'SAT': (export_mgr.createSATExportOptions, '.sat'),
        'SMT': (export_mgr.createSMTExportOptions, '.smt'),
    }

    for type_name, (export_function, extension) in solid_export_functions.items():
        if is_type_selected(file_types, type_name):
            export_name = folder + output_name + extension
            export_name = dup_check(export_name)
            export_options = export_function(export_name)
            export_mgr.execute(export_options)

    if is_type_selected(file_types, 'F3D'):

        if document.allDocumentReferences.count > 0:
            SKIPPED_FILES.append(document.name)

        else:
            export_name = folder + output_name + '.f3d'
            export_name = dup_check(export_name)
            export_options = export_mgr.createFusionArchiveExportOptions(export_name)
            export_mgr.execute(export_options)

    if is_type_selected(file_types, 'STL'):
        stl_export_name = folder + output_name + '.stl'
        stl_export_name = dup_check(stl_export_name)
        stl_options = export_mgr.createSTLExportOptions(design.rootComponent, stl_export_name)
        export_mgr.execute(stl_options)


def _export_one_electronics_format(product, type_name, folder, output_name):
    """Export a single electronics document to one EAGLE format.

    product: the electronics product (Board, Schematic, or Library)
    type_name: one of the keys in ELECTRONICS_EXPORTS ('BRD', 'SCH', 'LBR')

    The ElectronicsExportManager is a preview API, so we verify the factory
    method exists before calling it and tolerate any failure by recording it
    rather than aborting the whole archive run.
    """
    factory_name, extension = ELECTRONICS_EXPORTS[type_name]

    try:
        export_mgr = product.exportManager

        # The factory only exists on supported/preview builds. If it's missing,
        # skip quietly with a collected note instead of raising.
        if export_mgr is None or not hasattr(export_mgr, factory_name):
            ELECTRONICS_ERRORS.append(
                "{}: {} export not available in this Fusion version".format(output_name, type_name)
            )
            return

        export_name = folder + output_name + extension
        export_name = dup_check(export_name)

        export_options = getattr(export_mgr, factory_name)(export_name)

        # A None result means the factory was called on the wrong product type.
        if export_options is None:
            ELECTRONICS_ERRORS.append(
                "{}: {} export options could not be created".format(output_name, type_name)
            )
            return

        if not export_mgr.execute(export_options):
            ELECTRONICS_ERRORS.append("{}: {} export failed".format(output_name, type_name))

    except Exception as e:
        ELECTRONICS_ERRORS.append("{}: {} export error: {}".format(output_name, type_name, str(e)))


def export_electronics_doc(folder, file_types, output_name):
    """Export the active electronics document to the selected EAGLE formats.

    Determines the document type by casting the active product (per the Fusion
    Electronics API pattern) and routes to the matching export manager(s).
    Boards/schematics already embed the library parts they reference, so a
    standalone .lbr is only produced for a standalone Library document.
    """
    if not HAS_ELECTRON:
        return

    # The active product may not resolve immediately after opening certain
    # documents; treat that as "nothing to export here" rather than erroring.
    try:
        product = app.activeProduct
    except Exception:
        return

    if product is None:
        return

    board = adsk.electron.Board.cast(product)
    schematic = adsk.electron.Schematic.cast(product)
    library = adsk.electron.Library.cast(product)
    ecad_design = adsk.electron.EcadDesign.cast(product)

    if board is not None:
        if is_type_selected(file_types, 'BRD'):
            _export_one_electronics_format(board, 'BRD', folder, output_name)

    elif schematic is not None:
        if is_type_selected(file_types, 'SCH'):
            _export_one_electronics_format(schematic, 'SCH', folder, output_name)

    elif library is not None:
        if is_type_selected(file_types, 'LBR'):
            _export_one_electronics_format(library, 'LBR', folder, output_name)

    elif ecad_design is not None:
        # An electronics design ties together a schematic and board; export each
        # through its own product so the right export manager is used.
        if is_type_selected(file_types, 'SCH') and ecad_design.schematic is not None:
            _export_one_electronics_format(ecad_design.schematic, 'SCH', folder, output_name)
        if is_type_selected(file_types, 'BRD') and ecad_design.board is not None:
            _export_one_electronics_format(ecad_design.board, 'BRD', folder, output_name)


def get_document_name(write_version):
    """Derive an output name from the active document's name.

    The trailing version suffix (e.g. " v3") is removed unless write_version is set.
    """
    doc_name = app.activeDocument.name

    if not write_version:
        version_index = doc_name.rfind(' v')
        if version_index != -1:
            doc_name = doc_name[:version_index]

    return sanitize_name(doc_name)


def get_name(write_version, option):
    """Derive an output name for a design using the selected File Name Option.

    Falls back to the document name when the description or part number is empty.
    """
    if option == 'Document Name':
        return get_document_name(write_version)

    elif option == 'Description':
        output_name = get_active_design().rootComponent.description

    elif option == 'Part Number':
        output_name = get_active_design().rootComponent.partNumber

    else:
        raise ValueError('Something strange happened')

    output_name = sanitize_name(output_name)
    if not output_name:
        output_name = get_document_name(write_version)

    return output_name

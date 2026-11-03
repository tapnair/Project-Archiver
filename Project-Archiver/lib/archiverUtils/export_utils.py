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

# Feature-detect the Drawing API for the same reason
try:
    import adsk.drawing
    HAS_DRAWING = True
except ImportError:
    HAS_DRAWING = False

from .file_utils import dup_check, sanitize_name

app = adsk.core.Application.get()
ui = app.userInterface

SKIPPED_FILES = []
FAILED_FILES = []
ELECTRONICS_ERRORS = []

# Data file ids of the documents the user already had open when the export started.
# These are left open rather than closed after export.
OPEN_BEFORE_EXPORT = set()

# True from the end of an export until Close All has finished cleaning up after it
EXPORT_CLEANUP_PENDING = False

# Electronics export type name -> (factory method name on the ElectronicsExportManager, file extension)
ELECTRONICS_EXPORTS = {
    'BRD': ('createEagleBrdExportOptions', '.brd'),
    'SCH': ('createEagleSchExportOptions', '.sch'),
    'LBR': ('createEagleLbrExportOptions', '.lbr'),
}

# Fusion-native data-panel extensions for electronics documents:
# fsch = schematic, fbrd = 2D PCB board, flbr = library. These are the document
# extensions in the hub, distinct from the EAGLE export extensions (.sch/.brd/.lbr)
# produced on export. An electronics design (fprj) is skipped: its schematic and
# board are separate fsch and fbrd files that are exported on their own.
ELECTRONICS_EXTENSIONS = {'fsch', 'fbrd', 'flbr'}

# Drawing export type name -> (factory method name on the DrawingExportManager, file extension).
# DXF and DWG export are preview APIs, so each factory is checked before it's used.
DRAWING_EXPORTS = {
    'PDF': ('createPDFExportOptions', '.pdf'),
    'DXF': ('createDXFExportOptions', '.dxf'),
    'DWG': ('createDWGExportOptions', '.dwg'),
}


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


def export_project(output_folder, file_types, drawing_types, write_version, name_option, folder_preserve,
                   export_electronics):
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

    OPEN_BEFORE_EXPORT.clear()
    for i in range(app.documents.count):
        OPEN_BEFORE_EXPORT.add(get_data_file_id(app.documents.item(i)))
    OPEN_BEFORE_EXPORT.discard(None)

    export_folder(root_folder, output_folder, file_types, drawing_types, write_version, name_option,
                  folder_preserve, export_electronics)

    global EXPORT_CLEANUP_PENDING
    EXPORT_CLEANUP_PENDING = True


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


def export_folder(root_folder, output_folder, file_types, drawing_types, write_version, name_option,
                  folder_preserve, export_electronics):
    for folder in root_folder.dataFolders:

        if folder_preserve:
            new_folder = os.path.join(output_folder, sanitize_name(folder.name), "")

            if not os.path.exists(new_folder):
                os.makedirs(new_folder)
        else:
            new_folder = output_folder

        export_folder(folder, new_folder, file_types, drawing_types, write_version, name_option,
                      folder_preserve, export_electronics)

    for file in root_folder.dataFiles:
        if file.fileExtension == "f3d" and any_type_selected(file_types):
            export_data_file(file, output_folder, file_types, write_version, name_option)

        elif HAS_DRAWING and file.fileExtension == "f2d" and any_type_selected(drawing_types):
            export_drawing_file(file, output_folder, drawing_types, write_version)

        elif HAS_ELECTRON and export_electronics and file.fileExtension in ELECTRONICS_EXTENSIONS:
            # Only open Fusion-native electronics documents (fsch/fbrd/flbr).
            # Opening unrelated hub files (drawings, etc.) and reading product
            # data on them raises Fusion's "failed to find product" error.
            export_electronics_file(file, output_folder, write_version)


def export_data_file(data_file, output_folder, file_types, write_version, name_option):
    """Open a design, export it, and close it again so memory doesn't grow with the size of the project.

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

    finally:
        close_doc(document)


def export_drawing_file(data_file, output_folder, drawing_types, write_version):
    """Open a drawing, export it to the selected types, and close it again."""
    document = open_doc(data_file)

    if document is None:
        FAILED_FILES.append("{}: could not be opened".format(data_file.name))
        return

    try:
        # Drawings don't have a description or part number, so always use the document name
        output_name = get_document_name(write_version)
        export_drawing_doc(document, output_folder, drawing_types, output_name)

    except Exception as e:
        FAILED_FILES.append("{}: {}".format(data_file.name, str(e)))

    finally:
        close_doc(document)


def export_drawing_doc(document, folder, drawing_types, output_name):
    """Export a drawing to each selected type. Each type produces one file containing every sheet.

    A type that fails is recorded and the remaining types are still exported.
    """
    # A drawing isn't available through document.products, only through the drawing document
    export_mgr = adsk.drawing.DrawingDocument.cast(document).drawing.exportManager

    for type_name, (factory_name, extension) in DRAWING_EXPORTS.items():
        if not is_type_selected(drawing_types, type_name):
            continue

        if not hasattr(export_mgr, factory_name):
            FAILED_FILES.append("{}: {} export not available in this Fusion version".format(output_name, type_name))
            continue

        try:
            export_name = dup_check(folder + output_name + extension)
            export_options = getattr(export_mgr, factory_name)(export_name)

            if type_name == 'PDF':
                export_options.openPDF = False

            if not export_mgr.execute(export_options):
                FAILED_FILES.append("{}: {} export failed".format(output_name, type_name))

        except Exception as e:
            FAILED_FILES.append("{}: {} export error: {}".format(output_name, type_name, str(e)))


def export_electronics_file(data_file, output_folder, write_version):
    """Open an electronics document, export it to its EAGLE format, and close it again."""
    document = open_doc(data_file)

    if document is None:
        ELECTRONICS_ERRORS.append("{}: could not be opened".format(data_file.name))
        return

    try:
        # Electronics docs are not design products, so the root_comp
        # based name options in get_name would fail. Use the document
        # name directly (optionally stripped of its version suffix).
        output_name = get_document_name(write_version)
        export_electronics_doc(output_folder, output_name)
    except Exception as e:
        ELECTRONICS_ERRORS.append("{}: {}".format(data_file.name, str(e)))

    finally:
        close_doc(document)


def get_data_file_id(document):
    """Return the id of the data file a document was opened from, or None for an unsaved document."""
    try:
        data_file = document.dataFile
        return data_file.id if data_file else None
    except RuntimeError:
        return None


def open_doc(data_file):
    """Open and activate a data file, returning its document, or None if it didn't open.

    Opening one document can load several: an electronics schematic or board loads its whole
    electronics design, and the document open returns isn't always the one requested. Fusion
    also sometimes raises "failed to find product" even though the document opened. So the
    requested document is found among the open documents by its data file.
    """
    try:
        document = app.documents.open(data_file, True)

        # A design that can't be loaded, such as an upload that never finished
        # processing, opens as an empty unsaved placeholder instead
        if document is not None and not document.isSaved:
            document.close(False)
            return None
    except RuntimeError:
        pass

    for i in range(app.documents.count):
        document = app.documents.item(i)
        if get_data_file_id(document) == data_file.id:
            try:
                document.activate()
            except RuntimeError:
                pass
            if get_data_file_id(app.activeDocument) == data_file.id:
                return document

    return None


def close_doc(document):
    """Close a document opened for export without saving, unless the user already had it open.

    Fusion sometimes raises "failed to find product" even though the document closed. A document
    that really doesn't close is still picked up by Close All when the export finishes.
    """
    if get_data_file_id(document) in OPEN_BEFORE_EXPORT:
        return

    try:
        document.close(False)
    except RuntimeError:
        pass


def close_documents_pass() -> bool:
    """Make one pass closing saved documents, and return True if any closed.

    After an export, only documents the export loaded are closed, including designs an assembly
    referenced that stay loaded after the assembly closes. Otherwise every saved document is
    closed. A document can't close while another loaded document references it, so the caller
    repeats passes, letting Fusion finish each one, until a pass closes nothing. Unsaved
    documents are never closed.
    """
    keep = OPEN_BEFORE_EXPORT if EXPORT_CLEANUP_PENDING else set()
    progress = False

    for document in [app.documents.item(i) for i in range(app.documents.count)]:
        if not document.isValid:
            continue

        data_file_id = get_data_file_id(document)
        if data_file_id is None or data_file_id in keep:
            continue

        count = app.documents.count
        try:
            closed = document.close(False)
        except RuntimeError:
            closed = False

        if closed or app.documents.count < count:
            progress = True

    return progress


def finish_close_all():
    """Called when Close All is done. Reports the results of an export it was cleaning up after."""
    global EXPORT_CLEANUP_PENDING

    if EXPORT_CLEANUP_PENDING:
        EXPORT_CLEANUP_PENDING = False
        OPEN_BEFORE_EXPORT.clear()
        show_export_summary()


def any_type_selected(file_types):
    """Return True if any export type is checked in the dropdown."""
    return any(file_types.item(i).isSelected for i in range(file_types.count))


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


def export_electronics_doc(folder, output_name):
    """Export the active electronics document to its EAGLE format.

    Each electronics document type has exactly one export format: a board exports
    as .brd, a schematic as .sch and a library as .lbr.

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

    if board is not None:
        _export_one_electronics_format(board, 'BRD', folder, output_name)

    elif schematic is not None:
        _export_one_electronics_format(schematic, 'SCH', folder, output_name)

    elif library is not None:
        _export_one_electronics_format(library, 'LBR', folder, output_name)


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
    """Derive an output name for a design using the selected file name option.

    Falls back to the document name when the description or part number is empty.
    """
    if option == 'Document name':
        return get_document_name(write_version)

    elif option == 'Description':
        output_name = get_active_design().rootComponent.description

    elif option == 'Part number':
        output_name = get_active_design().rootComponent.partNumber

    else:
        raise ValueError('Something strange happened')

    output_name = sanitize_name(output_name)
    if not output_name:
        output_name = get_document_name(write_version)

    return output_name

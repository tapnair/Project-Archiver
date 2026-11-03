#  Copyright (c) 2020 by Patrick Rainsberry.
#  :license: Apache2, see LICENSE for more details.

import os
import re

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
from .log_utils import LOG_FILE_NAME, start_log, end_log, log

app = adsk.core.Application.get()
ui = app.userInterface

SKIPPED_FILES = []
EXISTING_FILES_SKIPPED = []
USED_DESIGNS_SKIPPED = []

# Paths written for the file currently being exported, for the log
current_exports = []
FAILED_FILES = []
ELECTRONICS_ERRORS = []

# Data file ids of the documents the user already had open when the export started.
# These are left open rather than closed after export.
OPEN_BEFORE_EXPORT = set()

# What to do when an export file already exists. The values are the Existing files dropdown items.
EXISTING_FILES_RENAME = 'Rename with -dup'
EXISTING_FILES_SKIP = 'Skip existing files'
EXISTING_FILES_OVERWRITE = 'Overwrite'
EXISTING_FILES_OPTIONS = [EXISTING_FILES_RENAME, EXISTING_FILES_SKIP, EXISTING_FILES_OVERWRITE]
existing_files = EXISTING_FILES_RENAME

# When True, designs inserted into other designs aren't exported on their own
skip_used_designs = False

# When True, hidden bodies and components are shown before exporting to formats other than F3D
include_hidden = False

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
ELECTRONICS_EXTENSIONS = {'fsch': '.sch', 'fbrd': '.brd', 'flbr': '.lbr'}

# Data panel file extensions this add-in can export
EXPORTED_EXTENSIONS = {'f3d', 'f2d'} | set(ELECTRONICS_EXTENSIONS)

# Design export type name -> file extension
DESIGN_EXTENSIONS = {'IGES': '.igs', 'STEP': '.step', 'SAT': '.sat', 'SMT': '.smt', 'F3D': '.f3d', 'STL': '.stl'}

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
    EXISTING_FILES_SKIPPED.clear()
    USED_DESIGNS_SKIPPED.clear()
    FAILED_FILES.clear()
    ELECTRONICS_ERRORS.clear()


def export_project(output_folder, file_types, drawing_types, write_version, name_option, folder_preserve,
                   export_electronics, existing_files_option=EXISTING_FILES_RENAME, skip_used_designs_option=False,
                   include_hidden_option=False):
    """Export every document in the active project.

    Files that could not be exported are collected and reported by show_export_summary
    once the opened documents have been closed.
    """
    root_folder = get_active_project().rootFolder

    global existing_files, skip_used_designs, include_hidden
    existing_files = existing_files_option
    skip_used_designs = skip_used_designs_option
    include_hidden = include_hidden_option

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

    start_log(output_folder, [
        'Project: {}'.format(get_active_project().name),
        'Output folder: {}'.format(output_folder),
        'Design export types: {}'.format(', '.join(selected_type_names(file_types)) or 'none'),
        'Drawing export types: {}'.format(', '.join(selected_type_names(drawing_types)) or 'none'),
        'Export electronics documents: {}'.format('yes' if HAS_ELECTRON and export_electronics else 'no'),
        'File name option: {}{}'.format(name_option, ', with versions' if write_version else ''),
        'Preserve folder structure: {}'.format('yes' if folder_preserve else 'no'),
        'Existing files: {}'.format(existing_files),
        'Skip designs used by other designs: {}'.format('yes' if skip_used_designs else 'no'),
        'Include hidden bodies and components: {}'.format('yes' if include_hidden else 'no'),
    ])

    export_folder(root_folder, output_folder, file_types, drawing_types, write_version, name_option,
                  folder_preserve, export_electronics)

    end_log(get_summary_messages() or ['Every file was exported.'])

    global EXPORT_CLEANUP_PENDING
    EXPORT_CLEANUP_PENDING = True


def show_export_summary():
    """Report any files that could not be exported, then clear the list.

    Showing a message box while the exported documents are still open can fail with
    "failed to find product", so this is called after they have been closed.
    """
    messages = get_summary_messages()
    if messages:
        messages.append('Details for every file are in {} in the output folder.'.format(LOG_FILE_NAME))

    clear_export_messages()

    for message in messages:
        ui.messageBox(message)


def get_summary_messages():
    """Return the messages that summarize what wasn't exported."""
    messages = []

    if len(USED_DESIGNS_SKIPPED) > 0:
        messages.append(
            "{} designs used by other designs were skipped.".format(len(USED_DESIGNS_SKIPPED))
        )

    if len(EXISTING_FILES_SKIPPED) > 0:
        messages.append(
            "{} files already existed in the output folder and were skipped.".format(len(EXISTING_FILES_SKIPPED))
        )

    if len(SKIPPED_FILES) > 0:
        messages.append(
            "These designs reference other designs, so they weren't exported as F3D:\n{}\n\n"
            "An F3D of a design like this only links to the referenced designs and can't be opened on its own. "
            "The other export types were still exported, and each referenced design gets its own F3D. "
            "To keep a design with everything it references, open it and use File > Export to save an F3Z.".format(
                "\n".join(SKIPPED_FILES)
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

    return messages


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

        elif file.fileExtension in EXPORTED_EXTENSIONS:
            log('Not exported: {} (export type not selected)'.format(get_project_path(file)))

        else:
            log('Not exported: {} (.{} files aren\'t exported)'.format(get_project_path(file), file.fileExtension))


def export_data_file(data_file, output_folder, file_types, write_version, name_option):
    """Open a design, export it, and close it again so memory doesn't grow with the size of the project.

    A file that fails is recorded and skipped so the rest of the project is still exported.
    """
    if skip_used_designs and is_used_by_other_designs(data_file):
        USED_DESIGNS_SKIPPED.append(data_file.name)
        parents = [parent.name for parent in data_file.parentReferences if parent.fileExtension == 'f3d']
        log('Skipped: {} (used by {})'.format(get_project_path(data_file), ', '.join(parents)))
        return

    # The document name is known without opening the design, so existing files can be skipped early
    if name_option == 'Document name':
        extensions = [extension for type_name, extension in DESIGN_EXTENSIONS.items()
                      if is_type_selected(file_types, type_name)
                      and not (type_name == 'F3D' and data_file.hasChildReferences)]
        if all_exports_exist(data_file, output_folder, extensions, write_version):
            return

    document = open_doc(data_file)

    if document is None:
        record_failure(FAILED_FILES, data_file, 'could not be opened')
        return

    current_exports.clear()
    try:
        output_name = get_name(write_version, name_option)
        export_active_doc(output_folder, file_types, output_name)
        log_exports(data_file)

    except Exception as e:
        record_failure(FAILED_FILES, data_file, str(e))

    finally:
        close_doc(document)


def export_drawing_file(data_file, output_folder, drawing_types, write_version):
    """Open a drawing, export it to the selected types, and close it again."""
    extensions = [extension for type_name, (_, extension) in DRAWING_EXPORTS.items()
                  if is_type_selected(drawing_types, type_name)]
    if all_exports_exist(data_file, output_folder, extensions, write_version):
        return

    document = open_doc(data_file)

    if document is None:
        record_failure(FAILED_FILES, data_file, 'could not be opened')
        return

    current_exports.clear()
    try:
        # Drawings don't have a description or part number, so always use the document name
        output_name = get_document_name(write_version)
        export_drawing_doc(document, output_folder, drawing_types, output_name)
        log_exports(data_file)

    except Exception as e:
        record_failure(FAILED_FILES, data_file, str(e))

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
            record_format_failure(FAILED_FILES, "{}: {} export not available in this Fusion version".format(
                output_name, type_name))
            continue

        try:
            export_name = get_export_path(folder + output_name + extension)
            if export_name is None:
                continue
            export_options = getattr(export_mgr, factory_name)(export_name)

            if type_name == 'PDF':
                export_options.openPDF = False

            if not export_mgr.execute(export_options):
                record_format_failure(FAILED_FILES, "{}: {} export failed".format(output_name, type_name),
                                      export_name)

        except Exception as e:
            record_format_failure(FAILED_FILES, "{}: {} export error: {}".format(output_name, type_name, str(e)))


def export_electronics_file(data_file, output_folder, write_version):
    """Open an electronics document, export it to its EAGLE format, and close it again."""
    if all_exports_exist(data_file, output_folder, [ELECTRONICS_EXTENSIONS[data_file.fileExtension]], write_version):
        return

    document = open_doc(data_file)

    if document is None:
        record_failure(ELECTRONICS_ERRORS, data_file, 'could not be opened')
        return

    current_exports.clear()
    try:
        # Electronics docs are not design products, so the root_comp
        # based name options in get_name would fail. Use the document
        # name directly (optionally stripped of its version suffix).
        output_name = get_document_name(write_version)
        export_electronics_doc(output_folder, output_name)
        log_exports(data_file)
    except Exception as e:
        record_failure(ELECTRONICS_ERRORS, data_file, str(e))

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
    """Export the active design to each selected design type.

    F3D is exported first, as the design is. When include_hidden is set, hidden bodies and
    components are then shown for the other types, and hidden again afterward if the user
    already had the design open.
    """
    document = app.activeDocument
    design = get_active_design()
    export_mgr = design.exportManager

    if is_type_selected(file_types, 'F3D'):

        # The data file knows this even when the design was loaded in the background by an assembly,
        # where document.allDocumentReferences raises an error
        if document.dataFile.hasChildReferences:
            SKIPPED_FILES.append(document.name)
            log('Not exported as F3D: {} (references other designs; use File > Export in Fusion to save an F3Z)'
                .format(get_project_path(document.dataFile)))

        else:
            export_name = get_export_path(folder + output_name + '.f3d')
            if export_name is not None:
                export_options = export_mgr.createFusionArchiveExportOptions(export_name)
                export_mgr.execute(export_options)

    # Simple solid-body export types, keyed by the dropdown item name.
    solid_export_functions = {
        'IGES': (export_mgr.createIGESExportOptions, '.igs'),
        'STEP': (export_mgr.createSTEPExportOptions, '.step'),
        'SAT': (export_mgr.createSATExportOptions, '.sat'),
        'SMT': (export_mgr.createSMTExportOptions, '.smt'),
    }
    other_types = [type_name for type_name in list(solid_export_functions) + ['STL']
                   if is_type_selected(file_types, type_name)]
    if not other_types:
        return

    shown = show_hidden_geometry(design) if include_hidden else []
    if shown:
        log('Showed {} hidden bodies and components in {}'.format(len(shown), get_project_path(document.dataFile)))

    try:
        for type_name, (export_function, extension) in solid_export_functions.items():
            if type_name in other_types:
                export_name = get_export_path(folder + output_name + extension)
                if export_name is None:
                    continue
                export_options = export_function(export_name)
                export_mgr.execute(export_options)

        if 'STL' in other_types:
            stl_export_name = get_export_path(folder + output_name + '.stl')
            if stl_export_name is not None:
                stl_options = export_mgr.createSTLExportOptions(design.rootComponent, stl_export_name)
                export_mgr.execute(stl_options)

    finally:
        # Exported documents are closed without saving, but one the user already had open stays open
        if shown and get_data_file_id(document) in OPEN_BEFORE_EXPORT:
            hide_again(shown)


def show_hidden_geometry(design):
    """Show every hidden body and component at every level of a design.

    Turns on the bodies and Bodies folder of the root component and of every component
    occurrence, and the occurrences themselves, so nothing is left out of the export.
    Returns what was turned on, so it can be hidden again.
    """
    shown = []

    def turn_on(entity, light_bulb):
        try:
            if not getattr(entity, light_bulb):
                setattr(entity, light_bulb, True)
                shown.append((entity, light_bulb))
        except RuntimeError:
            # Some entities can't be changed, such as bodies in a referenced component
            pass

    root = design.rootComponent
    turn_on(root, 'isBodiesFolderLightBulbOn')
    for body in root.bRepBodies:
        turn_on(body, 'isLightBulbOn')

    for occurrence in root.allOccurrences:
        turn_on(occurrence, 'isLightBulbOn')
        turn_on(occurrence.component, 'isBodiesFolderLightBulbOn')

        # The occurrence's bodies are proxies, so this shows them in this occurrence of the component
        for body in occurrence.bRepBodies:
            turn_on(body, 'isLightBulbOn')

    return shown


def hide_again(shown):
    """Hide what show_hidden_geometry turned on."""
    for entity, light_bulb in reversed(shown):
        try:
            setattr(entity, light_bulb, False)
        except RuntimeError:
            pass


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
            record_format_failure(ELECTRONICS_ERRORS, "{}: {} export not available in this Fusion version".format(
                output_name, type_name))
            return

        export_name = get_export_path(folder + output_name + extension)
        if export_name is None:
            return

        export_options = getattr(export_mgr, factory_name)(export_name)

        # A None result means the factory was called on the wrong product type.
        if export_options is None:
            record_format_failure(ELECTRONICS_ERRORS, "{}: {} export options could not be created".format(
                output_name, type_name), export_name)
            return

        if not export_mgr.execute(export_options):
            record_format_failure(ELECTRONICS_ERRORS, "{}: {} export failed".format(output_name, type_name),
                                  export_name)

    except Exception as e:
        record_format_failure(ELECTRONICS_ERRORS, "{}: {} export error: {}".format(output_name, type_name, str(e)))


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


def get_project_path(data_file):
    """Return a data file's path within its project, such as "Folder/Subfolder/Design"."""
    names = [data_file.name]
    folder = data_file.parentFolder
    while folder is not None and folder.parentFolder is not None:
        names.insert(0, folder.name)
        folder = folder.parentFolder
    return '/'.join(names)


def log_exports(data_file):
    """Log the files written for a data file."""
    if current_exports:
        log('Exported: {} -> {}'.format(get_project_path(data_file),
                                         ', '.join(os.path.basename(path) for path in current_exports)))


def record_failure(failures, data_file, reason):
    """Record a file that couldn't be exported for the summary and the log."""
    failures.append("{}: {}".format(data_file.name, reason))
    log('Failed: {}: {}'.format(get_project_path(data_file), reason))


def record_format_failure(failures, message, export_path=None):
    """Record one export type of a file that failed, for the summary and the log."""
    failures.append(message)
    log('Failed: {}'.format(message))
    if export_path in current_exports:
        current_exports.remove(export_path)


def selected_type_names(file_types):
    """Return the names of the export types checked in a dropdown."""
    return [file_types.item(i).name for i in range(file_types.count) if file_types.item(i).isSelected]


def is_used_by_other_designs(data_file):
    """Return True if a design is inserted into another design, which is known without opening it.

    Drawings of a design also count as parent references, so only designs are considered.
    """
    if not data_file.hasParentReferences:
        return False

    return any(parent.fileExtension == 'f3d' for parent in data_file.parentReferences)


def get_export_path(path):
    """Return the path to export to, or None to skip it, based on the Existing files option."""
    if not os.path.exists(path):
        current_exports.append(path)
        return path

    if existing_files == EXISTING_FILES_SKIP:
        EXISTING_FILES_SKIPPED.append(path)
        log('Skipped: {} (already exists)'.format(os.path.basename(path)))
        return None

    if existing_files == EXISTING_FILES_OVERWRITE:
        os.remove(path)
        current_exports.append(path)
        return path

    path = dup_check(path)
    current_exports.append(path)
    return path


def all_exports_exist(data_file, folder, extensions, write_version):
    """With Skip existing files, return True if every export of a data file already exists.

    Uses the name the document will have when opened, so the file doesn't need to be opened.
    """
    if existing_files != EXISTING_FILES_SKIP or not extensions:
        return False

    name = data_file.name
    if write_version:
        name += ' v{}'.format(data_file.versionNumber)

    paths = [folder + sanitize_name(name) + extension for extension in extensions]
    if all(os.path.exists(path) for path in paths):
        EXISTING_FILES_SKIPPED.extend(paths)
        log('Skipped: {} (already exported)'.format(get_project_path(data_file)))
        return True

    return False


def get_document_name(write_version):
    """Derive an output name from the active document's name.

    Current Fusion versions don't include the version in the document name, so it's added
    from the data file when write_version is set. A trailing version suffix (e.g. " v3")
    that older Fusion versions included in the name is removed first.
    """
    document = app.activeDocument
    doc_name = re.sub(r' v\d+$', '', document.name)

    if write_version and document.dataFile is not None:
        doc_name += ' v{}'.format(document.dataFile.versionNumber)

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

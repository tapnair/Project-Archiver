# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Copyright (c) 2020 by Patrick Rainsberry.                                   ~
#  :license: Apache2, see LICENSE for more details.                            ~
#  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  SampleCommand2.py                                                           ~
#  This file is a component of Project-Archiver.                               ~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import os
import re
import time

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

import apper
from apper import AppObjects

import config

# Errors are collected during a run and shown in a single dialog at the end, so
# one bad document cannot abort an archive that may take hours to complete.
EXPORT_ERRORS = []
ELECTRONICS_ERRORS = []

# Documents that were already open when the run started. Closing them would
# discard whatever the user had open, so they are left alone.
PREEXISTING_DOCUMENTS = set()

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

# Characters Windows/macOS do not allow in a file name. A Fusion document name
# can legitimately contain any of these (e.g. "worm gear 30:1"), and passing
# them straight through to ExportManager raises RuntimeError: 3 ("The file name
# is not valid.", or "The selected folder does not exist." when a '/' makes the
# name look like a path).
ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name):
    """Replace characters that are illegal in file names with a dash."""
    return ILLEGAL_FILENAME_CHARS.sub('-', name)


def export_folder(root_folder, output_folder, file_types, write_version, name_option, folder_preserve,
                  include_hidden=False):
    for folder in root_folder.dataFolders:

        if folder_preserve:
            new_folder = os.path.join(output_folder, sanitize_filename(folder.name), "")

            if not os.path.exists(new_folder):
                os.makedirs(new_folder)
        else:
            new_folder = output_folder

        export_folder(folder, new_folder, file_types, write_version, name_option, folder_preserve,
                      include_hidden)

    for file in root_folder.dataFiles:
        if file.fileExtension == "f3d":
            if not open_doc(file):
                continue
            written_files = []
            hidden_changed = []
            try:
                if include_hidden:
                    hidden_changed = show_all_hidden(AppObjects().design)
                output_name = get_name(write_version, name_option)
                written_files = export_active_doc(output_folder, file_types, output_name)

            except Exception as e:
                # Record the failure and carry on with the next document. A
                # single unexportable file used to abort the whole run (or, for
                # AttributeError, every remaining file in the folder).
                EXPORT_ERRORS.append("{}: {}".format(file.name, str(e)))

            finally:
                # Restore visibility while this document is still the active one.
                if hidden_changed:
                    restore_hidden(hidden_changed)
                close_active_doc(wait_for_files=written_files)

        elif (HAS_ELECTRON and any_electronics_selected(file_types)
                and file.fileExtension in ELECTRONICS_EXTENSIONS):
            # Only open Fusion-native electronics documents (fprj/fsch/fbrd/flbr).
            # Opening unrelated hub files (drawings, etc.) and reading product
            # data on them raises Fusion's "failed to find product" error.
            if not open_doc(file):
                continue
            try:
                # Electronics docs are not design products, so the root_comp
                # based name options in get_name would fail. Use the document
                # name directly (optionally stripped of its version suffix).
                output_name = get_electronics_name(write_version)
                export_electronics_doc(output_folder, file_types, output_name)
            except Exception as e:
                ELECTRONICS_ERRORS.append("{}: {}".format(file.name, str(e)))
            finally:
                close_active_doc()


def open_doc(data_file):
    """Open and activate a data-panel file.

    Returns True on success. On failure the error is recorded and the caller
    skips the file: continuing here would export whichever document is still
    active under the wrong name.
    """
    app = adsk.core.Application.get()

    try:
        document = app.documents.open(data_file, True)
    except Exception as e:
        EXPORT_ERRORS.append("{}: could not be opened ({})".format(data_file.name, str(e)))
        return False

    if document is None:
        EXPORT_ERRORS.append("{}: could not be opened".format(data_file.name))
        return False

    # A failed activate() should not skip the file: the document may already be
    # the active one, and the export below does not depend on it.
    try:
        document.activate()
    except Exception:
        pass

    return True


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


def _run_export(export_mgr, export_name, type_name, create_options, written_files):
    """Create the export options and execute them, recording failures.

    Each format is attempted independently so that, for example, an STL export
    that Fusion cannot build does not stop the STEP export of the same document
    (or any later document).
    """
    try:
        export_options = create_options(export_name)
        if export_options is None:
            raise RuntimeError('export options could not be created')
        export_mgr.execute(export_options)
        written_files.append(export_name)
    except Exception as e:
        EXPORT_ERRORS.append("{} ({}): {}".format(os.path.basename(export_name), type_name, str(e)))


def export_active_doc(folder, file_types, output_name):
    """Export the active document to every selected format.

    Returns the list of paths written, so the caller can wait for those files
    to be flushed to disk before closing the document.
    """
    ao = AppObjects()
    export_mgr = ao.export_manager
    written_files = []

    # Simple solid-body export types, keyed by the dropdown item name.
    solid_export_functions = {
        'IGES': (export_mgr.createIGESExportOptions, '.igs'),
        'STEP': (export_mgr.createSTEPExportOptions, '.step'),
        'SAT': (export_mgr.createSATExportOptions, '.sat'),
        'SMT': (export_mgr.createSMTExportOptions, '.smt'),
    }

    for type_name, (export_function, extension) in solid_export_functions.items():
        if is_type_selected(file_types, type_name):
            export_name = dup_check(folder + output_name + extension)
            _run_export(export_mgr, export_name, type_name, export_function, written_files)

    if is_type_selected(file_types, 'F3D'):
        # A design with external references cannot be stored as a single .f3d.
        # Fusion archives it as .f3z, which bundles the referenced designs, so
        # ask for that extension instead of skipping the file (issues #22, #49).
        if ao.document.allDocumentReferences.count > 0:
            extension = '.f3z'
        else:
            extension = '.f3d'
        export_name = dup_check(folder + output_name + extension)
        _run_export(export_mgr, export_name, 'F3D',
                    export_mgr.createFusionArchiveExportOptions, written_files)

    if is_type_selected(file_types, 'STL'):
        stl_export_name = dup_check(folder + output_name + '.stl')
        _run_export(export_mgr, stl_export_name, 'STL',
                    lambda name: export_mgr.createSTLExportOptions(ao.design.rootComponent, name),
                    written_files)

    return written_files


def close_active_doc(wait_for_files=None, timeout=10.0):
    """Close the currently active document without saving.

    ExportManager.execute() is not documented to be fully synchronous for the
    on-disk write, and closing a document too early has been reported to crash
    Fusion or leave a truncated export. So when the paths that were just
    written are given, poll each file's size until it is stable across two
    checks before closing, capped at `timeout` seconds so a failed export
    cannot hang the whole batch.
    """
    if wait_for_files:
        if isinstance(wait_for_files, str):
            wait_for_files = [wait_for_files]
        deadline = time.time() + timeout
        for file_path in wait_for_files:
            last_size = -1
            while time.time() < deadline:
                try:
                    size = os.path.getsize(file_path)
                except OSError:
                    size = -1
                if size >= 0 and size == last_size:
                    break
                last_size = size
                time.sleep(0.5)

    app = adsk.core.Application.get()
    document = app.activeDocument
    if document is None:
        return

    # Never silently discard unsaved work in a document the user already had
    # open before the archive started.
    try:
        keep_open = document.isModified and document.name in PREEXISTING_DOCUMENTS
    except Exception:
        keep_open = False

    if keep_open:
        return

    try:
        document.close(False)
    except Exception:
        pass


def show_all_hidden(design):
    """Temporarily make every hidden body/occurrence visible for export.

    Fusion's exporters only include visible geometry, so hidden bodies would
    otherwise be silently missing from the archive. Returns the list of objects
    that were actually off, so the caller can restore exactly those afterwards.
    """
    changed = []

    def visit(component):
        for body in component.bRepBodies:
            if not body.isLightBulbOn:
                changed.append(body)
                body.isLightBulbOn = True
        for occurrence in component.occurrences:
            if not occurrence.isLightBulbOn:
                changed.append(occurrence)
                occurrence.isLightBulbOn = True
            visit(occurrence.component)

    visit(design.rootComponent)
    return changed


def restore_hidden(changed):
    """Undo show_all_hidden() - hide exactly what was hidden before."""
    for obj in changed:
        try:
            obj.isLightBulbOn = False
        except Exception:
            pass


def _export_one_electronics_format(product, type_name, folder, output_name):
    """Export a single electronics document to one EAGLE format.

    product: the electronics product (Board, Schematic, or Library)
    type_name: one of the keys in ELECTRONICS_EXPORTS ('BRD', 'SCH', 'LBR')

    The ElectronicsExportManager is a preview API, so we verify the factory
    method exists before calling it and tolerate any failure by recording it
    rather than aborting the whole archive run.
    """
    global ELECTRONICS_ERRORS

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

    app = adsk.core.Application.get()

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


def dup_check(name):
    """Return `name`, or the first `-dup` variant that does not exist yet."""
    if not os.path.exists(name):
        return name
    base, ext = os.path.splitext(name)
    return dup_check(base + '-dup' + ext)


def get_electronics_name(write_version):
    """Derive an output name for an electronics document.

    Electronics documents are not design products, so the Description / Part
    Number options (which read root_comp) do not apply. We always use the
    document name, optionally stripping the trailing version suffix to match
    the behavior of the 'Document Name' option.
    """
    app = adsk.core.Application.get()
    doc_name = app.activeDocument.name

    if not write_version:
        version_index = doc_name.rfind(' v')
        if version_index != -1:
            doc_name = doc_name[:version_index]

    return sanitize_filename(doc_name)


def get_name(write_version, option):
    ao = AppObjects()
    output_name = ''

    if option == 'Document Name':

        doc_name = ao.app.activeDocument.name

        if not write_version:
            version_index = doc_name.rfind(' v')
            if version_index != -1:
                doc_name = doc_name[:version_index]
        output_name = doc_name

    elif option == 'Description':
        output_name = ao.root_comp.description

    elif option == 'Part Number':
        output_name = ao.root_comp.partNumber

    else:
        raise ValueError('Something strange happened')

    # Description / Part Number are optional in Fusion, and an empty name would
    # produce a file called ".step" in the output folder. Fall back to the
    # document name instead.
    if not output_name or not output_name.strip():
        output_name = ao.app.activeDocument.name
        if not write_version:
            version_index = output_name.rfind(' v')
            if version_index != -1:
                output_name = output_name[:version_index]

    return sanitize_filename(output_name)


def update_name_inputs(command_inputs, selection):
    command_inputs.itemById('write_version').isVisible = False

    if selection == 'Document Name':
        command_inputs.itemById('write_version').isVisible = True


def report_errors(ui, output_folder, errors):
    """Show a bounded error dialog and write the full list beside the exports."""
    if not errors:
        return

    max_shown = 15
    message = "Some files could not be exported:\n\n{}".format("\n".join(errors[:max_shown]))
    if len(errors) > max_shown:
        message += "\n\n... and {} more.".format(len(errors) - max_shown)

    report_path = os.path.join(output_folder, 'Project-Archiver-errors.txt')
    try:
        with open(report_path, 'w', encoding='utf-8') as report:
            report.write("\n".join(errors))
        message += "\n\nFull list written to:\n{}".format(report_path)
    except OSError:
        pass

    ui.messageBox(message)


class ExportCommand(apper.Fusion360CommandBase):

    def on_input_changed(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs,
                         changed_input, input_values):
        if changed_input.id == 'name_option_id':
            update_name_inputs(inputs, changed_input.selectedItem.name)

    def on_execute(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs, args, input_values):
        ao = AppObjects()

        output_folder = (input_values['output_folder'] or '').strip()
        if not output_folder:
            ao.ui.messageBox('Please enter an output folder.')
            return

        folder_preserve = input_values['folder_preserve_id']
        include_hidden = input_values['include_hidden_id']

        # TODO broken?????
        file_types = inputs.itemById('file_types_input').listItems

        write_version = input_values['write_version']
        name_option = input_values['name_option_id']

        # data.activeProject raises RuntimeError: 2 (InternalValidationError)
        # when the Data Panel is not on a project, e.g. when no design is open
        # in the modelling workspace (issues #41, #52, #53).
        try:
            active_project = ao.app.data.activeProject
        except Exception:
            active_project = None

        if active_project is None:
            ao.ui.messageBox(
                'No active project was found.\n\n'
                'Open a design from the project you want to archive, then run '
                'Project-Archiver again.'
            )
            return

        root_folder = active_project.rootFolder

        # Make sure we have a folder not a file
        if not output_folder.endswith(os.path.sep):
            output_folder += os.path.sep

        # Create the base folder for this output if doesn't exist
        try:
            os.makedirs(output_folder, exist_ok=True)
        except OSError as e:
            ao.ui.messageBox('Could not create the output folder:\n{}'.format(str(e)))
            return

        # Remember what the user already had open so their unsaved work is not
        # closed (and discarded) by the per-document cleanup.
        PREEXISTING_DOCUMENTS.clear()
        try:
            documents = ao.app.documents
            for i in range(documents.count):
                PREEXISTING_DOCUMENTS.add(documents.item(i).name)
        except Exception:
            pass

        export_folder(root_folder, output_folder, file_types, write_version, name_option, folder_preserve,
                      include_hidden)

        errors = []
        if EXPORT_ERRORS:
            errors.append('Designs:')
            errors.extend(EXPORT_ERRORS)
        if ELECTRONICS_ERRORS:
            errors.append('Electronics documents:')
            errors.extend(ELECTRONICS_ERRORS)
        report_errors(ao.ui, output_folder, errors)

    def on_create(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs):
        EXPORT_ERRORS.clear()
        ELECTRONICS_ERRORS.clear()
        default_dir = apper.get_default_dir(config.app_name)

        inputs.addStringValueInput('output_folder', 'Output Folder:', default_dir)

        drop_input_list = inputs.addDropDownCommandInput('file_types_input', 'Export Types',
                                                         adsk.core.DropDownStyles.CheckBoxDropDownStyle)
        drop_input_list = drop_input_list.listItems
        drop_input_list.add('IGES', False)
        drop_input_list.add('STEP', True)
        drop_input_list.add('SAT', False)
        drop_input_list.add('SMT', False)
        drop_input_list.add('F3D', False)
        drop_input_list.add('STL', False)
        drop_input_list.add('BRD', False)
        drop_input_list.add('SCH', False)
        drop_input_list.add('LBR', False)

        name_option_group = inputs.addDropDownCommandInput('name_option_id', 'File Name Option',
                                                                   adsk.core.DropDownStyles.TextListDropDownStyle)
        name_option_group.listItems.add('Document Name', True)
        name_option_group.listItems.add('Description', False)
        name_option_group.listItems.add('Part Number', False)
        name_option_group.isVisible = True

        preserve_input = inputs.addBoolValueInput('folder_preserve_id', 'Preserve folder structure?', True, '', True)
        preserve_input.isVisible = True

        include_hidden_input = inputs.addBoolValueInput('include_hidden_id', 'Include hidden bodies/components?',
                                                       True, '', False)
        include_hidden_input.isVisible = True

        version_input = inputs.addBoolValueInput('write_version', 'Write versions to output file names?', True, '', False)
        version_input.isVisible = False

        update_name_inputs(inputs, 'Document Name')

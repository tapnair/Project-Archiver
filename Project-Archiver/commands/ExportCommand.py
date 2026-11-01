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

SKIPPED_FILES = []
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
    ao = AppObjects()

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
            open_doc(file)
            written_files = []
            hidden_changed = []
            try:
                if include_hidden:
                    hidden_changed = show_all_hidden(AppObjects().design)
                output_name = get_name(write_version, name_option)
                written_files = export_active_doc(output_folder, file_types, output_name)

            # TODO add handling
            except ValueError as e:
                ao.ui.messageBox(str(e))

            except AttributeError as e:
                ao.ui.messageBox(str(e))
                break

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
            open_doc(file)
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
    app = adsk.core.Application.get()

    try:
        document = app.documents.open(data_file, True)
        if document is not None:
            document.activate()
    except:
        pass
        # TODO add handling


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
    """Export the active document to every selected format.

    Returns the list of paths written, so the caller can wait for those files
    to be flushed to disk before closing the document.
    """
    global SKIPPED_FILES

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
            export_name = folder + output_name + extension
            export_name = dup_check(export_name)
            export_options = export_function(export_name)
            export_mgr.execute(export_options)
            written_files.append(export_name)

    if is_type_selected(file_types, 'F3D'):

        if ao.document.allDocumentReferences.count > 0:
            SKIPPED_FILES.append(ao.document.name)

        else:
            export_name = folder + output_name + '.f3d'
            export_name = dup_check(export_name)
            export_options = export_mgr.createFusionArchiveExportOptions(export_name)
            export_mgr.execute(export_options)
            written_files.append(export_name)

    if is_type_selected(file_types, 'STL'):
        stl_export_name = folder + output_name + '.stl'
        stl_options = export_mgr.createSTLExportOptions(ao.design.rootComponent, stl_export_name)
        export_mgr.execute(stl_options)
        written_files.append(stl_export_name)

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
    if document is not None:
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
    if os.path.exists(name):
        base, ext = os.path.splitext(name)
        base += '-dup'
        name = base + ext
        dup_check(name)
    return name


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

    return sanitize_filename(output_name)


def update_name_inputs(command_inputs, selection):
    command_inputs.itemById('write_version').isVisible = False

    if selection == 'Document Name':
        command_inputs.itemById('write_version').isVisible = True


class ExportCommand(apper.Fusion360CommandBase):

    def on_input_changed(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs,
                         changed_input, input_values):
        if changed_input.id == 'name_option_id':
            update_name_inputs(inputs, changed_input.selectedItem.name)

    def on_execute(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs, args, input_values):
        global SKIPPED_FILES
        global ELECTRONICS_ERRORS
        ao = AppObjects()

        output_folder = input_values['output_folder']
        folder_preserve = input_values['folder_preserve_id']
        include_hidden = input_values['include_hidden_id']

        # TODO broken?????
        file_types = inputs.itemById('file_types_input').listItems

        write_version = input_values['write_version']
        name_option = input_values['name_option_id']
        root_folder = ao.app.data.activeProject.rootFolder

        # Make sure we have a folder not a file
        if not output_folder.endswith(os.path.sep):
            output_folder += os.path.sep

        # Create the base folder for this output if doesn't exist
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        export_folder(root_folder, output_folder, file_types, write_version, name_option, folder_preserve,
                      include_hidden)

        if len(SKIPPED_FILES) > 0:
            ao.ui.messageBox(
                "The following files contained external references and could not be exported as f3d's: {}".format(
                    SKIPPED_FILES
                )
            )

        if len(ELECTRONICS_ERRORS) > 0:
            ao.ui.messageBox(
                "Some electronics documents could not be exported:\n{}".format(
                    "\n".join(ELECTRONICS_ERRORS)
                )
            )

        close_command = ao.ui.commandDefinitions.itemById(self.fusion_app.command_id_from_name(config.close_cmd_id))
        close_command.execute()

    def on_create(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs):
        global SKIPPED_FILES
        global ELECTRONICS_ERRORS
        SKIPPED_FILES.clear()
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

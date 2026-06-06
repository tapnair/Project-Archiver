# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Copyright (c) 2020 by Patrick Rainsberry.                                   ~
#  :license: Apache2, see LICENSE for more details.                            ~
#  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  SampleCommand2.py                                                           ~
#  This file is a component of Project-Archiver.                               ~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import os
import json
import time
import traceback

import adsk.core
import adsk.fusion
import adsk.cam

import apper
from apper import AppObjects

import config

SKIPPED_FILES = []

# --- Tuning constants for large projects ---
BATCH_SIZE        = 5     # files per batch before a cooldown pause
BATCH_COOLDOWN    = 2.0   # seconds to pause between batches
OPEN_SETTLE_TIME  = 0.3   # seconds after closing a doc before opening next
PROGRESS_FILE     = 'archiver_progress.json'  # saved in output folder

# Named constants for export format indices — prevents silent breakage
# if list order ever changes
EXPORT_FORMATS = {
    'iges': {'index': 0, 'ext': '.igs',  'dir': 'iges'},
    'step': {'index': 1, 'ext': '.step', 'dir': 'step'},
    'sat':  {'index': 2, 'ext': '.sat',  'dir': 'sat'},
    'smt':  {'index': 3, 'ext': '.smt',  'dir': 'smt'},
    'f3d':  {'index': 4, 'ext': '.f3d',  'dir': 'f3d'},
    'stl':  {'index': 5, 'ext': '.stl',  'dir': 'stl'},
}


def save_progress(output_folder, completed_ids, skipped_names):
    """Saves completed file IDs to disk so a crash can be resumed."""
    progress_path = os.path.join(output_folder, PROGRESS_FILE)
    try:
        with open(progress_path, 'w') as f:
            json.dump({'completed': list(completed_ids), 'skipped': skipped_names}, f)
    except Exception:
        pass


def load_progress(output_folder):
    """Loads previously completed file IDs. Returns (set, list) or (empty set, [])."""
    progress_path = os.path.join(output_folder, PROGRESS_FILE)
    try:
        if os.path.exists(progress_path):
            with open(progress_path, 'r') as f:
                data = json.load(f)
            return set(data.get('completed', [])), data.get('skipped', [])
    except Exception:
        pass
    return set(), []


def clear_progress(output_folder):
    """Removes the progress file after a successful full run."""
    progress_path = os.path.join(output_folder, PROGRESS_FILE)
    try:
        if os.path.exists(progress_path):
            os.remove(progress_path)
    except Exception:
        pass


def collect_f3d_files(data_folder):
    """
    Recursively collects all F3D DataFile objects into a flat list.
    Much faster than counting first then re-traversing — single pass only.
    Uses doEvents to prevent UI freezing during deep scans.
    Returns: list of (data_file, relative_path) tuples
    """
    results = []
    _collect_recursive(data_folder, "", results)
    return results


def _collect_recursive(data_folder, relative_path, results, progress_dialog=None):
    adsk.doEvents()

    if progress_dialog:
        folder_display = relative_path if relative_path else '(root)'
        progress_dialog.message = (
            f'Scanning: {folder_display}  —  {len(results)} files found so far...'
        )
        adsk.doEvents()

    try:
        for j in range(data_folder.dataFolders.count):
            try:
                folder = data_folder.dataFolders.item(j)
                if folder:
                    _collect_recursive(
                        folder,
                        os.path.join(relative_path, folder.name),
                        results,
                        progress_dialog
                    )
            except Exception:
                pass

        for i in range(data_folder.dataFiles.count):
            try:
                file = data_folder.dataFiles.item(i)
                if file and file.fileExtension == "f3d":
                    results.append((file, relative_path))
                    if progress_dialog:
                        progress_dialog.message = (
                            f'Scanning: {relative_path or "(root)"}  —  {len(results)} files found so far...'
                        )
                        adsk.doEvents()
            except Exception:
                pass
    except Exception:
        pass


def should_skip_file(data_file, base_output, relative_path, file_types, write_version, name_option):
    """
    Returns True if all selected export formats already exist for this file.
    Avoids opening the document at all if nothing needs exporting.
    Only works for 'Document Name' mode (predictable filename without opening doc).
    """
    if name_option != 'Document Name':
        return False

    file_name = data_file.name.replace("/", "_")
    predicted_name = (
        file_name + ' v' + str(data_file.latestVersionNumber)
        if write_version else file_name
    )

    for fmt_name, fmt in EXPORT_FORMATS.items():
        idx = fmt['index']
        # Skip F3D and STL (handled separately at end of export_doc)
        if idx >= file_types.count - 2:
            continue
        if file_types.item(idx).isSelected:
            check_path = os.path.join(base_output, fmt['dir'], relative_path, predicted_name + fmt['ext'])
            if not os.path.exists(check_path):
                return False

    # Also check F3D and STL (last two)
    if file_types.item(file_types.count - 2).isSelected:
        check_path = os.path.join(base_output, 'f3d', relative_path, predicted_name + '.f3d')
        if not os.path.exists(check_path):
            return False

    if file_types.item(file_types.count - 1).isSelected:
        check_path = os.path.join(base_output, 'stl', relative_path, predicted_name + '.stl')
        if not os.path.exists(check_path):
            return False

    return True


def open_doc(data_file):
    app = adsk.core.Application.get()
    try:
        document = app.documents.open(data_file, False)
        return document
    except Exception:
        return None


def export_doc(document, base_output, relative_path, file_types, output_name):
    global SKIPPED_FILES

    design = adsk.fusion.Design.cast(document.products.itemByProductType('DesignProductType'))
    if not design:
        return

    export_mgr = design.exportManager

    export_functions = [
        export_mgr.createIGESExportOptions,
        export_mgr.createSTEPExportOptions,
        export_mgr.createSATExportOptions,
        export_mgr.createSMTExportOptions,
        export_mgr.createFusionArchiveExportOptions,
        export_mgr.createSTLExportOptions,
    ]

    # Export standard formats (all except last two: F3D and STL)
    standard_formats = list(EXPORT_FORMATS.values())[:-2]  # iges, step, sat, smt
    for fmt in standard_formats:
        idx = fmt['index']
        if not file_types.item(idx).isSelected:
            continue
        format_dir = os.path.join(base_output, fmt['dir'], relative_path, "")
        os.makedirs(format_dir, exist_ok=True)
        export_path = format_dir + output_name + fmt['ext']
        if not os.path.exists(export_path):
            try:
                export_options = export_functions[idx](export_path)
                export_mgr.execute(export_options)
            except Exception:
                pass

    # F3D export (second-to-last): skip files with external references
    f3d_idx = file_types.count - 2
    if file_types.item(f3d_idx).isSelected:
        if document.allDocumentReferences.count > 0:
            SKIPPED_FILES.append(document.name)
        else:
            format_dir = os.path.join(base_output, 'f3d', relative_path, "")
            os.makedirs(format_dir, exist_ok=True)
            export_path = format_dir + output_name + '.f3d'
            if not os.path.exists(export_path):
                try:
                    export_options = export_mgr.createFusionArchiveExportOptions(export_path)
                    export_mgr.execute(export_options)
                except Exception:
                    pass

    # STL export (last)
    stl_idx = file_types.count - 1
    if file_types.item(stl_idx).isSelected:
        format_dir = os.path.join(base_output, 'stl', relative_path, "")
        os.makedirs(format_dir, exist_ok=True)
        export_path = format_dir + output_name + '.stl'
        if not os.path.exists(export_path):
            if design and design.rootComponent:
                try:
                    stl_options = export_mgr.createSTLExportOptions(design.rootComponent, export_path)
                    export_mgr.execute(stl_options)
                except Exception:
                    pass


def get_name(document, write_version, option):
    output_name = ''

    if option == 'Document Name':
        doc_name = document.name
        if not write_version and ' v' in doc_name:
            doc_name = doc_name[:doc_name.rfind(' v')]
        output_name = doc_name

    elif option in ('Description', 'Part Number'):
        design = adsk.fusion.Design.cast(document.products.itemByProductType('DesignProductType'))
        if design and design.rootComponent:
            output_name = (
                design.rootComponent.description
                if option == 'Description'
                else design.rootComponent.partNumber
            )
        # Fallback to document name if description/part number is empty
        if not output_name:
            doc_name = document.name
            if not write_version and ' v' in doc_name:
                doc_name = doc_name[:doc_name.rfind(' v')]
            output_name = doc_name
    else:
        raise ValueError(f'Unknown name option: {option!r}')

    return output_name.replace("/", "_")


def update_name_inputs(command_inputs, selection):
    version_input = command_inputs.itemById('write_version')
    if version_input:
        version_input.isVisible = (selection == 'Document Name')


class ExportCommand(apper.Fusion360CommandBase):

    def on_input_changed(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs,
                         changed_input, input_values):
        if changed_input.id == 'name_option_id':
            update_name_inputs(inputs, changed_input.selectedItem.name)

    def on_execute(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs, args, input_values):
        global SKIPPED_FILES
        SKIPPED_FILES.clear()  # Clear here, not in on_create

        ao = AppObjects()
        app = adsk.core.Application.get()
        ui = app.userInterface
        progress_dialog = None

        try:
            output_folder    = input_values['output_folder']
            folder_preserve  = input_values['folder_preserve_id']
            file_types       = inputs.itemById('file_types_input').listItems
            write_version    = input_values['write_version']
            name_option      = input_values['name_option_id']
            root_folder      = ao.app.data.activeProject.rootFolder

            if not output_folder.endswith(os.path.sep):
                output_folder += os.path.sep
            os.makedirs(output_folder, exist_ok=True)

            # Show progress dialog immediately
            progress_dialog = ui.createProgressDialog()
            progress_dialog.cancelButtonText = 'Cancel'
            progress_dialog.isBackgroundDependent = False
            progress_dialog.show('Project Archiver', 'Scanning project folders...', 0, 1, 0)
            adsk.doEvents()

            # Single-pass collection: gather all files AND their paths at once
            # This is faster than count-then-traverse (old approach did 2 full traversals)
            all_files = collect_f3d_files(root_folder)
            total_files = max(len(all_files), 1)

            progress_dialog.maximumValue = total_files
            progress_dialog.progressValue = 0
            progress_dialog.message = 'Preparing to export...'
            adsk.doEvents()

            # Resume support: load previously completed file IDs
            completed_ids, prev_skipped = load_progress(output_folder)
            SKIPPED_FILES.extend(prev_skipped)

            is_resuming = len(completed_ids) > 0
            if is_resuming:
                progress_dialog.message = f'Resuming — {len(completed_ids)} files already done, skipping...'
                adsk.doEvents()

            exported = 0
            skipped  = 0

            for idx, (data_file, rel_path) in enumerate(all_files):
                if progress_dialog.wasCancelled:
                    save_progress(output_folder, completed_ids, SKIPPED_FILES)
                    break

                # Update UI responsiveness every file
                progress_dialog.progressValue = idx
                progress_dialog.message = f'Exporting ({idx + 1}/{total_files}): {data_file.name}...'
                adsk.doEvents()

                effective_path = rel_path if folder_preserve else ""

                # Resume: skip files already done in a previous run
                file_id = data_file.id
                if file_id in completed_ids:
                    skipped += 1
                    continue

                # Fast pre-check: skip opening doc if all outputs exist on disk
                if should_skip_file(data_file, output_folder, effective_path, file_types, write_version, name_option):
                    skipped += 1
                    completed_ids.add(file_id)
                    continue

                document = open_doc(data_file)
                if not document:
                    continue

                try:
                    output_name = get_name(document, write_version, name_option)
                    export_doc(document, output_folder, effective_path, file_types, output_name)
                    exported += 1
                    completed_ids.add(file_id)
                except (ValueError, AttributeError) as e:
                    ui.messageBox(str(e))
                    if isinstance(e, AttributeError):
                        break
                finally:
                    # Always close, even if export failed partway
                    try:
                        document.close(False)
                    except Exception:
                        pass
                    # Settle time — lets F360 release memory before next open
                    adsk.doEvents()
                    time.sleep(OPEN_SETTLE_TIME)
                    adsk.doEvents()

                # Batch cooldown: pause every BATCH_SIZE files to prevent memory buildup
                if exported > 0 and exported % BATCH_SIZE == 0:
                    save_progress(output_folder, completed_ids, SKIPPED_FILES)
                    progress_dialog.message = (
                        f'Cooling down after batch ({exported}/{total_files} done)...'
                    )
                    adsk.doEvents()
                    time.sleep(BATCH_COOLDOWN)
                    adsk.doEvents()

            # Save final progress state
            save_progress(output_folder, completed_ids, SKIPPED_FILES)
            progress_dialog.hide()

            if SKIPPED_FILES:
                ui.messageBox(
                    "The following files had external references and could not be exported as F3D:\n\n" +
                    "\n".join(SKIPPED_FILES)
                )

            if not progress_dialog.wasCancelled:
                clear_progress(output_folder)  # clean up — full run succeeded
                summary = f"Archiving complete!\n\nExported: {exported} files"
                if skipped > 0:
                    summary += f"\nSkipped (already up to date): {skipped} files"
                ui.messageBox(summary)

        except Exception:
            if progress_dialog:
                try:
                    progress_dialog.hide()
                except Exception:
                    pass
            # Save progress so the run can be resumed after fixing the crash
            try:
                save_progress(output_folder, completed_ids, SKIPPED_FILES)
            except Exception:
                pass
            ui.messageBox(
                "Project Archiver encountered an unexpected error.\n"
                "Progress has been saved — rerun to resume where it left off.\n\n"
                + traceback.format_exc(),
                "Export Halted"
            )

        finally:
            try:
                close_cmd_id = self.fusion_app.command_id_from_name(config.close_cmd_id)
                close_command = ui.commandDefinitions.itemById(close_cmd_id)
                if close_command:
                    close_command.execute()
            except Exception:
                pass

    def on_create(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs):
        # Note: SKIPPED_FILES is cleared in on_execute, not here,
        # to avoid clearing state if the dialog is opened but cancelled.
        default_dir = apper.get_default_dir(config.app_name)

        inputs.addStringValueInput('output_folder', 'Output Folder:', default_dir)

        drop_input_list = inputs.addDropDownCommandInput(
            'file_types_input', 'Export Types',
            adsk.core.DropDownStyles.CheckBoxDropDownStyle
        )
        items = drop_input_list.listItems
        items.add('IGES', False)
        items.add('STEP', True)
        items.add('SAT',  False)
        items.add('SMT',  False)
        items.add('F3D',  False)
        items.add('STL',  False)

        name_option_group = inputs.addDropDownCommandInput(
            'name_option_id', 'File Name Option',
            adsk.core.DropDownStyles.TextListDropDownStyle
        )
        name_option_group.listItems.add('Document Name', True)
        name_option_group.listItems.add('Description',   False)
        name_option_group.listItems.add('Part Number',   False)

        preserve_input = inputs.addBoolValueInput('folder_preserve_id', 'Preserve folder structure?', True, '', True)
        preserve_input.isVisible = True

        version_input = inputs.addBoolValueInput('write_version', 'Write versions to output file names?', True, '', False)
        version_input.isVisible = False  # shown dynamically via update_name_inputs

        update_name_inputs(inputs, 'Document Name')
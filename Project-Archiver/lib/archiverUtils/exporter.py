#  Copyright (c) 2019-2026 Patrick Rainsberry
#  Licensed under the Apache License, Version 2.0. See LICENSE for details.

"""Exports the documents in a Fusion project or folder to local files.

An export runs in these steps:

1. collect_exports walks the folders and lists the files to export, without opening any.
2. Each file is opened, exported to every selected type, and closed again right away, so
   Fusion's memory doesn't grow with the size of the project. A progress dialog shows how far
   the export has got and lets the user cancel between files.
3. The Close all documents command then closes any documents still loaded, such as designs an
   assembly referenced, and calls finish_export to show the summary. Showing a message box
   while exported documents are still open can fail, which is why the summary waits for this.
"""

import os
import re

import adsk.core
import adsk.fusion

# Feature-detect the Electronics and Drawing APIs. Older Fusion versions don't have them, and
# importing them unconditionally would stop the add-in from loading at all on those versions.
try:
    import adsk.electron
    HAS_ELECTRON = True
except ImportError:
    HAS_ELECTRON = False

try:
    import adsk.drawing
    HAS_DRAWING = True
except ImportError:
    HAS_DRAWING = False

from . import document_utils
from .export_options import (DESIGN_EXTENSIONS, DESIGN_FILE_EXTENSION, DRAWING_EXPORTS, DRAWING_FILE_EXTENSION,
                             ELECTRONICS_EXPORTS, EXISTING_FILES_OVERWRITE, EXISTING_FILES_SKIP,
                             EXPORTED_FILE_EXTENSIONS, NAME_DESCRIPTION, NAME_DOCUMENT, NAME_PART_NUMBER,
                             ExportOptions, ExportResults)
from .file_utils import dup_check, sanitize_name
from .log_utils import LOG_FILE_NAME, end_log, log, start_log

app = adsk.core.Application.get()
ui = app.userInterface

# The export that Close all documents is cleaning up after, or None
pending_export = None


def export(options: ExportOptions):
    """Export with the given options. Close all documents finishes it by calling finish_export."""
    global pending_export
    pending_export = Exporter(options)
    pending_export.run()


def get_keep_version_ids():
    """Return the documents Close all documents should leave open: the ones the user had open
    before the export it's cleaning up after, or none when it isn't cleaning up after an export."""
    return pending_export.open_before_export if pending_export else frozenset()


def finish_export():
    """Called when Close all documents is done. Shows the summary of the export it cleaned up after."""
    global pending_export
    if pending_export:
        pending_export.show_summary()
        pending_export = None


class Exporter:
    """Exports a project or folder with one set of options, and collects the results."""

    def __init__(self, options: ExportOptions):
        self.options = options
        self.results = ExportResults()

        # Version ids of the documents the user already had open, which are left open
        self.open_before_export = frozenset()

        # Paths written for the file currently being exported, for the log
        self.current_exports = []

        # The workspace Fusion switched to when the current file was opened, to tell a
        # workspace switch from the user clicking Cancel
        self.opened_in_workspace = None

    # ----------------------------------------------------------------------------------------
    # Running the export
    # ----------------------------------------------------------------------------------------

    def run(self):
        """Export every document in the active project, or in options.data_folder and its subfolders."""
        options = self.options
        project = document_utils.get_active_project()
        root_folder = options.data_folder or project.rootFolder
        folder_path = document_utils.get_folder_path(root_folder)

        # Versions of a design would otherwise export to the same file name
        if options.all_versions:
            options.write_version = True

        # A folder's files go under its path in the project, where a whole-project export would put
        # them, so folder-by-folder exports build up the same archive. The log stays at the top.
        log_folder = os.path.join(options.output_folder, '')
        output_folder = log_folder
        if options.preserve_folders and folder_path:
            output_folder = os.path.join(log_folder, *[sanitize_name(name) for name in folder_path], '')
        os.makedirs(output_folder, exist_ok=True)

        self.open_before_export = frozenset(document_utils.get_open_version_ids())

        start_log(log_folder, [
            'Project: {}'.format(project.name),
            'Folder: {}'.format('/'.join(folder_path) if folder_path else 'whole project'),
            'Output folder: {}'.format(output_folder),
            'Design export types: {}'.format(', '.join(options.design_types) or 'none'),
            'Drawing export types: {}'.format(', '.join(options.drawing_types) or 'none'),
            'Export electronics documents: {}'.format(yes_no(HAS_ELECTRON and options.export_electronics)),
            'File name option: {}{}'.format(options.name_option, ', with versions' if options.write_version else ''),
            'Preserve folder structure: {}'.format(yes_no(options.preserve_folders)),
            'Existing files: {}'.format(options.existing_files),
            'Skip designs used by other designs: {}'.format(yes_no(options.skip_used_designs)),
            'Include hidden bodies and components: {}'.format(yes_no(options.include_hidden)),
            'Export all versions: {}'.format(yes_no(options.all_versions)),
        ])

        exports = self.collect_exports(root_folder, output_folder)
        if exports:
            if options.all_versions and not self.confirm_all_versions(exports):
                self.results.declined = True
                log('Cancelled before exporting: {} versions to export'.format(len(exports)))
            else:
                self.export_with_progress(exports)

        end_log(self.get_summary_messages() or ['Every file was exported.'])

    def collect_exports(self, data_folder, output_folder):
        """List the files to export in a folder and its subfolders, without opening any of them.

        Returns (export method, data file, output folder) for each file, so the total is known for
        the progress dialog. Creates the output folders and logs the files that aren't exported.
        """
        options = self.options
        exports = []

        for folder in data_folder.dataFolders:
            new_folder = output_folder
            if options.preserve_folders:
                new_folder = os.path.join(output_folder, sanitize_name(folder.name), '')
                os.makedirs(new_folder, exist_ok=True)

            exports += self.collect_exports(folder, new_folder)

        for data_file in data_folder.dataFiles:
            extension = data_file.fileExtension

            if extension == DESIGN_FILE_EXTENSION and options.design_types:
                for version in document_utils.get_versions(data_file, options.all_versions):
                    exports.append((self.export_design_file, version, output_folder))

            elif HAS_DRAWING and extension == DRAWING_FILE_EXTENSION and options.drawing_types:
                for version in document_utils.get_versions(data_file, options.all_versions):
                    exports.append((self.export_drawing_file, version, output_folder))

            # Electronics documents are only exported at their latest version, since opening one
            # loads its whole electronics design
            elif HAS_ELECTRON and options.export_electronics and extension in ELECTRONICS_EXPORTS:
                exports.append((self.export_electronics_file, data_file, output_folder))

            elif extension in EXPORTED_FILE_EXTENSIONS:
                log('Not exported: {} (export type not selected)'.format(self.project_path(data_file)))

            else:
                log('Not exported: {} (.{} files aren\'t exported)'.format(self.project_path(data_file), extension))

        return exports

    def confirm_all_versions(self, exports):
        """Ask the user to confirm an all-versions export, showing how many files it will write."""
        documents = len({data_file.id for _, data_file, _ in exports})

        files = 0
        for export_method, _, _ in exports:
            if export_method == self.export_design_file:
                files += len(self.options.design_types)
            elif export_method == self.export_drawing_file:
                files += len(self.options.drawing_types)
            else:
                files += 1

        result = ui.messageBox(
            'This will export {} versions of {} documents, about {} files.\n\n'
            'Exporting every version can take much longer than exporting only the latest versions. '
            'Continue?'.format(len(exports), documents, files),
            'Export all versions',
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.QuestionIconType
        )
        return result == adsk.core.DialogResults.DialogYes

    def export_with_progress(self, exports):
        """Export each file, showing progress with a Cancel button that stops before the next file."""
        progress = show_progress(len(exports), 0)
        workspace_changed = False

        try:
            for index, (export_method, data_file, output_folder) in enumerate(exports):
                if progress.wasCancelled:
                    # Opening some documents, such as electronics documents, switches Fusion to another
                    # workspace, which closes the progress dialog and reports it as cancelled. Only a
                    # cancel without a workspace change came from the user.
                    if not workspace_changed:
                        self.results.cancelled = (index, len(exports))
                        log('Cancelled after {} of {} files'.format(index, len(exports)))
                        break

                    progress.hide()
                    progress = show_progress(len(exports), index)

                progress.message = 'Exporting %v of %m: {}'.format(self.project_path(data_file))
                progress.progressValue = index

                workspace = ui.activeWorkspace.id
                self.opened_in_workspace = workspace
                export_method(data_file, output_folder)
                workspace_changed = self.opened_in_workspace != workspace

            else:
                progress.progressValue = len(exports)

        finally:
            progress.hide()

    # ----------------------------------------------------------------------------------------
    # Exporting one file
    # ----------------------------------------------------------------------------------------

    def export_design_file(self, data_file, output_folder):
        """Open a design, export it to each selected design type, and close it again."""
        options = self.options

        # Whether a design is used by others is known without opening it
        if options.skip_used_designs and document_utils.is_used_by_other_designs(data_file):
            self.results.used_designs_skipped.add(data_file.id)
            parents = [parent.name for parent in data_file.parentReferences if parent.fileExtension == 'f3d']
            log('Skipped: {} (used by {})'.format(self.project_path(data_file), ', '.join(parents)))
            return

        # The output name is known without opening the design when it's the document name
        if options.name_option == NAME_DOCUMENT:
            extensions = [extension for type_name, extension in DESIGN_EXTENSIONS.items()
                          if type_name in options.design_types
                          and not (type_name == 'F3D' and data_file.hasChildReferences)]
            if self.all_exports_exist(data_file, output_folder, extensions):
                return

        self.export_opened(data_file, lambda document: self.export_design(document, output_folder))

    def export_drawing_file(self, data_file, output_folder):
        """Open a drawing, export it to each selected drawing type, and close it again."""
        extensions = [DRAWING_EXPORTS[type_name][1] for type_name in self.options.drawing_types]
        if self.all_exports_exist(data_file, output_folder, extensions):
            return

        self.export_opened(data_file, lambda document: self.export_drawing(document, output_folder))

    def export_electronics_file(self, data_file, output_folder):
        """Open an electronics document, export it to its EAGLE format, and close it again."""
        extension = ELECTRONICS_EXPORTS[data_file.fileExtension][1]
        if self.all_exports_exist(data_file, output_folder, [extension]):
            return

        self.export_opened(data_file, lambda document: self.export_electronics(data_file, output_folder))

    def export_opened(self, data_file, export_document):
        """Open a data file, call export_document with its document, and close it again.

        A file that fails is recorded and skipped, so the rest of the project is still exported.
        Documents the user already had open are left open.
        """
        document = document_utils.open_data_file(data_file)
        self.opened_in_workspace = ui.activeWorkspace.id
        if document is None:
            self.record_failure(data_file, 'could not be opened')
            return

        self.current_exports.clear()
        try:
            export_document(document)
            self.log_exports(data_file)

        except Exception as e:
            self.record_failure(data_file, str(e))

        finally:
            if document_utils.get_version_id(document) not in self.open_before_export:
                document_utils.close_document(document)

    # ----------------------------------------------------------------------------------------
    # Exporting the open document
    # ----------------------------------------------------------------------------------------

    def export_design(self, document, folder):
        """Export the active design to each selected design type.

        F3D is exported first, as the design is. With include_hidden, hidden bodies and
        components are then shown for the other types, and hidden again afterward if the user
        already had the design open.
        """
        options = self.options
        design = document_utils.get_active_design()
        if design is None:
            raise RuntimeError("the document isn't a design")
        export_mgr = design.exportManager
        output_name = self.get_design_name(design)

        if 'F3D' in options.design_types:
            # An F3D of a design that references other designs only links to them, and Fusion
            # can't open it on its own. The API can't create an F3Z, so these are skipped.
            # The data file knows this even when the design was loaded in the background by an
            # assembly, where document.allDocumentReferences raises an error.
            if document.dataFile.hasChildReferences:
                self.results.f3d_skipped.append(self.project_path(document.dataFile))
                log('Not exported as F3D: {} (references other designs; use File > Export in Fusion to save an F3Z)'
                    .format(self.project_path(document.dataFile)))
            else:
                export_name = self.get_export_path(folder + output_name + DESIGN_EXTENSIONS['F3D'])
                if export_name is not None:
                    export_mgr.execute(export_mgr.createFusionArchiveExportOptions(export_name))

        # The other types export the root component, and leave out anything hidden
        create_options = {
            'IGES': export_mgr.createIGESExportOptions,
            'STEP': export_mgr.createSTEPExportOptions,
            'SAT': export_mgr.createSATExportOptions,
            'SMT': export_mgr.createSMTExportOptions,
            'STL': lambda filename: export_mgr.createSTLExportOptions(design.rootComponent, filename),
        }
        other_types = [type_name for type_name in create_options if type_name in options.design_types]
        if not other_types:
            return

        shown = document_utils.show_hidden_geometry(design) if options.include_hidden else []
        if shown:
            log('Showed {} hidden bodies and components in {}'.format(len(shown),
                                                                       self.project_path(document.dataFile)))

        try:
            for type_name in other_types:
                export_name = self.get_export_path(folder + output_name + DESIGN_EXTENSIONS[type_name])
                if export_name is not None:
                    export_mgr.execute(create_options[type_name](export_name))

        finally:
            # Exported documents are closed without saving, but one the user already had open stays open
            if shown and document_utils.get_version_id(document) in self.open_before_export:
                document_utils.hide_again(shown)

    def export_drawing(self, document, folder):
        """Export a drawing to each selected drawing type. Each type is one file containing every sheet.

        A type that fails is recorded and the remaining types are still exported.
        """
        # Drawings don't have a description or part number, so always use the document name
        output_name = self.get_document_name()

        # A drawing isn't available through document.products, only through the drawing document
        export_mgr = adsk.drawing.DrawingDocument.cast(document).drawing.exportManager

        for type_name in self.options.drawing_types:
            factory_name, extension = DRAWING_EXPORTS[type_name]
            if not hasattr(export_mgr, factory_name):
                self.record_type_failure('{}: {} export not available in this Fusion version'.format(
                    output_name, type_name))
                continue

            try:
                export_name = self.get_export_path(folder + output_name + extension)
                if export_name is None:
                    continue

                export_options = getattr(export_mgr, factory_name)(export_name)
                if type_name == 'PDF':
                    export_options.openPDF = False

                if not export_mgr.execute(export_options):
                    self.record_type_failure('{}: {} export failed'.format(output_name, type_name), export_name)

            except Exception as e:
                self.record_type_failure('{}: {} export error: {}'.format(output_name, type_name, e))

    def export_electronics(self, data_file, folder):
        """Export the active electronics document (a board, schematic or library) to its EAGLE format.

        The Electronics API is a preview API, so the export method is checked before it's used.
        """
        # Electronics documents don't have a description or part number, so always use the document name
        output_name = self.get_document_name()
        factory_name, extension = ELECTRONICS_EXPORTS[data_file.fileExtension]

        product = app.activeProduct
        electronics_product = (adsk.electron.Board.cast(product) or adsk.electron.Schematic.cast(product)
                               or adsk.electron.Library.cast(product))
        export_mgr = electronics_product.exportManager if electronics_product else None

        if export_mgr is None or not hasattr(export_mgr, factory_name):
            self.record_type_failure('{}: export not available in this Fusion version'.format(output_name))
            return

        export_name = self.get_export_path(folder + output_name + extension)
        if export_name is None:
            return

        # The export options are None if the document isn't the expected type of electronics document
        export_options = getattr(export_mgr, factory_name)(export_name)
        if export_options is None or not export_mgr.execute(export_options):
            self.record_type_failure('{}: export failed'.format(output_name), export_name)

    # ----------------------------------------------------------------------------------------
    # Output names and paths
    # ----------------------------------------------------------------------------------------

    def get_document_name(self):
        """Return an output name from the active document's name, with the version if write_version is set.

        Current Fusion versions don't include the version in the document name, so it comes from
        the data file. A trailing " v3" that older Fusion versions included is removed first.
        """
        document = app.activeDocument
        name = strip_version(document.name)

        if self.options.write_version and document.dataFile is not None:
            name += ' v{}'.format(document.dataFile.versionNumber)

        return sanitize_name(name)

    def get_design_name(self, design):
        """Return an output name for a design using the File name option.

        Falls back to the document name when the description or part number is empty.
        """
        option = self.options.name_option
        if option == NAME_DESCRIPTION:
            name = sanitize_name(design.rootComponent.description)
        elif option == NAME_PART_NUMBER:
            name = sanitize_name(design.rootComponent.partNumber)
        else:
            return self.get_document_name()

        if not name:
            return self.get_document_name()

        if self.options.write_version:
            name += ' v{}'.format(app.activeDocument.dataFile.versionNumber)

        return name

    def get_export_path(self, path):
        """Return the path to export to, or None to skip it, based on the Existing files option."""
        if os.path.exists(path):
            if self.options.existing_files == EXISTING_FILES_SKIP:
                self.results.existing_skipped.append(path)
                log('Skipped: {} (already exists)'.format(os.path.basename(path)))
                return None

            if self.options.existing_files == EXISTING_FILES_OVERWRITE:
                os.remove(path)
            else:
                path = dup_check(path)

        self.current_exports.append(path)
        return path

    def all_exports_exist(self, data_file, folder, extensions):
        """With Skip existing files, return True if every export of a data file already exists.

        Uses the name the document will have when opened, so it doesn't need to be opened.
        """
        if self.options.existing_files != EXISTING_FILES_SKIP or not extensions:
            return False

        name = strip_version(data_file.name)
        if self.options.write_version:
            name += ' v{}'.format(data_file.versionNumber)

        paths = [folder + sanitize_name(name) + extension for extension in extensions]
        if all(os.path.exists(path) for path in paths):
            self.results.existing_skipped.extend(paths)
            log('Skipped: {} (already exported)'.format(self.project_path(data_file)))
            return True

        return False

    def project_path(self, data_file):
        """Return a data file's path within its project for messages, with the version when exporting all versions."""
        return document_utils.get_project_path(data_file, self.options.all_versions)

    # ----------------------------------------------------------------------------------------
    # Results
    # ----------------------------------------------------------------------------------------

    def log_exports(self, data_file):
        """Log the files written for a data file."""
        if self.current_exports:
            self.results.exported_files += len(self.current_exports)
            log('Exported: {} -> {}'.format(self.project_path(data_file),
                                             ', '.join(os.path.basename(path) for path in self.current_exports)))

    def record_failure(self, data_file, reason):
        """Record a file that couldn't be exported, for the summary and the log."""
        self.results.failed.append('{}: {}'.format(data_file.name, reason))
        log('Failed: {}: {}'.format(self.project_path(data_file), reason))

    def record_type_failure(self, message, export_path=None):
        """Record one export type of a file that failed, for the summary and the log."""
        self.results.failed.append(message)
        log('Failed: {}'.format(message))
        if export_path in self.current_exports:
            self.current_exports.remove(export_path)

    def get_summary_messages(self):
        """Return the messages that summarize what wasn't exported."""
        results = self.results
        messages = []

        if results.declined:
            messages.append('The export was cancelled before any files were exported.')

        if results.cancelled:
            messages.append('The export was cancelled after {} of {} files. Run it again with Existing files set to '
                            'Skip existing files to continue where it stopped.'.format(*results.cancelled))

        if results.used_designs_skipped:
            messages.append('{} designs used by other designs were skipped.'.format(len(results.used_designs_skipped)))

        if results.existing_skipped:
            messages.append('{} files already existed in the output folder and were skipped.'.format(
                len(results.existing_skipped)))

        if results.f3d_skipped:
            messages.append(
                "These designs reference other designs, so they weren't exported as F3D:\n{}\n\n"
                "An F3D of a design like this only links to the referenced designs and can't be opened on its own. "
                "The other export types were still exported, and each referenced design gets its own F3D. "
                "To keep a design with everything it references, open it and use File > Export to save an F3Z.".format(
                    '\n'.join(results.f3d_skipped)))

        if results.failed:
            messages.append('The following files could not be exported:\n{}'.format('\n'.join(results.failed)))

        return messages

    def show_summary(self):
        """Show what wasn't exported, once the exported documents have been closed."""
        messages = self.get_summary_messages()
        if messages:
            messages.append('Details for every file are in {} in the output folder.'.format(LOG_FILE_NAME))

        for message in messages:
            ui.messageBox(message)


def show_progress(total, value):
    """Show the export progress dialog with a Cancel button.

    Updating the dialog after each file is enough for Fusion to handle its Cancel button while
    the export runs; no adsk.doEvents() call is needed.
    """
    progress = ui.createProgressDialog()
    progress.isCancelButtonShown = True
    progress.cancelButtonText = 'Cancel'
    progress.show('Project Archiver', 'Exporting %v of %m', 0, total)
    progress.progressValue = value
    return progress


def strip_version(name):
    """Remove a trailing version suffix such as " v3" from a document name."""
    return re.sub(r' v\d+$', '', name)


def yes_no(value):
    return 'yes' if value else 'no'


def selected_type_names(list_items: adsk.core.ListItems):
    """Return the names of the items checked in a check box dropdown."""
    return [list_items.item(i).name for i in range(list_items.count) if list_items.item(i).isSelected]


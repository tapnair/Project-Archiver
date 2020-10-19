# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Copyright (c) 2020 by Patrick Rainsberry.                                   ~
#  :license: Apache2, see LICENSE for more details.                            ~
#  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  SampleCommand2.py                                                           ~
#  This file is a component of Project-Archiver.                               ~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import os

import adsk.core
import adsk.fusion
import adsk.cam

import apper
from apper import AppObjects

import config
import traceback

FILES_WITH_EXTERNAL_REFS = []
FAILED_FILES = []
SKIPPED_DUP_FILES = []

def export_folder(root_folder, output_folder, file_types, write_version, export_all_versions, skip_duplicates, name_option, folder_preserve):
    ao = AppObjects()

    for folder in root_folder.dataFolders:

        if folder_preserve:
            new_folder = os.path.join(output_folder, folder.name, "")

            if not os.path.exists(new_folder):
                os.makedirs(new_folder)
        else:
            new_folder = output_folder

        export_folder(folder, new_folder, file_types, write_version, export_all_versions, skip_duplicates, name_option, folder_preserve)

    # Set styles of progress dialog.
    app = adsk.core.Application.get()
    ui  = app.userInterface
    progressDialog = ui.createProgressDialog()
    progressDialog.isBackgroundTranslucent = False
    progressDialog.cancelButtonText = 'Cancel'
    progressDialog.isCancelButtonShown = True

    # Show progress dialog
    progressDialog.show(root_folder.name, 'Processing %v of %m', 0, len(root_folder.dataFiles), 0)
    
    for data_file in root_folder.dataFiles:
        # Update progress value of progress dialog
        progressDialog.progressValue += 1
        if progressDialog.wasCancelled:
            stop_here_error
            break
        adsk.doEvents()
        
        # TODO: Priority=low: Improve progress metering for larger projects when exporting all versions
        # Refactor this outer loop so that a list of all files and versions is generated first, and then iterated on. 
            
        if data_file.fileExtension == "f3d":
            if export_all_versions:
                versions = data_file.versions
            else:
                versions = [ data_file ]
                
            for data_file_v in versions:
                # TODO: Priority=highest: Fix Main inner loop
                # This is the main inner loop and is very dirty. 
                # A duplicate check was placed here to speed up sync of large projects, but this breaks exports of non-f3d files
                # This dup_check, open_doc, export_doc, close_doc should be bubbled into 'export_data_file()'
                output_name = get_name2(data_file_v, write_version, name_option)
                export_name = output_folder + output_name + '.f3d' # This is dirty because it would skip exports for other file types
                export_name, dup = dup_check(export_name)
                if not (dup and skip_duplicates):
                    doc = open_doc(data_file_v)
                    try:
                        #output_name = get_name(write_version, name_option)
                        export_active_doc(output_folder, file_types, output_name, skip_duplicates)
                        close_doc( doc )

                    # TODO add handling
                    except ValueError as e:
                        ao.ui.messageBox('export_folder Failed:ValueError\n{}'.format(traceback.format_exc()))

                    except AttributeError as e:
                        FAILED_FILES.append(ao.document.name)
                        ao.ui.messageBox('export_folder Failed:AttributeError\n{}'.format(traceback.format_exc()))
    # Hide the progress dialog at the end.
    progressDialog.hide()
    adsk.doEvents()


def open_doc(data_file):
    # TODO: This often fails due to Runtime Error 3. Error Downloading. 
    # However, when ran again, it works. This function should be updated to retry at least once.
    app = adsk.core.Application.get()

    try:
        document = app.documents.open(data_file, True)
        if document is not None:
            document.activate()
            return document
    except:
        ao = AppObjects()
        ao.ui.messageBox('open_doc failed for file:{name}\n{tb}'.format(name=data_file.name,tb=traceback.format_exc()))

def close_doc( doc ):
    try:
        doc.close(False)
    except:
        ao = AppObjects()
        ao.ui.messageBox('close_doc Failed:\n{}'.format(traceback.format_exc()))

def export_active_doc(folder, file_types, output_name, skip_dups):
    global FILES_WITH_EXTERNAL_REFS
    
    ao = AppObjects()
    export_mgr = ao.export_manager

    export_functions = [export_mgr.createIGESExportOptions,
                        export_mgr.createSTEPExportOptions,
                        export_mgr.createSATExportOptions,
                        export_mgr.createSMTExportOptions,
                        export_mgr.createFusionArchiveExportOptions,
                        export_mgr.createSTLExportOptions]
    export_extensions = ['.igs', '.step', '.sat', '.smt', '.f3d', '.stl']

    for i in range(file_types.count-2):

        if file_types.item(i).isSelected:
            export_name = folder + output_name + export_extensions[i]
            export_name, dup = dup_check(export_name)
            if not (dup and skip_dups):
                export_options = export_functions[i](export_name)
                export_mgr.execute(export_options)

    if file_types.item(file_types.count - 2).isSelected:

        if ao.document.allDocumentReferences.count > 0:
            FILES_WITH_EXTERNAL_REFS.append(ao.document.name) # Why?

        export_name = folder + output_name + '.f3d'
        export_name, dup = dup_check(export_name)
        if not (dup and skip_dups):
            export_options = export_mgr.createFusionArchiveExportOptions(export_name)
            export_mgr.execute(export_options)
    
    if file_types.item(file_types.count - 1).isSelected:
        stl_export_name = folder + output_name + '.stl'
        stl_export_name, dup = dup_check(stl_export_name)
        if not (dup and skip_dups):
            stl_options = export_mgr.createSTLExportOptions(ao.design.rootComponent, stl_export_name)
            export_mgr.execute(stl_options)


def dup_check(name):
    dup = False
    if os.path.exists(name):
        SKIPPED_DUP_FILES.append(name)
        base, ext = os.path.splitext(name)
        base += '-dup'
        name = base + ext
        dup_check(name)
        dup = True
    return name, dup


def get_name(write_version, option):
    ao = AppObjects()
    output_name = ''

    if option == 'Document Name':

        doc_name = ao.app.activeDocument.name
        
        if (doc_name.find('/') != -1):
          ao.ui.messageBox('Error: Filename has an illegal "/". You must rename this model:\n{}'.format(doc_name) )
          # TODO: Exit AddIn gracefully. 

        if not write_version:
            doc_name = doc_name[:doc_name.rfind(' v')]
        output_name = doc_name

    elif option == 'Description':
        output_name = ao.root_comp.description

    elif option == 'Part Number':
        output_name = ao.root_comp.partNumber

    else:
        raise ValueError('Something strange happened')

    return output_name
    
def get_name2(data_file, write_version, option):
    ao = AppObjects()
    output_name = ''

    if option == 'Document Name':

        doc_name = data_file.name + " v" + str(data_file.versionNumber)
        #ao.ui.messageBox('get_name2:data_file\n{}'.format(doc_name) )
                
        if (doc_name.find('/') != -1):
          ao.ui.messageBox('Error: Filename has an illegal "/". You must rename this model:\n{}'.format(doc_name) )
          # TODO: Exit AddIn gracefully. 

        if not write_version:
            doc_name = doc_name[:doc_name.rfind(' v')]
        output_name = doc_name

    elif option == 'Description':
        output_name = ao.root_comp.description

    elif option == 'Part Number':
        output_name = ao.root_comp.partNumber

    else:
        raise ValueError('Something strange happened')

    return output_name


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
        global FILES_WITH_EXTERNAL_REFS
        ao = AppObjects()
        
        project_folder = ao.app.data.activeProject.rootFolder

        output_folder = input_values['output_folder']
        folder_preserve = input_values['folder_preserve_id']
        file_types = inputs.itemById('file_types_input').listItems # TODO broken?????
        write_version = input_values['write_version']
        export_all_versions = input_values['export_all_versions']
        name_option = input_values['name_option_id']
        skip_duplicates = input_values['skip_duplicates']

        # Make sure we have a folder not a file
        if not output_folder.endswith(os.path.sep):
            output_folder += os.path.sep

        # Create the base folder for this output if doesn't exist
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        export_folder(project_folder, output_folder, file_types, write_version, export_all_versions, skip_duplicates, name_option, folder_preserve)

        # Report Final Results
        log_file_name = output_folder + 'export_log.txt'
        f = open( log_file_name, "a")
        f.write("- - - - - - Exporting Log Session - - - - - - \n")
        if len(FAILED_FILES) > 0:
            f.write("The following files Failed Export:\n")
            for f_n in FAILED_FILES:
                f.write("  {}\n".format(f_n))
        if len(FILES_WITH_EXTERNAL_REFS) > 0:
            f.write("The following files contained external references, be careful with these files and their references:\n")
            for f_n in FILES_WITH_EXTERNAL_REFS:
                f.write("  {}\n".format(f_n))
        if len(SKIPPED_DUP_FILES) > 0:
            f.write("The following files were skipped because they were duplicates:\n")
            for f_n in SKIPPED_DUP_FILES:
                f.write("  {}\n".format(f_n))        
        f.close()
        
        ao.ui.messageBox( "Finished Exporting:\n  Failed files:{fails}\n  SkippeddDuplicate Files:{dups}\n  Files with External References:{refs}\nSee export_log.txt".format(
          fails=len(FAILED_FILES),dups=len(SKIPPED_DUP_FILES),refs=len(FILES_WITH_EXTERNAL_REFS)
        ) )


    def on_create(self, command: adsk.core.Command, inputs: adsk.core.CommandInputs):
        global FILES_WITH_EXTERNAL_REFS
        FILES_WITH_EXTERNAL_REFS.clear()
        FAILED_FILES.clear()
        SKIPPED_DUP_FILES.clear()
        
        ao = AppObjects()
        default_dir = apper.get_default_dir(config.app_name) + ao.app.data.activeProject.rootFolder.name

        inputs.addStringValueInput('output_folder', 'Output Folder:', default_dir)

        drop_input_list = inputs.addDropDownCommandInput('file_types_input', 'Export Types',
                                                         adsk.core.DropDownStyles.CheckBoxDropDownStyle)
        drop_input_list = drop_input_list.listItems
        drop_input_list.add('IGES', False)
        drop_input_list.add('STEP', False)
        drop_input_list.add('SAT', False)
        drop_input_list.add('SMT', False)
        drop_input_list.add('F3D', True)
        drop_input_list.add('STL', False)

        name_option_group = inputs.addDropDownCommandInput('name_option_id', 'File Name Option',
                                                                   adsk.core.DropDownStyles.TextListDropDownStyle)
        name_option_group.listItems.add('Document Name', True)
        name_option_group.listItems.add('Description', False)
        name_option_group.listItems.add('Part Number', False)
        name_option_group.isVisible = True

        preserve_input = inputs.addBoolValueInput('folder_preserve_id', 'Preserve folder structure?', True, '', True)
        preserve_input.isVisible = True

        version_input = inputs.addBoolValueInput('write_version', 'Write versions to output file names?', True, '', True)
        version_input.isVisible = True
        
        all_versions_input = inputs.addBoolValueInput('export_all_versions', 'Export all versions?', True, '', True)
        all_versions_input.isVisible = True
        
        skip_duplicates_input = inputs.addBoolValueInput('skip_duplicates', 'Skip duplicates?', True, '', True)
        skip_duplicates_input.isVisible = True

        update_name_inputs(inputs, 'Document Name')

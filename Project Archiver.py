#Author- Patrick Rainsberry
#Description-This is sample addin showing how to export a project.
# Use at your own risk... this is neither official or supported.

import adsk.core, adsk.fusion, traceback
import os

from os.path import expanduser

MAX_PROJECTS = 20
        
commandName = 'ProjectArchiver'
commandDescription = 'Project Archiver'
commandResources = './resources'

cmdId = 'projectCommandOnPanel'


# global set of event handlers to keep them referenced for the duration of the command
handlers = []
    
def commandDefinitionById(id):
    app = adsk.core.Application.get()
    ui = app.userInterface
    if not id:
        ui.messageBox('commandDefinition id is not specified')
        return None
    commandDefinitions_ = ui.commandDefinitions
    commandDefinition_ = commandDefinitions_.itemById(id)
    return commandDefinition_

def commandControlByIdForPanel(id):
    app = adsk.core.Application.get()
    ui = app.userInterface
    if not id:
        ui.messageBox('commandControl id is not specified')
        return None
    workspaces_ = ui.workspaces
    modelingWorkspace_ = workspaces_.itemById('FusionSolidEnvironment')
    toolbarPanels_ = modelingWorkspace_.toolbarPanels
    toolbarPanel_ = toolbarPanels_.item(8)
    toolbarControls_ = toolbarPanel_.controls
    toolbarControl_ = toolbarControls_.itemById(id)
    return toolbarControl_

def destroyObject(uiObj, tobeDeleteObj):
    if uiObj and tobeDeleteObj:
        if tobeDeleteObj.isValid:
            tobeDeleteObj.deleteMe()
        else:
            uiObj.messageBox('tobeDeleteObj is not a valid object')

def exportFolder(rootFolder, outputFolder, file_types):
    for folder in rootFolder.dataFolders:
        exportFolder(folder, outputFolder)
    for file in rootFolder.dataFiles:
        if file.fileExtension == "f3d":
            openDoc(file, outputFolder, file_types)

def dupCheck(name):
    if os.path.exists(name):
        base, ext = os.path.splitext(name)
        base += '-dup'
        name = base + ext
        dupCheck(name)
    return name

# Creates directory and returns file name for settings file
def getFileName(projectName):

    # Get Home directory
    defaultPath = expanduser("~")
    defaultPath += '/ProjectArchiver/'
    defaultPath += projectName
    defaultPath += '/'
    # Create if doesn't exist
    if not os.path.exists(defaultPath):
        os.makedirs(defaultPath)
    
    return defaultPath    

def exportActiveDoc(outputFolder, file_types):

    app = adsk.core.Application.get()
    design = app.activeProduct 
    exportMgr = design.exportManager

    exportFunctions = [exportMgr.createIGESExportOptions, 
                       exportMgr.createSTEPExportOptions, 
                       exportMgr.createSATExportOptions, 
                       exportMgr.createSMTExportOptions, 
                       exportMgr.createFusionArchiveExportOptions,
                       exportMgr.createSTLExportOptions]
    export_extensions = ['.igs', '.step', '.sat', '.smt', '.f3d', '.stl']      
    
    for i in range(file_types.count):
        export_name = ' '
        if file_types.item(i).isSelected:
            export_name = outputFolder + app.activeDocument.name + export_extensions[i]
            export_name = dupCheck(export_name)
            exportOptions = exportFunctions[i](export_name)
            exportMgr.execute(exportOptions)

def openDoc(dataFile, outputFolder, file_types):
    app = adsk.core.Application.get()
    
    try:
        document = app.documents.open(dataFile, True)
        if document is not None:
            document.activate()
            exportActiveDoc(outputFolder, file_types)
            
            # Causes Fusion 360 to crash?
            # document.close(False)
    except:
        pass


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        class ExecutePreviewHandler(adsk.core.CommandEventHandler):
            def __init__(self):
                super().__init__()
            def notify(self, args):
                try:
                    command = args.firingEvent.sender
#                    ui.messageBox('Preview: {} execute preview event triggered'.format(command.parentCommandDefinition.id))
                except:
                    if ui:
                        ui.messageBox('Input changed event failed: {}'.format(traceback.format_exc()))

        class DestroyHandler(adsk.core.CommandEventHandler):
            def __init__(self):
                super().__init__()
            def notify(self, args):
                # Code to react to the event.
                try:
                    command = args.firingEvent.sender
#                    ui.messageBox('Command: {} destroyed'.format(command.parentCommandDefinition.id))
#                    ui.messageBox("Reason for termination= " + str(args.terminationReason))
                except:
                    if ui:
                        ui.messageBox('Input changed event failed: {}'.format(traceback.format_exc()))

        class InputChangedHandler(adsk.core.InputChangedEventHandler):
            def __init__(self):
                super().__init__()
            def notify(self, args):
                try:
                    command = args.firingEvent.sender
#                    ui.messageBox('Input: {} changed event triggered'.format(command.parentCommandDefinition.id))
                except:
                    if ui:
                        ui.messageBox('Input changed event failed: {}'.format(traceback.format_exc()))

        class CommandExecuteHandler(adsk.core.CommandEventHandler):
            def __init__(self):
                super().__init__()
            def notify(self, args):
                try:
                    
                    app = adsk.core.Application.get()
                    inputs = args.command.commandInputs
                    
                    outputPath = inputs.itemById('outputPath').value   
                    file_types = inputs.itemById('file_type_input').listItems
#                    # This is to implement selective export                   
#                    projectName = inputs.itemById('projectSelect').selectedItem.name  
#                    
#                    allProjects = app.data.dataProjects
#
#                    for project in allProjects:
#                        if project is not None:
#                            if project.name == projectName:
#                                exportProject = project
#                                break
                    
                    
                    exportFolder(app.data.activeProject.rootFolder, outputPath, file_types)
                
                except:
                    if ui:
                        ui.messageBox('command executed failed: {}'.format(traceback.format_exc()))

        class CommandCreatedEventHandlerPanel(adsk.core.CommandCreatedEventHandler):
            def __init__(self):
                super().__init__() 
            def notify(self, args):
                try:
                    cmd = args.command
                    
                    onExecute = CommandExecuteHandler()
                    cmd.execute.add(onExecute)
                    handlers.append(onExecute)
                    
                    onInputChanged = InputChangedHandler()
                    cmd.inputChanged.add(onInputChanged)
                    handlers.append(onInputChanged)
                    
                    onDestroy = DestroyHandler()
                    cmd.destroy.add(onDestroy)
                    handlers.append(onDestroy)
                    
                    onExecutePreview = ExecutePreviewHandler()
                    cmd.executePreview.add(onExecutePreview)
                    handlers.append(onExecutePreview)

                    app = adsk.core.Application.get()
#                    allProjects = app.data.dataProjects
                    activeProject = app.data.activeProject
                    projectName = activeProject.name
                    # Create a few inputs in the UI
                    commandInputs_ = cmd.commandInputs
                    projectSelect = commandInputs_.addStringValueInput('projectSelect', "Project to Archive: ", projectName)
                    projectSelect.isReadOnly = True
                    
                    defaultPath = getFileName(projectName)
                    commandInputs_.addStringValueInput('outputPath', 'Output Path: ', defaultPath)                    
                    
                    multiSelectionCommandInput_ = commandInputs_.addDropDownCommandInput('file_type_input', 'Export Types', adsk.core.DropDownStyles.CheckBoxDropDownStyle)

                    multiSelectionCommandInputListItems_ = multiSelectionCommandInput_.listItems
                    multiSelectionCommandInputListItems_.add('IGES', False)
                    multiSelectionCommandInputListItems_.add('STEP', True)
                    multiSelectionCommandInputListItems_.add('SAT', False)
                    multiSelectionCommandInputListItems_.add('SMT', False)
                    multiSelectionCommandInputListItems_.add('F3D', False)
                    multiSelectionCommandInputListItems_.add('STL', False)
            
            
                    


#                   THis creates a list of projects.  too slow.  Just using active.
#                    currentProject = 0
#                    for project in allProjects:
#                        if project is not None:
#                            projectSelect.listItems.add(project.name, False)
#                            currentProject += 1
#                            if currentProject >= MAX_PROJECTS:
#                                break


#                    ui.messageBox('Panel command created successfully')
                except:
                    if ui:
                        ui.messageBox('Panel command created failed: {}'.format(traceback.format_exc()))

        # Start actual Addin execution
        # Establish the command and add it to the UI
        commandDefinitions_ = ui.commandDefinitions

        # add a command on create panel in modeling workspace
        workspaces_ = ui.workspaces
        modelingWorkspace_ = workspaces_.itemById('FusionSolidEnvironment')
        toolbarPanels_ = modelingWorkspace_.toolbarPanels
        toolbarPanel_ = toolbarPanels_.item(8) # add the new command under the Addins panel
        toolbarControlsPanel_ = toolbarPanel_.controls
        toolbarControlPanel_ = toolbarControlsPanel_.itemById(cmdId)
        if not toolbarControlPanel_:
            commandDefinitionPanel_ = commandDefinitions_.itemById(cmdId)
            if not commandDefinitionPanel_:
                commandDefinitionPanel_ = commandDefinitions_.addButtonDefinition(cmdId, commandName, commandDescription, commandResources)
            onCommandCreated = CommandCreatedEventHandlerPanel()
            commandDefinitionPanel_.commandCreated.add(onCommandCreated)
            # keep the handler referenced beyond this function
            handlers.append(onCommandCreated)
            toolbarControlPanel_ = toolbarControlsPanel_.addCommand(commandDefinitionPanel_)
            toolbarControlPanel_.isVisible = True

    except:
        if ui:
            ui.messageBox('AddIn Start Failed: {}'.format(traceback.format_exc()))

def stop(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        objArray = []

        commandControlPanel_ = commandControlByIdForPanel(cmdId)
        if commandControlPanel_:
            objArray.append(commandControlPanel_)

        commandDefinitionPanel_ = commandDefinitionById(cmdId)
        if commandDefinitionPanel_:
            objArray.append(commandDefinitionPanel_)

        for obj in objArray:
            destroyObject(ui, obj)

    except:
        if ui:
            ui.messageBox('AddIn Stop Failed: {}'.format(traceback.format_exc()))

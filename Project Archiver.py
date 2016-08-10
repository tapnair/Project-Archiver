#Author-Autodesk Inc.
#Description-This is sample addin.

import adsk.core, adsk.fusion, traceback

MAX_PROJECTS = 10
        
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
    toolbarPanel_ = toolbarPanels_.item(0)
    toolbarControls_ = toolbarPanel_.controls
    toolbarControl_ = toolbarControls_.itemById(id)
    return toolbarControl_

def destroyObject(uiObj, tobeDeleteObj):
    if uiObj and tobeDeleteObj:
        if tobeDeleteObj.isValid:
            tobeDeleteObj.deleteMe()
        else:
            uiObj.messageBox('tobeDeleteObj is not a valid object')

def exportFolder(rootFolder, outputFolder):
    for folder in rootFolder.dataFolders:
        exportFolder(folder, outputFolder)
    for file in rootFolder.dataFiles:
        openDoc(file, outputFolder)
 
def exportActiveDoc(outputFolder):

    app = adsk.core.Application.get()
    design = app.activeProduct 
    exportMgr = design.exportManager

    export_name = outputFolder + app.activeDocument.name + '.stp'
    exportOptions = exportMgr.createSTEPExportOptions(export_name)
    exportMgr.execute(exportOptions)

def openDoc(dataFile, outputFolder):
    app = adsk.core.Application.get()
    
    try:
        document = app.documents.open(dataFile, True)
        if document is not None:
            document.activate()
            exportActiveDoc(outputFolder)
            
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
                    projectName = inputs.itemById('projectSelect').selectedItem.name  
                    
                    allProjects = app.data.dataProjects

                    for project in allProjects:
                        if project is not None:
                            if project.name == projectName:
                                exportProject = project
                                break
                    exportFolder(exportProject.rootFolder, outputPath)
                
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

                    # Create a few inputs in the UI
                    commandInputs_ = cmd.commandInputs
                    projectSelect = commandInputs_.addDropDownCommandInput('projectSelect', 'Select Project', 1)
                    commandInputs_.addStringValueInput('outputPath', 'Output Path: ')                    
                    
                    app = adsk.core.Application.get()
                    allProjects = app.data.dataProjects
                    
                    currentProject = 0
                    for project in allProjects:
                        if project is not None:
                            
                            projectSelect.listItems.add(project.name, False)
                            currentProject += 1
                            if currentProject >= MAX_PROJECTS:
                                break


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
        toolbarPanel_ = toolbarPanels_.item(0) # add the new command under the first panel
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

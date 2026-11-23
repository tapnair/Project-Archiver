#  Copyright (c) 2019-2026 Patrick Rainsberry
#  Licensed under the Apache License, Version 2.0. See LICENSE for details.

"""Checks for the Export Thumbnail option, using a stand-in for the Fusion API so no Fusion is needed.

Run from the repository root with:  python3 -m unittest discover -s tests -v

The stand-in only covers what the thumbnail code and the export dialog's inputs call. It is not
shipped with the add-in, and it can't show how Fusion itself draws or saves anything: see the
testing notes in the pull request for what still needs a try in Fusion.
"""

import copy
import importlib
import os
import shutil
import sys
import tempfile
import types
import unittest

ADDIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Project-Archiver')


# ------------------------------------------------------------------------------------------
# A minimal stand-in for adsk, installed before the add-in is imported
# ------------------------------------------------------------------------------------------

class StubMeta(type):
    """Any enum member, such as adsk.core.ViewOrientations.IsoTopRightViewOrientation, is its own name."""

    def __getattr__(cls, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return name


class Stub(metaclass=StubMeta):
    """Any adsk class the add-in only mentions in a type hint."""


class FakeCamera:
    def __init__(self, orientation='Original', smooth=True):
        self.viewOrientation = orientation
        self.isSmoothTransition = smooth


class FakeViewport:
    """Records what the design looked like each time an image is saved."""

    def __init__(self, app):
        self.app = app
        self.stored_camera = FakeCamera('UserView')
        self.fits = 0
        self.saved_images = []   # (path, width, height, snapshot of what was visible)
        self.save_result = True
        self.save_error = None

    @property
    def camera(self):
        return copy.copy(self.stored_camera)   # Fusion returns a copy

    @camera.setter
    def camera(self, camera):
        self.stored_camera = copy.copy(camera)

    def fit(self):
        self.fits += 1

    def saveAsImageFile(self, path, width, height):
        if self.save_error:
            raise self.save_error
        self.saved_images.append((path, width, height, self.app.design.snapshot(), self.stored_camera.viewOrientation))
        if self.save_result:
            open(path, 'wb').close()
        return self.save_result


class FakeBody:
    def __init__(self, visible=True):
        self.isLightBulbOn = visible


class FakeCanvas:
    def __init__(self, visible=True, locked=False):
        self._visible = visible
        self.locked = locked

    @property
    def isLightBulbOn(self):
        return self._visible

    @isLightBulbOn.setter
    def isLightBulbOn(self, value):
        if self.locked:
            raise RuntimeError('a canvas in a referenced component can\'t be changed')
        self._visible = value


class FakeComponent:
    """A component with a Bodies folder, a body, the folders of non-solid geometry, and canvases.

    Fusion has no folder property for canvases, so there isn't one here either.
    """

    def __init__(self, bodies_visible=True, body_visible=True):
        self.isBodiesFolderLightBulbOn = bodies_visible
        self.bRepBodies = [FakeBody(body_visible)]
        self.isSketchFolderLightBulbOn = True
        self.isConstructionFolderLightBulbOn = True
        self.isOriginFolderLightBulbOn = True
        self.isJointsFolderLightBulbOn = True
        self.isJointOriginsFolderLightBulbOn = True
        self.canvases = [FakeCanvas()]
        self.allOccurrences = []
        self.description = ''
        self.partNumber = ''


class FakeOccurrence:
    def __init__(self, visible=True, component=None):
        self.isLightBulbOn = visible
        self.component = component or FakeComponent()
        self.bRepBodies = [FakeBody(body.isLightBulbOn) for body in self.component.bRepBodies]


class FakeExportManager:
    def __init__(self, design):
        self.design = design

    def __getattr__(self, name):
        if name.startswith('create') and name.endswith('ExportOptions'):
            kind = name[len('create'):-len('ExportOptions')]
            return lambda *args: (kind, args[-1])
        raise AttributeError(name)

    def execute(self, options):
        kind, path = options
        self.design.exports.append((kind, path, self.design.snapshot()))
        open(path, 'wb').close()
        return True


class FakeDesign:
    """A root component with a visible body, and two components under it that are hidden in different ways."""

    def __init__(self):
        self.rootComponent = FakeComponent()
        self.hidden_component = FakeOccurrence(visible=False)
        self.hidden_body = FakeOccurrence(visible=True, component=FakeComponent(bodies_visible=False,
                                                                                body_visible=False))
        self.rootComponent.allOccurrences = [self.hidden_component, self.hidden_body]
        self.exportManager = FakeExportManager(self)
        self.exports = []

    def snapshot(self):
        """What is visible right now, for comparing before, during and after."""
        root = self.rootComponent
        state = {'root bodies': root.isBodiesFolderLightBulbOn, 'root body': root.bRepBodies[0].isLightBulbOn}
        for name in ('Sketch', 'Construction', 'Origin', 'Joints', 'JointOrigins'):
            state[name] = getattr(root, 'is{}FolderLightBulbOn'.format(name))
        state['Canvas'] = root.canvases[0].isLightBulbOn
        for index, occurrence in enumerate(root.allOccurrences):
            state['occurrence {}'.format(index)] = occurrence.isLightBulbOn
            state['occurrence {} folder'.format(index)] = occurrence.component.isBodiesFolderLightBulbOn
            state['occurrence {} body'.format(index)] = occurrence.bRepBodies[0].isLightBulbOn
            state['occurrence {} sketches'.format(index)] = occurrence.component.isSketchFolderLightBulbOn
            state['occurrence {} canvas'.format(index)] = occurrence.component.canvases[0].isLightBulbOn
        return state


class FakeDocument:
    def __init__(self, app, data_file, name):
        self.app = app
        self.dataFile = data_file
        self.name = name
        self.isSaved = True
        self.isValid = True
        self.closed_with = []
        self.products = types.SimpleNamespace(itemByProductType=lambda product_type: app.design)

    def activate(self):
        self.app.activeDocument = self

    def close(self, save_changes):
        self.closed_with.append(save_changes)
        if self in self.app.documents.open_documents:
            self.app.documents.open_documents.remove(self)
        return True

    def save(self, *args):
        raise AssertionError('The design must never be saved')

    saveAs = save


class FakeDocuments:
    def __init__(self, app):
        self.app = app
        self.open_documents = []
        self.opened = []

    @property
    def count(self):
        return len(self.open_documents)

    def item(self, index):
        return self.open_documents[index]

    def open(self, data_file, visible):
        document = FakeDocument(self.app, data_file, data_file.name)
        self.opened.append(document)
        self.open_documents.append(document)
        document.activate()
        return document


class FakePreferences:
    def __init__(self):
        self.isAutomaticSaveOnCloseEnabled = True
        self.isAutomaticVersioningEnabled = True
        self.history = []

    def __setattr__(self, name, value):
        if name != 'history' and hasattr(self, 'history'):
            self.history.append((name, value))
        object.__setattr__(self, name, value)


class FakeWorkspace:
    def __init__(self, ui, workspace_id):
        self.ui = ui
        self.id = workspace_id

    def activate(self):
        self.ui.activeWorkspace = self


class FakeUI:
    def __init__(self):
        self.activeWorkspace = FakeWorkspace(self, 'FusionSolidEnvironment')
        self.workspaces = types.SimpleNamespace(itemById=lambda workspace_id: FakeWorkspace(self, workspace_id))


class FakeApp:
    def __init__(self):
        self.userInterface = FakeUI()
        self.reset()

    def reset(self):
        self.design = FakeDesign()
        self.documents = FakeDocuments(self)
        self.activeDocument = None
        self.activeViewport = FakeViewport(self)
        self.preferences = types.SimpleNamespace(generalPreferences=FakePreferences())
        self.userInterface.activeWorkspace = FakeWorkspace(self.userInterface, 'FusionSolidEnvironment')
        self.log_lines = []

    def log(self, message, *args):
        self.log_lines.append(message)


def install_fake_adsk():
    fake_app = FakeApp()

    adsk = types.ModuleType('adsk')
    adsk.__path__ = []
    adsk.doEvents = lambda: None

    core = types.ModuleType('adsk.core')
    core.__getattr__ = lambda name: Stub
    core.Application = types.SimpleNamespace(get=lambda: fake_app)

    fusion = types.ModuleType('adsk.fusion')
    fusion.__getattr__ = lambda name: Stub
    fusion.Design = types.SimpleNamespace(cast=lambda product: product)

    adsk.core, adsk.fusion = core, fusion
    sys.modules.update({'adsk': adsk, 'adsk.core': core, 'adsk.fusion': fusion})
    return fake_app


def load_addin():
    """Import the add-in's modules as a package, since its folder name isn't a valid module name."""
    package = types.ModuleType('Project_Archiver')
    package.__path__ = [ADDIN_DIR]
    sys.modules['Project_Archiver'] = package
    return {name: importlib.import_module('Project_Archiver.lib.archiverUtils.' + name)
            for name in ('exporter', 'export_dialog', 'export_options', 'document_utils')}


fake_app = install_fake_adsk()
modules = load_addin()
exporter, export_dialog, export_options, document_utils = (
    modules[name] for name in ('exporter', 'export_dialog', 'export_options', 'document_utils'))


# ------------------------------------------------------------------------------------------
# The export dialog
# ------------------------------------------------------------------------------------------

class FakeInput:
    def __init__(self, input_id, name, value=None):
        self.id, self.name, self.value = input_id, name, value
        self.tooltip = ''
        self.isVisible = True
        self.isExpanded = True
        self.children = FakeInputs()
        self.listItems = types.SimpleNamespace(add=lambda *args: None)


class FakeInputs:
    """Records the inputs added to a dialog, in order."""

    def __init__(self):
        self.added = []

    def _add(self, input_id, name, value=None, *rest):
        self.added.append(FakeInput(input_id, name, value))
        return self.added[-1]

    addBoolValueInput = lambda self, input_id, name, is_check_box, icon, value: self._add(input_id, name, value)
    addTextBoxCommandInput = lambda self, input_id, name, text, *rest: self._add(input_id, name, text)
    addStringValueInput = lambda self, input_id, name, value: self._add(input_id, name, value)
    addDropDownCommandInput = lambda self, input_id, name, style: self._add(input_id, name)
    addGroupCommandInput = lambda self, input_id, name: self._add(input_id, name)

    def itemById(self, input_id):
        """Find an input, including inside groups like Fusion does."""
        for item in self.added:
            if item.id == input_id:
                return item
            found = item.children.itemById(input_id)
            if found:
                return found
        return None


class DialogTests(unittest.TestCase):
    def build_dialog(self):
        inputs = FakeInputs()
        export_dialog.add_export_inputs(inputs, 'Project:', 'Test', 'Hub', 'Test')
        return inputs

    def test_export_thumbnail_checkbox_follows_file_name_option(self):
        inputs = self.build_dialog()
        ids = [item.id for item in inputs.added]
        thumbnail = inputs.itemById('export_thumbnail')

        self.assertEqual(thumbnail.name, 'Export Thumbnail')
        self.assertIs(thumbnail.value, False)
        self.assertEqual(ids[ids.index('name_option') + 1], 'export_thumbnail')
        self.assertEqual(ids[ids.index('export_thumbnail') + 1], 'advanced_options')

    def test_unhide_checkbox_is_below_include_hidden_in_advanced_options(self):
        inputs = self.build_dialog()
        advanced_ids = [item.id for item in inputs.itemById('advanced_options').children.added]
        unhide = inputs.itemById('advanced_options').children.itemById('unhide_for_thumbnails')

        self.assertEqual(unhide.name, 'Unhide bodies for thumbnails?')
        self.assertIs(unhide.value, False)
        self.assertEqual(advanced_ids[advanced_ids.index('include_hidden') + 1], 'unhide_for_thumbnails')

    def test_options_are_read_from_the_dialog(self):
        inputs = FakeInputs()
        for input_id, value in (('output_folder', '/out/'), ('export_electronics', True), ('write_version', False),
                                ('preserve_folders', True), ('skip_used_designs', False), ('include_hidden', False),
                                ('all_versions', False), ('export_thumbnail', True),
                                ('unhide_for_thumbnails', True)):
            inputs.added.append(FakeInput(input_id, '', value))
        for input_id in ('design_types', 'drawing_types', 'name_option', 'existing_files'):
            item = FakeInput(input_id, '')
            item.selectedItem = types.SimpleNamespace(name='Document name')
            item.listItems = types.SimpleNamespace(count=0)
            inputs.added.append(item)

        options = export_dialog.get_export_options(inputs)

        self.assertTrue(options.export_thumbnail)
        self.assertTrue(options.unhide_for_thumbnails)
        self.assertTrue(export_dialog.inputs_are_valid(inputs), 'a thumbnail alone is something to export')
        inputs.itemById('export_thumbnail').value = False
        self.assertFalse(export_dialog.inputs_are_valid(inputs))


# ------------------------------------------------------------------------------------------
# Exporting a design
# ------------------------------------------------------------------------------------------

def make_data_file(name='Bracket', version=3, version_id='v3'):
    return types.SimpleNamespace(
        name=name, fileExtension='f3d', versionNumber=version, versionId=version_id, id='id-' + name,
        hasChildReferences=False, hasParentReferences=False, parentReferences=[],
        parentFolder=types.SimpleNamespace(parentFolder=None, name='root'))


class ThumbnailExportTests(unittest.TestCase):
    def setUp(self):
        fake_app.reset()
        self.folder = tempfile.mkdtemp() + os.sep
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.design = fake_app.design
        self.original = self.design.snapshot()

    def export(self, data_file=None, open_before=(), **option_values):
        values = dict(output_folder=self.folder, design_types=['STEP'], export_thumbnail=True)
        values.update(option_values)
        document_exporter = exporter.Exporter(export_options.ExportOptions(**values), frozenset(open_before))
        document_exporter.export_design_file(data_file or make_data_file(), self.folder)
        return document_exporter

    def images(self):
        return fake_app.activeViewport.saved_images

    def test_thumbnail_is_800_square_png_named_like_the_other_exports(self):
        document_exporter = self.export()

        path, width, height, _, orientation = self.images()[0]
        self.assertEqual((os.path.join(self.folder, 'Bracket.png'), 800, 800), (path, width, height))
        self.assertEqual(orientation, 'IsoTopRightViewOrientation')
        self.assertEqual(fake_app.activeViewport.fits, 1)
        self.assertEqual([export[1] for export in self.design.exports], [os.path.join(self.folder, 'Bracket.step')])
        self.assertEqual(document_exporter.results.exported_files, 2)
        self.assertFalse(document_exporter.results.failed)

    def test_name_follows_the_file_name_option_and_write_versions(self):
        self.design.rootComponent.description = 'Mounting bracket'
        self.design.rootComponent.partNumber = 'PN/100'
        cases = [
            (export_options.NAME_DOCUMENT, False, 'Bracket.png'),
            (export_options.NAME_DOCUMENT, True, 'Bracket v3.png'),
            (export_options.NAME_DESCRIPTION, False, 'Mounting bracket.png'),
            (export_options.NAME_DESCRIPTION, True, 'Mounting bracket v3.png'),
            (export_options.NAME_PART_NUMBER, False, 'PN-100.png'),
            (export_options.NAME_PART_NUMBER, True, 'PN-100 v3.png'),
        ]
        for name_option, write_version, expected in cases:
            with self.subTest(name_option=name_option, write_version=write_version):
                fake_app.reset()
                self.design = fake_app.design
                self.design.rootComponent.description = 'Mounting bracket'
                self.design.rootComponent.partNumber = 'PN/100'
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                document = fake_app.documents
                document.open_documents.clear()

                self.export(make_data_file(name='Bracket v3'), name_option=name_option, write_version=write_version)

                self.assertEqual(os.path.basename(self.images()[0][0]), expected)
                self.assertTrue(os.path.exists(os.path.join(self.folder, expected)))
                step_name = os.path.splitext(expected)[0] + '.step'
                self.assertEqual(os.path.basename(self.design.exports[0][1]), step_name)

    def test_empty_description_falls_back_to_the_document_name(self):
        self.export(name_option=export_options.NAME_DESCRIPTION, write_version=True)
        self.assertEqual(os.path.basename(self.images()[0][0]), 'Bracket v3.png')

    def test_no_thumbnail_unless_asked_for(self):
        document_exporter = self.export(export_thumbnail=False)

        self.assertEqual(self.images(), [])
        self.assertEqual(document_exporter.results.exported_files, 1)

    def test_solids_only_are_shown_and_hidden_items_stay_hidden_by_default(self):
        self.export()

        during = self.images()[0][3]
        for folder in ('Sketch', 'Construction', 'Origin', 'Joints', 'JointOrigins', 'Canvas'):
            self.assertFalse(during[folder], folder + ' should be hidden in the thumbnail')
        self.assertFalse(during['occurrence 0 canvas'])
        self.assertFalse(during['occurrence 1 canvas'])
        self.assertFalse(hasattr(self.design.rootComponent, 'isCanvasFolderLightBulbOn'),
                         'canvases are hidden one by one, not through a folder property Fusion doesn\'t have')
        self.assertFalse(during['occurrence 0'])
        self.assertFalse(during['occurrence 1 body'])
        self.assertFalse(during['occurrence 1 folder'])
        self.assertFalse(during['occurrence 1 sketches'])

    def test_only_the_canvases_that_were_visible_are_hidden_and_restored(self):
        root = self.design.rootComponent
        root.canvases = [FakeCanvas(visible=True), FakeCanvas(visible=False)]
        component = self.design.hidden_body.component
        component.canvases = [FakeCanvas(visible=True)]

        hidden = document_utils.hide_non_solid_geometry(self.design)

        self.assertEqual([root.canvases[0].isLightBulbOn, root.canvases[1].isLightBulbOn], [False, False])
        self.assertFalse(component.canvases[0].isLightBulbOn)
        self.assertEqual(sum(1 for entity, _ in hidden if isinstance(entity, FakeCanvas)), 3)

        document_utils.show_again(hidden)

        self.assertEqual([root.canvases[0].isLightBulbOn, root.canvases[1].isLightBulbOn], [True, False],
                         'the canvas that was already hidden stays hidden')
        self.assertTrue(component.canvases[0].isLightBulbOn)

    def test_a_canvas_that_cannot_be_changed_is_skipped(self):
        self.design.rootComponent.canvases = [FakeCanvas(locked=True), FakeCanvas()]

        document_exporter = self.export()

        self.assertEqual(len(self.images()), 1)
        self.assertFalse(document_exporter.results.failed)
        self.assertTrue(self.design.rootComponent.canvases[1].isLightBulbOn)

    def test_canvases_are_restored_for_an_already_open_design(self):
        data_file = make_data_file()
        fake_app.documents.open(data_file, True)

        self.export(data_file, open_before={data_file.versionId})

        self.assertEqual(self.design.snapshot(), self.original)

    def test_unhide_shows_hidden_bodies_and_components_for_the_thumbnail_only(self):
        self.export(unhide_for_thumbnails=True)

        during = self.images()[0][3]
        self.assertTrue(during['occurrence 0'])
        self.assertTrue(during['occurrence 1 body'])
        self.assertTrue(during['occurrence 1 folder'])
        self.assertFalse(during['Sketch'])

        step_state = self.design.exports[0][2]
        self.assertEqual(step_state, self.original, 'the other exports see the design as it is')
        self.assertEqual(self.design.snapshot(), self.original)

    def test_unhide_is_independent_of_include_hidden(self):
        self.export(include_hidden=True, unhide_for_thumbnails=False)

        self.assertFalse(self.images()[0][3]['occurrence 0'], 'include hidden must not show up in the thumbnail')
        self.assertTrue(self.design.exports[0][2]['occurrence 0'], 'include hidden still applies to the export')

    def test_visibility_and_view_are_restored_for_a_design_that_was_already_open(self):
        data_file = make_data_file()
        document = fake_app.documents.open(data_file, True)
        fake_app.documents.opened.clear()
        before_view = fake_app.activeViewport.stored_camera.viewOrientation

        self.export(data_file, open_before={data_file.versionId}, unhide_for_thumbnails=True)

        self.assertEqual(self.design.snapshot(), self.original)
        self.assertEqual(fake_app.activeViewport.stored_camera.viewOrientation, before_view)
        self.assertEqual(document.closed_with, [], 'a design the user had open stays open')

    def test_visibility_is_restored_even_when_the_capture_fails(self):
        fake_app.activeViewport.save_error = RuntimeError('capture failed')

        document_exporter = self.export(unhide_for_thumbnails=True)

        self.assertEqual(self.design.snapshot(), self.original)
        self.assertEqual(len(document_exporter.results.failed), 1)
        self.assertIn('thumbnail', document_exporter.results.failed[0])

    def test_a_failed_thumbnail_is_logged_and_the_design_is_still_exported(self):
        fake_app.activeViewport.save_result = False

        document_exporter = self.export()

        self.assertEqual([export[0] for export in self.design.exports], ['STEP'])
        self.assertEqual(document_exporter.results.exported_files, 1)
        self.assertEqual(len(document_exporter.results.failed), 1)

    def test_a_thumbnail_path_that_cannot_be_prepared_is_a_thumbnail_failure_only(self):
        # A directory with the PNG's name can't be overwritten: os.remove raises an OSError
        os.makedirs(os.path.join(self.folder, 'Bracket.png'))

        document_exporter = self.export(existing_files=export_options.EXISTING_FILES_OVERWRITE)

        self.assertEqual(self.images(), [], 'no picture is taken when the path can\'t be prepared')
        self.assertEqual([export[0] for export in self.design.exports], ['STEP'])
        self.assertEqual(len(document_exporter.results.failed), 1)
        self.assertIn('thumbnail export error', document_exporter.results.failed[0])
        self.assertEqual(self.design.snapshot(), self.original)
        self.assertEqual(fake_app.documents.opened[0].closed_with, [False])

    def test_a_protected_png_is_a_thumbnail_failure_only(self):
        open(os.path.join(self.folder, 'Bracket.png'), 'wb').close()
        real_remove = os.remove

        def refuse(path):
            if path.endswith('.png'):
                raise PermissionError('protected')
            real_remove(path)

        os.remove = refuse
        try:
            document_exporter = self.export(existing_files=export_options.EXISTING_FILES_OVERWRITE,
                                            design_types=['STEP', 'F3D'])
        finally:
            os.remove = real_remove

        self.assertEqual(sorted(export[0] for export in self.design.exports), ['FusionArchive', 'STEP'])
        self.assertEqual(len(document_exporter.results.failed), 1)
        self.assertEqual(document_exporter.results.exported_files, 2)

    def test_the_design_is_never_saved_and_exported_documents_are_closed_discarding_changes(self):
        self.export(unhide_for_thumbnails=True)

        (document,) = fake_app.documents.opened   # FakeDocument.save raises if it was ever called
        self.assertEqual(document.closed_with, [False])

    def test_thumbnail_alone_exports_each_design(self):
        document_exporter = self.export(design_types=[])

        self.assertEqual(len(self.images()), 1)
        self.assertEqual(self.design.exports, [])
        self.assertEqual(document_exporter.results.exported_files, 1)

    def test_existing_thumbnail_is_skipped_but_a_missing_one_is_added_to_an_earlier_export(self):
        open(os.path.join(self.folder, 'Bracket.step'), 'wb').close()

        self.export()

        self.assertEqual(len(self.images()), 1, 'the design is opened to add the missing thumbnail')

        fake_app.reset()
        self.export()
        self.assertEqual(fake_app.documents.opened, [], 'every export exists, so the design is not opened')

    def test_thumbnails_use_the_existing_files_option(self):
        open(os.path.join(self.folder, 'Bracket.png'), 'wb').close()

        self.export(design_types=['STEP'], existing_files=export_options.EXISTING_FILES_RENAME)

        self.assertEqual(os.path.basename(self.images()[0][0]), 'Bracket-dup.png')

    def test_the_design_workspace_is_activated_for_the_capture(self):
        fake_app.userInterface.activeWorkspace = FakeWorkspace(fake_app.userInterface, 'CAMEnvironment')

        self.export()

        self.assertEqual(fake_app.userInterface.activeWorkspace.id, 'FusionSolidEnvironment')

    def test_only_designs_are_collected_for_thumbnails(self):
        options = export_options.ExportOptions(output_folder=self.folder, design_types=[], export_thumbnail=True,
                                               export_electronics=False)
        drawing = make_data_file(name='Drawing')
        drawing.fileExtension = 'f2d'
        board = make_data_file(name='Board')
        board.fileExtension = 'fbrd'
        folder = types.SimpleNamespace(dataFolders=[], dataFiles=[make_data_file(), drawing, board])

        exports = exporter.Exporter(options).collect_exports(folder, self.folder)

        self.assertEqual([data_file.name for _, data_file, _ in exports], ['Bracket'])


class AutoSaveTests(unittest.TestCase):
    PREFERENCES = ('isAutomaticSaveOnCloseEnabled', 'isAutomaticVersioningEnabled')

    def setUp(self):
        fake_app.reset()
        self.preferences = fake_app.preferences.generalPreferences

    def set_preferences(self, save_on_close, versioning):
        self.preferences.isAutomaticSaveOnCloseEnabled = save_on_close
        self.preferences.isAutomaticVersioningEnabled = versioning
        self.preferences.history.clear()

    def current(self):
        return tuple(getattr(self.preferences, name) for name in self.PREFERENCES)

    def run_export(self, options, run, hub=False):
        """Run exporter.export (or export_hub) with an Exporter whose run does something chosen by the test."""
        class FakeExporter:
            def __init__(self, *args):
                pass

            def run(self):
                run()

        original = exporter.Exporter, exporter.HubExporter
        exporter.Exporter = exporter.HubExporter = FakeExporter
        try:
            if hub:
                exporter.export_hub(options, [])
            else:
                exporter.export(options)
        finally:
            exporter.Exporter, exporter.HubExporter = original
            exporter.pending_export = None

    def thumbnails(self):
        return export_options.ExportOptions(output_folder='/out/', export_thumbnail=True)

    def test_each_combination_is_off_during_the_export_and_back_as_it_was_after(self):
        for original in ((True, True), (False, False), (True, False), (False, True)):
            with self.subTest(original=original):
                self.set_preferences(*original)
                seen = []

                with document_utils.suspended_auto_save():
                    seen.append(self.current())

                self.assertEqual(seen, [(False, False)])
                self.assertEqual(self.current(), original)

    def test_a_preference_that_was_already_off_is_never_written(self):
        self.set_preferences(True, False)

        with document_utils.suspended_auto_save():
            pass

        self.assertEqual(self.preferences.history, [
            ('isAutomaticSaveOnCloseEnabled', False), ('isAutomaticSaveOnCloseEnabled', True)])

    def test_each_combination_is_restored_when_the_export_raises(self):
        for original in ((True, True), (False, False), (True, False), (False, True)):
            with self.subTest(original=original):
                self.set_preferences(*original)

                def fail():
                    self.assertEqual(self.current(), (False, False))
                    raise ValueError('export failed')

                with self.assertRaises(ValueError):
                    self.run_export(self.thumbnails(), fail)

                self.assertEqual(self.current(), original)

    def test_hub_export_restores_after_an_exception(self):
        self.set_preferences(True, True)

        def fail():
            raise ValueError('export failed')

        with self.assertRaises(ValueError):
            self.run_export(self.thumbnails(), fail, hub=True)

        self.assertEqual(self.current(), (True, True))

    def test_cancelled_export_restores_the_preferences(self):
        # A cancelled export stops between files and returns normally; the user closing the
        # dialog with Cancel at the progress dialog never leaves run
        for original in ((True, True), (True, False)):
            with self.subTest(original=original):
                self.set_preferences(*original)
                seen = []

                self.run_export(self.thumbnails(), lambda: seen.append(self.current()))

                self.assertEqual(seen, [(False, False)])
                self.assertEqual(self.current(), original)

    def test_preferences_are_restored_when_the_export_is_interrupted(self):
        self.set_preferences(True, True)

        def interrupt():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.run_export(self.thumbnails(), interrupt)

        self.assertEqual(self.current(), (True, True))

    def test_a_failure_while_turning_them_off_restores_the_one_already_off(self):
        self.set_preferences(True, True)

        class Failing(FakePreferences):
            def __setattr__(self, name, value):
                if name == 'isAutomaticVersioningEnabled' and value is False:
                    raise ValueError('unexpected')
                FakePreferences.__setattr__(self, name, value)

        failing = Failing()
        failing.history = []
        fake_app.preferences = types.SimpleNamespace(generalPreferences=failing)

        with self.assertRaises(ValueError):
            with document_utils.suspended_auto_save():
                self.fail('the export must not start')

        self.assertTrue(failing.isAutomaticSaveOnCloseEnabled)
        self.assertTrue(failing.isAutomaticVersioningEnabled)

    def test_preferences_are_left_alone_without_thumbnails(self):
        self.set_preferences(True, True)

        with document_utils.suspended_auto_save(False):
            pass
        self.run_export(export_options.ExportOptions(output_folder='/out/'), lambda: None)

        self.assertEqual(self.preferences.history, [])
        self.assertEqual(self.current(), (True, True))

    def test_preferences_that_cannot_be_read_are_skipped(self):
        class Unreadable:
            def __getattr__(self, name):
                raise RuntimeError('not available')

        fake_app.preferences = types.SimpleNamespace(generalPreferences=Unreadable())
        ran = []

        with document_utils.suspended_auto_save():
            ran.append(True)

        self.assertEqual(ran, [True])


if __name__ == '__main__':
    unittest.main()

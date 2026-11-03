#  Copyright (c) 2019-2026 Patrick Rainsberry
#  Licensed under the Apache License, Version 2.0. See LICENSE for details.

"""Helpers for finding, opening and closing Fusion documents and data files.

Opening and closing documents during a long export is where most of Fusion's quirks show up,
so this module collects what's been learned:

- Fusion sometimes raises "failed to find product" from an API call that actually succeeded,
  apparently reporting an error from work it's still doing in the background. Opening and
  closing therefore check the result instead of trusting the exception.
- Opening a design that references other designs also loads those designs in the background,
  without a tab of their own. They can stay loaded after the design closes.
- Every version of a data file has the same id; only the version id tells them apart.
"""

import adsk.core
import adsk.fusion

app = adsk.core.Application.get()


def get_active_project():
    """Return the project selected in the Data Panel, or None if Fusion can't provide one.

    There is normally always an active project, but in rare cases Fusion raises an
    InternalValidationError instead, for example before the Data Panel has loaded.
    """
    try:
        return app.data.activeProject
    except RuntimeError:
        return None


def get_active_folder():
    """Return the folder open in the Data Panel, or None if Fusion can't provide one."""
    try:
        return app.data.activeFolder
    except RuntimeError:
        return None


def get_active_design():
    """Return the Design product of the active document, or None if it isn't a design."""
    try:
        return adsk.fusion.Design.cast(app.activeDocument.products.itemByProductType('DesignProductType'))
    except RuntimeError:
        return None


def get_version_id(document):
    """Return the version id of the data file a document was opened from, or None for an unsaved document."""
    try:
        data_file = document.dataFile
        return data_file.versionId if data_file else None
    except RuntimeError:
        return None


def get_open_version_ids():
    """Return the version ids of every open document, including ones loaded in the background."""
    version_ids = {get_version_id(app.documents.item(i)) for i in range(app.documents.count)}
    version_ids.discard(None)
    return version_ids


def open_data_file(data_file):
    """Open and activate a data file, returning its document, or None if it didn't open.

    Opening one document can load several: an electronics schematic or board loads its whole
    electronics design, and the document that documents.open returns isn't always the one
    requested. With the latest version of a design open, opening an older version returns the
    latest one. So the requested version is looked up among the open documents.
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
        if get_version_id(document) == data_file.versionId:
            try:
                document.activate()
            except RuntimeError:
                pass
            if get_version_id(app.activeDocument) == data_file.versionId:
                return document

    return None


def close_document(document):
    """Close a document without saving. A document that really doesn't close is left for Close All."""
    try:
        document.close(False)
    except RuntimeError:
        pass


def close_documents_pass(keep_version_ids=frozenset()) -> bool:
    """Make one pass closing saved documents, except those in keep_version_ids, and return True if any closed.

    A document can't close while another loaded document references it, so the caller repeats
    passes, letting Fusion finish each one, until a pass closes nothing. Unsaved documents are
    never closed.
    """
    closed_any = False

    for document in [app.documents.item(i) for i in range(app.documents.count)]:
        if not document.isValid:
            continue

        version_id = get_version_id(document)
        if version_id is None or version_id in keep_version_ids:
            continue

        count = app.documents.count
        try:
            closed = document.close(False)
        except RuntimeError:
            closed = False

        if closed or app.documents.count < count:
            closed_any = True

    return closed_any


def is_used_by_other_designs(data_file):
    """Return True if a design is inserted into another design, which is known without opening it.

    Drawings of a design also count as parent references, so only designs are considered.
    """
    if not data_file.hasParentReferences:
        return False

    return any(parent.fileExtension == 'f3d' for parent in data_file.parentReferences)


def get_versions(data_file, all_versions):
    """Return every version of a data file, oldest first, or only the latest if all_versions is False."""
    if not all_versions:
        return [data_file]

    versions = data_file.versions
    return sorted((versions.item(i) for i in range(versions.count)), key=lambda version: version.versionNumber)


def get_folder_path(data_folder):
    """Return the names of the folders from the project root down to a data folder, or [] for the root."""
    names = []
    while data_folder is not None and data_folder.parentFolder is not None:
        names.insert(0, data_folder.name)
        data_folder = data_folder.parentFolder
    return names


def get_project_path(data_file, with_version=False):
    """Return a data file's path within its project, such as "Folder/Subfolder/Design" or "... v3"."""
    name = data_file.name + (' v{}'.format(data_file.versionNumber) if with_version else '')
    return '/'.join(get_folder_path(data_file.parentFolder) + [name])


def show_hidden_geometry(design):
    """Show every hidden body and component at every level of a design.

    Turns on the bodies and Bodies folder of the root component and of every component
    occurrence, and the occurrences themselves, so nothing is left out of an export.
    Returns what was turned on, so hide_again can put it back.
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

# Release notes

## 3.0.0

Project Archiver 3.0.0 is a rebuild of the add-in on Fusion's standard Python add-in template, with new export types and options, and fixes for most of the problems reported since 2.1.0. See the [README](README.md) for how to install and use it.

### Install

Download **Project-Archiver.zip** from the [Releases page](https://github.com/tapnair/Project-Archiver/releases/latest), not the "Source code" zip. If you have 2.1.0 installed, stop it in Scripts and Add-Ins and replace its folder with the new one.

### New

- **Export active hub.** A new command exports the projects you choose from the hub open in the Data Panel, one project at a time. All projects are selected to start with, and a scrolling list with Select all and Select none makes it easy to choose a few. The add-in estimates how many documents the export includes and asks you to confirm.
- **Export active folder.** A new command exports only the folder open in the Data Panel and its subfolders. ([#36](https://github.com/tapnair/Project-Archiver/issues/36))
- **One archive layout for every command.** The output folder is a root, `~/ProjectArchiver/` by default, and files always go into `<hub>/<project>/` and the project's folders inside it. Exporting a hub, a project or a folder puts each design in the same place, so you can build up an archive a piece at a time. The dialog shows the full path the files will go to.
- **Drawings.** Export drawings to PDF (on by default), DXF and DWG, with every sheet in one file.
- **Export all versions.** Optionally export every version of each design and drawing, with the version in each file name. The add-in shows how many files it will export and asks you to confirm. ([#23](https://github.com/tapnair/Project-Archiver/issues/23))
- **Progress and cancel.** A progress dialog shows each file as it's exported, with a Cancel button that stops after the file in progress.
- **Skip existing files.** Existing files are skipped by default, so rerunning an export finishes a cancelled one or refreshes an archive quickly. Designs whose files already exist aren't even opened. You can also choose to rename new files with -dup or overwrite.
- **Log files and summary.** Every file is listed in Project-Archiver-log.txt in its project's folder and in Fusion's Text Commands window, and a hub export adds a log with each project's totals. The export ends with one summary of what was exported, skipped and failed.
- **Include hidden bodies and components.** Optionally show everything hidden in a design before exporting it, so STEP, STL and the other formats include it. ([#56](https://github.com/tapnair/Project-Archiver/issues/56))
- **Skip designs used by other designs.** Optionally export only designs that aren't inserted into another design, such as top-level assemblies.
- **Easier to set up an export.** The dialog shows which hub, project or folder will be exported, and has a Browse button for the output folder. Options most people don't change are in a collapsed Advanced options group, and OK is only available when something is selected to export.
- **Electronics on by default.** Electronics documents are exported with one checkbox instead of separate BRD, SCH and LBR types, since each document type has only one format.
- **New icons and command names.** Export active project, Export active folder, Export active hub and Close all documents have new icons for the light and dark themes.

### Fixed

- **No more missing apper library.** The add-in no longer depends on the apper library, which was missing from repository downloads and caused "Initialization Failed" and "cannot import name 'AppObjects'" errors. ([#15](https://github.com/tapnair/Project-Archiver/issues/15), [#25](https://github.com/tapnair/Project-Archiver/issues/25), [#27](https://github.com/tapnair/Project-Archiver/issues/27), [#31](https://github.com/tapnair/Project-Archiver/issues/31), [#44](https://github.com/tapnair/Project-Archiver/issues/44), [#47](https://github.com/tapnair/Project-Archiver/issues/47))
- **Download from Releases.** The installable zip is on the Releases page instead of in the repository, where it often downloaded corrupted. ([#40](https://github.com/tapnair/Project-Archiver/issues/40), [#43](https://github.com/tapnair/Project-Archiver/issues/43), [#57](https://github.com/tapnair/Project-Archiver/issues/57))
- **Memory.** Documents are closed after each one is exported, so large projects no longer run Fusion or the computer out of memory. ([#33](https://github.com/tapnair/Project-Archiver/issues/33), [#48](https://github.com/tapnair/Project-Archiver/issues/48), [#56](https://github.com/tapnair/Project-Archiver/issues/56))
- **Names with special characters.** Design and folder names with characters such as `/`, `:` or `"` no longer fail with "The selected folder does not exist" or an invalid file name. ([#19](https://github.com/tapnair/Project-Archiver/issues/19), [#20](https://github.com/tapnair/Project-Archiver/issues/20), [#35](https://github.com/tapnair/Project-Archiver/issues/35), [#45](https://github.com/tapnair/Project-Archiver/issues/45), [#54](https://github.com/tapnair/Project-Archiver/issues/54))
- **One failure no longer stops the export.** A file that can't be opened or exported is listed in the summary and the rest of the project is still exported.
- **No active project.** Instead of `RuntimeError: 2 : InternalValidationError`, the add-in asks you to navigate to the project in the Data Panel. ([#38](https://github.com/tapnair/Project-Archiver/issues/38), [#41](https://github.com/tapnair/Project-Archiver/issues/41), [#52](https://github.com/tapnair/Project-Archiver/issues/52))
- **Designs that reference other designs.** These are still skipped for F3D, since an F3D of them can't be opened on its own, but the summary now explains why and how to save an F3Z from Fusion. Checking for references no longer fails for designs loaded in the background by an assembly. ([#22](https://github.com/tapnair/Project-Archiver/issues/22), [#49](https://github.com/tapnair/Project-Archiver/issues/49))
- **Duplicate names.** A third file with the same name no longer overwrites the first -dup file, and STL exports are checked for duplicates too.
- **Empty description or part number.** Files are named by the document name instead of only by the extension, such as `.step`.
- **Write versions.** The option now adds the version to file names, for every file name option. Before, it did nothing in current versions of Fusion, and names containing " v" were cut short (for example, "Shop vac" became "Shop").
- **Wrong document exported.** If a design failed to open, the previously open design is no longer exported under its name.
- **Electronics designs.** Schematics and boards are no longer exported twice, once on their own and once as part of their electronics design.
- **Summary message.** The summary no longer fails with "failed to find product" and is shown after the exported documents have been closed.

### Thanks

Thanks to everyone who reported problems and proposed fixes. These pull requests weren't merged as they were, since 3.0.0 is a rebuild, but their ideas are in this release:

- [#58](https://github.com/tapnair/Project-Archiver/pull/58) by jcar01: file name cleanup, duplicate and STL fixes, closing documents, per-file failures, the active project check and hidden bodies
- [#55](https://github.com/tapnair/Project-Archiver/pull/55) by mohammedrashithkp: progress, cancel and skipping files that were already exported
- [#46](https://github.com/tapnair/Project-Archiver/pull/46) by m79lol, [#39](https://github.com/tapnair/Project-Archiver/pull/39) by davidfarah2003 and [#30](https://github.com/tapnair/Project-Archiver/pull/30) by gsokoll: closing each document after export
- [#29](https://github.com/tapnair/Project-Archiver/pull/29) by gsokoll: file name cleanup
- [#37](https://github.com/tapnair/Project-Archiver/pull/37) by wrenchdog: exporting part of a project

### Known limitations

- F3D isn't exported for designs that reference other designs; use File > Export in Fusion to save an F3Z.
- DXF and DWG drawing export and electronics export use Fusion API preview features that may change.
- With Export all versions, older versions of a design that's open in Fusion can't be exported until it's closed.

## 2.1.0 and earlier

Versions before 3.0.0 used the apper library. Their code is in the repository history.

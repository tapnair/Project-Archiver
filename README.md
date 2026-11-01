# Project-Archiver
The archiver script will open all Fusion 360 3D data in a project and export it as STEP to a local location of your choosing. 

[How to install](#How-to-install)  
[How to use](#How-to-use)   
[For Developers](#For-Developers)

----

### How to install<a name="How-to-install"></a>
1. Download the latest distribution zip from the [Releases page](../../releases/latest) and unzip it to a permanent location on your computer. The zip is attached to each release.

*Do not use GitHub's **Download ZIP** button on the repository: that archive does not contain the `apper` submodule and the add-in will fail to initialize.*

The unzipped folder must contain a **Project-Archiver** sub-folder, and inside it both `Project-Archiver.py` and an `apper` folder.

*If the downloaded zip will not open, download it again (a partial download is the usual cause), or clone the repository with `git clone --recurse-submodules` and use the `Project-Archiver` folder directly.*

### Fusion 360  

1. Launch Fusion 360.
2. On the main toolbar click the **Scripts and Addins** button in the **Addins** Pane

	![](Project-Archiver/resources/scripts-addins_button.png)

3. Click the "+" at the top and select **Script or add-in from device**

    ![](Project-Archiver/resources/scripts-addins.png)

4. Browse to the **Project-Archiver** sub-folder in the unzipped folder

   ![](Project-Archiver/resources/pick_add_in.png)

5. Find Project-Archiver in the add-in list and click the run toggle switch.

   ![](Project-Archiver/resources/run_add_in.png)

6. Click the ProjectArchiver Tab and you should see **Archive** Panel and command.

	![](Project-Archiver/resources/button.png)

----

### How to use<a name="How-to-use"></a>

Open a design from the project you want to archive, then in the data panel navigate to that project.
The project of the design that is currently open is the one that gets archived: the add-in will export
all Fusion 360 files in the active project.

![](Project-Archiver/resources/dialog.png)

It then allows you to enter a path. Type in a path into the **Output Path** field.
* For OSX this might be: **/Users/*username*/Desktop/Test/**
* For Windows this might be something like **C:\Test**

Under **Export Types** select the different files types you want to export.  You can select multiple types.

#### Electronics documents

Electronics documents (prj/sch/brd/lbr) can also be archived. Select the **BRD**, **SCH**, or **LBR** export types to output the corresponding EAGLE files.

File Name Options allow you to specify the naming convention for output files.  
If you select 'Document Name' you can choose whether or not to append the version number to the file name.

Select **Include hidden bodies/components?** to export geometry that is currently hidden. Fusion's exporters
only include visible geometry, so hidden bodies would otherwise be missing from the archive. The add-in turns
everything on for the export and restores the original visibility afterwards.

Click **OK**.

Fusion will open and export each 3D design. Depending on the size of design and bandwidth this can take some time. 
Fusion 360 will be busy for the duration of the script running, so it would be advisable to run this on a dedicated machine that you can leav to run for some time. 

Each design is closed again as soon as it has been exported, so memory use stays flat even for large projects.
If a design cannot be exported, it is skipped and the run continues. At the end a summary is shown, and the full
list of failures is written to **Project-Archiver-errors.txt** in the output folder.

Designs that contain linked components are archived as **.f3z** files, since a single .f3d cannot store them.

### What's new in 2.1.1<a name="Changelog"></a>

* Designs are closed as soon as they are exported, so large projects no longer exhaust memory.
* Characters that are illegal in file names (`/ : * ? " < > |`) are replaced with `-` instead of aborting the run.
* A document that fails to export is skipped and reported, and the run continues. The full list is written to
  `Project-Archiver-errors.txt` in the output folder.
* Designs with linked components are archived as `.f3z` instead of being skipped.
* New **Include hidden bodies/components?** option.
* A missing or stale add-in dependency now produces a clear message instead of an initialization traceback.

### Troubleshooting<a name="Troubleshooting"></a>

**`Initialization Failed ... cannot import name 'AppObjects' from 'apper' (unknown location)`**

The `apper` submodule is missing. This happens when the repository was downloaded with GitHub's
**Download ZIP** button or cloned without submodules. Install the distribution zip from the Releases page, or run:

    git clone --recurse-submodules https://github.com/tapnair/Project-Archiver.git

**`No active project was found`**

Open a design from the project you want to archive, then run the command again. The add-in archives the
project that the currently open design belongs to.

**`module 'config' has no attribute 'app_name'`**

Another add-in left a module called `config` in Fusion's shared Python interpreter. Reloading the add-in
(or restarting Fusion) after updating to this version resolves it.

### For Developers<a name="For-Developers"></a>

Clone the repository including the `apper` submodule:

    git clone --recurse-submodules https://github.com/tapnair/Project-Archiver.git

If you already cloned without it, fetch the submodule in place:

    git submodule update --init --recursive

Do not run `git submodule add` - the submodule is already declared in `.gitmodules` and adding it again
creates a second, unused copy.

### Building a distribution<a name="Building-a-distribution"></a>

Distribution zips are attached to GitHub Releases, not committed to the repository. Build one with:

    python tools/build_dist.py

The version comes from `Project-Archiver/Project-Archiver.manifest`; keep `setup.py` in step with it, or the
build stops with a version mismatch. The zip is written to `dist/`, which is git-ignored, and the script checks
that the `apper` dependency and the add-in files are present before it reports success.

To publish the build:

    git tag v2.1.2
    git push origin v2.1.2
    gh release create v2.1.2 --title v2.1.2 --notes-file notes.md dist/Project-Archiver-2.1.2.zip
   
## License
Samples are licensed under the terms of the [MIT License](http://opensource.org/licenses/MIT). Please see the [LICENSE](LICENSE) file for full details.

## Written by

Written by [Patrick Rainsberry](https://twitter.com/prrainsberry) <br /> (Autodesk Fusion 360 Product Manager)

See more useful [Fusion 360 Utilities](https://tapnair.github.io/index.html)


Analytics
[![Analytics](https://ga-beacon.appspot.com/UA-41076924-3/project-archiver)](https://github.com/igrigorik/ga-beacon)




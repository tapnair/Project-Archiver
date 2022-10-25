# Project-Archiver
Forked since changes to the original project not being made and it being unusable otherwise! Is way faster and more reliable now  : ) 

Main aim is to export massive projects without supervision 

Implemented:
- closing files after export
- File name cleaning
- increased robustness a bit (had folder name errors)

TODO:
- some way of logging errors without GUI interrupts (can probably use a normal log file)
- only export un-exported files in a project, rather than going through all of them again







The archiver script will open all Fusion 360 3D data in a project and export it as STEP to a local location of your choosing. 

[How to install](#How-to-install)  
[How to use](#How-to-use)   
[For Developers](#For-Developers)

----

### How to install<a name="How-to-install"></a>
1. Click the latest link and download the [latest distribution](https://github.com/o-gent/Project-Archiver/blob/master/Project-Archiver.zip)

*Note you should download from the link above.  The regular git downloads won't get the apper submodule*

2. Unzip the archive to a permanent location on your computer

### Fusion 360  

1. Launch Fusion 360.
2. On the main toolbar click the **Scripts and Addins** button in the **Addins** Pane

	![](Project-Archiver/resources/scripts-addins_button.png)

3. Select the **Addins tab** and click the "add"  

    ![](Project-Archiver/resources/scripts-addins.png)

4. Browse to the unzipped folder
5. Select the addin in the list and click run.  
6. Dismiss the Addins dialog.  
7. Click the ProjectArchiver Tab and you should see **Archive** Panel and command.

	![](Project-Archiver/resources/button.png)

----

### How to use<a name="How-to-use"></a>

In the data panel navigate to the project you want to archive.
The add-in will export all Fusion 360 files in the active project.

![](Project-Archiver/resources/dialog.png)

It then allows you to enter a path. Type in a path into the **Output Path** field.
* For OSX this might be: **/Users/*username*/Desktop/Test/**
* For Windows this might be something like **C:\Test**

Under **Export Types** select the different files types you want to export.  You can select multiple types.

File Name Options allow you to specify the naming convention for output files.  
If you select 'Document Name' you can choose whether or not to append the version number to the file name.

Click **OK**.

Fusion will open and export each 3D design. Depending on the size of design and bandwidth this can take some time. 
Fusion 360 will be busy for the duration of the script running, so it would be advisable to run this on a dedicated machine that you can leav to run for some time. 

### For Developers<a name="For-Developers"></a>
Clone the repo

```
git submodule update --init
```

## License
Samples are licensed under the terms of the [MIT License](http://opensource.org/licenses/MIT). Please see the [LICENSE](LICENSE) file for full details.

## Written by

Written by [Patrick Rainsberry](https://twitter.com/prrainsberry) <br /> (Autodesk Fusion 360 Product Manager)

See more useful [Fusion 360 Utilities](https://tapnair.github.io/index.html)


Analytics
[![Analytics](https://ga-beacon.appspot.com/UA-41076924-3/project-archiver)](https://github.com/igrigorik/ga-beacon)




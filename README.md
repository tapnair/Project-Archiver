# Project-Archiver
The archiver script will open all Fusion 360 3D data in a project and export it as STEP to a local location of your choosing. 

[How to install](#How-to-install)  
[How to use](#How-to-use)

----

###How to install<a name="How-to-install"></a>
Download the [latest distribution]()

###Fusion 360  

1. Launch Fusion 360.
2. On the main toolbar click the **Scripts and Addins** button in the **Addins** Pane

	![](Project-Archiver/resources/scripts-addins_button.png)

3. Select the **Addins tab** and click the "add"  

    ![](Project-Archiver/resources/scripts-addins.png)
    
4. Browse to the 'Project-Archiver' sub directory in the unzipped directory
    
     ![](Project-Archiver/resources/unzipped.png)
     
5. Click run.  
6. Dismiss the Addins dialog.  
7.  Click the ProjectArchiver Tab and you should see **Archive** Pane.

	![](Project-Archiver/resources/button.png)

----

###How to use<a name="How-to-use"></a>

Launch Fusion 360.
Under the **Scripts and Addins** select Arcive-export.
In the data panel navigate to the project you want to archive.
The add-in will export all Fusion 360 files in the active project.

![](Project-Archiver/resources/dialog.png)

The dialog shows you the **Project to Archive** which is the current active project.

It then allows you to enter a path. Type in a path into the **Output Path** field.
* For OSX this might be: **/Users/*username*/Desktop/Test/**
* For Windows this might be something like **C:\Test**

Finally under **Export Types** select the different files types you want to export.  You can select multiple types.

Click **OK**.

Fusion will open and export each 3D design. Depending on the size of design and bandwidth this can take some time. 
Fusion 360 will be busy for the duration of the script running, so it would be advisable to run this on a dedicated machine that you can leav to run for some time. 

## License
Samples are licensed under the terms of the [MIT License](http://opensource.org/licenses/MIT). Please see the [LICENSE](LICENSE) file for full details.

## Written by

Written by [Patrick Rainsberry](https://twitter.com/prrainsberry) <br /> (Autodesk Fusion 360 Product Manager)

See more useful [Fusion 360 Utilities](https://tapnair.github.io/index.html)


Analytics
[![Analytics](https://ga-beacon.appspot.com/UA-41076924-3/project-archiver)](https://github.com/igrigorik/ga-beacon)




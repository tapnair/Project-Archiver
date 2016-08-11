# Project-Archiver
The archiver script will open all Fusion 360 3D data in a project and export it as STEP to a local location of your choosing. 

[How to install](#How-to-install)  
[How to use](#How-to-use)

----

###How to install<a name="How-to-install"></a>
####Windows
Download the REPO.  

1. Click Clone or *Download*  
2. Click *Download Zip*  

![](resources/download.png)

3. Un-Zip to any convient location.
4. Copy the data to: %AppData%\Autodesk\Autodesk Fusion 360\API\AddIns

5. You should then see:

![](resources/windows-result.png)

####MAC OS
Download the REPO.  

1. Click Clone or **Download**  
2. Click **Download Zip**  

![](resources/download.png)

3. Un-Zip to any convient location.
4. Copy the data to: ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns

5. You should then see:

![](resources/osx-result.png)

###Fusion 360  

1. Launch Fusion 360.
2. On the main toolbar click the **Scripts and Addins** button in the **Addins** Pane

	![](resources/scripts-addins.png)

3. Select the **Addins tab** and find the Archive-Exporter.  
4. Click **Run at startup**. 
5. Click run.  
 
	![](resources/archiver-addin.png)

6. Dismiss the Addins dialog.  
7.  On the main toolbar click the **Scripts and Addins** menu and you should see **Archive-Exporter** Pane.

	![](resources/button.png)

----

###How to use<a name="How-to-use"></a>

Launch Fusion 360.
Under the **Scripts and Addins** select Arcive-export.
After a time ( could be a long time ) a dialog will open with a list of projects. The more projects you have the longer this will take.

![](resources/dialog.png)

The dialog promts you to choose a project. From the **Select Project** drop down choose a project.
It then allows you to enter a path. Type in a path into the **Output Path** field.
* For OSX this might be: **/Users/*username*/Desktop/Test/**
* For Windows this might be something like **C:\Test**

Click **OK**.

Fusion will open and export each 3D design. Depending on the size of design and bandwidth this can take some time. Fuison 360 will be busy for the duration of the script running, so it would be adviable to run this on a dedicated machine that you can leav to run for some time. 








                                                                          
  >> Mot-Break v0.8 - "Don't just survive the horror, choreograph it." <<
  
Resident Evil Outbreak: Animation Modding Guide (v0.8)
Follow these steps to extract, modify, and re-import animations using Blender and the SwapAnimation Tool.

1. Character Setup
Import your character model into Blender. Ensure you are using the default skeleton provided by obTool (with bones named node0, node1, node2, etc.). The scripts are specifically designed to work with this bone hierarchy.

2. Enabling Scripts & Troubleshooting in Blender
Before starting, you must enable the tools and the diagnostic window within Blender:

The Log Window: Go to the top menu: Window -> Toggle System Console. Keep this window open! If an import or export fails, copy the text from this console and paste it into Discord for support.

Enable Scripts: Go to the Scripting tab at the top of the Blender window.

Open the Importer script and click Play (Run Script).

Open the Exporter script and click Play (Run Script).

You will now find the options under File -> Import -> Capcom MOT and File -> Export -> Capcom MOT.

3. Extracting a Single .mot File
Use the SwapAnimation Tool to isolate animations from game containers:

In the Read File Section, load a .bin file.

Select the animation blocks you want to extract.

Click Export Blocks as single animation and save the file with the .mot extension.

4. Importing into Blender
In the Blender window, go to File -> Import -> Capcom MOT.

Select the .mot file you just exported.

5. Editing the Animation
Modify the animation keyframes as desired.

Testing Tip: Current successful tests were performed keeping the original duration. However, feel free to experiment with different frame counts to help us determine the tool's current limits.

6. Timeline Synchronization
Ensure the animation length in Blender is set correctly before exporting:

Start Frame: 0

End Frame: [Your last keyframe]

7. Exporting from Blender
Go to File -> Export -> Capcom MOT.

IMPORTANT: For this version, you must overwrite the exact same file you originally imported into Blender.

8. Loop Settings
In the export settings panel (visible during export):

If the animation should loop: Enable the Loop Flag and specify the starting loop frame.

If not: Disable the flag.

9. Final Re-insertion
Use the SwapAnimation Tool to replace the original game animation:

Load your target file in the Write File Section.

Use the Swap function to replace the original block with your newly modified .mot.

Save the final file (it will automatically handle .bin or .mot formats).

Known Limitations

Facial Expressions: Data is readable, but eyes and eyebrows are not yet faithfully animated in Blender. Sometimes jaw goes into the skull ------> to improve- In the Exporter the face won't be exported. 
Multiple tracks: In work
Export animation from zero: should be working but it's advisible to import any animation, delete all the frame (except the first one) and begin to work from there. It's better to have all the rotation for the first frame. 
Importing hands animation: TODO


If you encounter failed imports or strange glitches, check the Blender System Console (Step 2) and send the log to me on Discord!

HUGE thanks to Fothsid for all the research, DChaps for inspiring the work and the community of OBServer!

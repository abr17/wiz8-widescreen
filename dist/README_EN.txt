Wizardry 8 Widescreen
=====================

Native widescreen for Wizardry 8: the 2D interface and the 3D view are drawn
wide (16:9, 16:10, 3:2 and the original 4:3), new wide loading screens, borderless
window, window and fullscreen modes, display settings inside the game.

Requirements
------------
Wizardry 8 version 1.2.4 from GOG or Steam (both use the same Wiz8.exe).
Wiz8.exe itself is not changed. With other versions the patch was not tested:
if the game code differs, the patch switches itself off at start-up and the game
runs as the original.

Install
-------
1. Unpack the whole archive.
2. Run Wiz8WideSetup.exe. It finds the GOG and Steam games itself; otherwise
   choose the game folder with "Browse...".
3. Press "Install".

Manual install: copy the contents of the "files" folder into the game folder
(where Wiz8.exe is), replacing files if asked.

Update
------
Run the new Wiz8WideSetup.exe; there is no need to uninstall the old version
first. Over an older version the button reads "Update" with both version
numbers: the old files are removed, the new ones installed, your settings kept.
An older installer over a newer version offers "Roll back" and asks first.

Settings
--------
Options - Video, second page: display mode (borderless / fullscreen / window)
and resolution. View distance and monster speed are on the same screens.
Changes apply at once; if the aspect ratio changes, restart the game.

To switch the patch off without removing it: in wiz8ws.ini, section [General], set Enabled=0.

Uninstall
---------
Run Wiz8WideSetup.exe and press "Uninstall". The game folder returns to the
state it was in before installation (the installer keeps a backup of every file it
replaced in Wiz8Wide.backup).

Notes
-----
- The package includes dgVoodoo 2 (DDraw.dll, D3DImm.dll, dgVoodoo.conf): without
  it the original game cannot open its video device on modern Windows.
- If the game folder already contains a version.dll from another mod, the
  installer will not overwrite it.
- Saved games are not affected and stay compatible with the original game.

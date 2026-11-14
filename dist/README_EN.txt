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
The patch draws the game through its own Direct3D 11 driver (see Notes);
dgVoodoo and other wrappers are no longer needed. The driver is designed for a
graphics card of the Direct3D 10 class or newer (feature level 10_0) and built
for Windows 7 SP1 and later; under Linux it runs with Proton or Wine.
What it was tested on: one laptop with an NVIDIA RTX 4080 under Windows 11, on
which the game was played; under Linux only a test bench with Proton and
Wine 9.0, where the picture is drawn in software. Everything else is expected
to work, but was not tried: cards from AMD and Intel, integrated graphics, cards
that offer only feature level 10_0 or 10_1, Windows 7, 8 and 10, a real Linux
PC, a Steam Deck.
If the picture is missing or very slow, look into Dll\srDD_D3D11.log in the
game folder: it names the graphics device the driver drew with. "WARP" there,
or the name of a software renderer instead of your graphics card, means that no
usable graphics card was found. Send the file with "Report a problem..." (see
Notes).

Install
-------
1. Unpack the whole archive.
2. Run Wiz8WideSetup.exe. It finds the GOG and Steam games itself; otherwise
   choose the game folder with "Browse...".
3. Press "Install". If the installer says that a file of the patch is missing,
   it has changed nothing: unpack the whole archive again (an antivirus program
   may have removed the file).

Manual install: copy the contents of the "files" folder into the game folder
(where Wiz8.exe is), replacing files if asked. Under Linux read the Linux
section first.

Update
------
Run the new Wiz8WideSetup.exe; there is no need to uninstall the old version
first. Over an older version the button reads "Update" with both version
numbers: the old files are removed, the new ones installed, your settings kept.
An older installer over a newer version offers "Roll back" and asks first.
A version installed with Wiz8WideSetup.exe should be updated with it too, not by
copying "files" over it (its uninstall would then miss the new files).
From 1.0.3 on the patch no longer uses dgVoodoo. The installer removes the
dgVoodoo files of an older version itself. If you installed that version by
copying "files" by hand, delete DDraw.dll, D3DImm.dll and dgVoodoo.conf from the
game folder (unless they are your own and you need them for something else).

Linux / Steam Deck (Proton, Wine)
---------------------------------
Under Linux the patch was tested only on a test bench (see Requirements), not
on a real Linux PC and not on a Steam Deck.

Run Wiz8WideSetup.exe with Wine or Proton, in any Wine prefix: it finds the
game (the GOG version added to Steam as a non-Steam game, or installed with
Heroic, Lutris or the GOG installer; the Steam version) and sets everything up.
No launch option is needed. Under Linux the patch starts through the game's
binkw32.dll: the installer puts a start file of the patch in its place and
keeps the original as binkw32_wiz8wide.dll (Uninstall puts it back). The game
draws through the patch's own Direct3D 11 driver (see Notes): Proton shows it
with DXVK, plain Wine with its own Direct3D 11, and nothing more has to be
installed. A game folder installed this way also works from Windows as it is
(dual boot, a shared drive); the installer need not be run there. If you run it
on Windows over such a folder anyway, it takes the Linux start file out again:
run Wiz8WideSetup.exe under Linux again and press "Reinstall", or start the
game once with the setting described below.

How to run Wiz8WideSetup.exe with Wine or Proton:
- Steam, also Steam Deck (in Desktop Mode): Games - Add a Non-Steam Game to My
  Library - Browse (set the file type to all files), choose
  Wiz8WideSetup.exe - Add Selected Programs. In its Properties - Compatibility
  tick "Force the use of a specific Steam Play compatibility tool" and choose a
  Proton, then press Play. Or right-click the exe - Open With - Protontricks
  Launcher.
- Heroic: the game's Settings - Wine - Run EXE on Prefix.
- Lutris: right-click the game - Run EXE inside Wine prefix.
- Bottles: the bottle's Run Executable.
- Plain Wine: wine Wiz8WideSetup.exe
Flatpak programs see only some folders: for Protontricks unpack the archive
into Downloads or Documents, for Heroic into Documents, for Bottles first copy
the unpacked folder to the bottle's C: drive; for a game on the SD card add
the installer to Steam instead. If the installer does not find the game,
choose its folder with "Browse..." (it opens at your home folder) or paste the
game's Linux path into the folder box, for example
  /home/deck/Games/Wizardry 8
Wine's Browse window does not show folders whose names start with a dot (such
as ~/.local, where Steam keeps its games): paste such a path.

If Steam checks the game's files (Verify integrity of game files) or GOG
Galaxy or Heroic repairs them, the original binkw32.dll comes back: run
Wiz8WideSetup.exe again and press "Reinstall".

If you copy the "files" folder by hand instead (Steam opens the game folder
with right-click Wizardry 8 - Manage - Browse local files), put the files into
the game's existing folders whatever the letter case of their names, as the
installer does by itself: under Linux a second "Dll" folder next to the game's
"DLL" does not work. The patch then needs the setting below for its first start
under Linux. It remembers it in the game's Wine prefix, and later starts work
without it; keeping it does no harm and helps if the prefix is ever reset. (The
installer's last message asks for it too in the rare cases where it is needed,
for example when another mod's binkw32.dll is in the game folder; the line is
then on the clipboard.)
- Steam: right-click Wizardry 8 - Properties - General - Launch Options (a
  non-Steam game: the "Shortcut" page of its Properties), enter:
    WINEDLLOVERRIDES="version=n,b;ddraw=b" %command%
- Heroic: the game's Settings - Advanced - Environment Variables: name
  WINEDLLOVERRIDES, value version=n,b;ddraw=b
- Lutris: Configure - Runner options - DLL overrides: version = n,b and
  ddraw = b (not System options: Lutris replaces WINEDLLOVERRIDES there).
- Bottles: the bottle's Settings - DLL Overrides: add version ("Native, then
  Builtin") and *ddraw with the star ("Builtin (Wine)"; Bottles refuses a
  plain ddraw).
- Plain Wine: WINEDLLOVERRIDES="version=n,b;ddraw=b" wine Wiz8.exe

With Wine 11.6 or later (not Proton), in a game folder that still has
dgVoodoo's DDraw.dll (left by version 1.0.2 or older: copied by hand, or
installed from Windows), the game may close at once at its very first start in
a Wine prefix where nothing was set up yet: delete DDraw.dll, D3DImm.dll and
dgVoodoo.conf (the patch no longer uses them), or start the game again, and if
it closes again, start it once with the setting above. If the game does not
start at all (no window opens), its Wine prefix probably sets ddraw to "native"
only (winecfg - Libraries, winetricks, or the DLL overrides of Bottles or
Lutris), which needs a DDraw.dll in the game folder: remove that setting, or
start the game once with the setting above (a setting for Wiz8.exe alone, made
under winecfg - Applications, must be removed). Patch files deleted by hand, or
an uninstall run in another Wine prefix, leave a small note of the patch in the
game's Wine prefix; it is harmless. If the main menu still shows only v1.2.4,
the patch did not start: run the installer again, or use the setting above. All
three display modes work under Linux: fullscreen keeps the monitor's own
resolution and scales the game's picture to fit, with black bars when the
proportions differ.

Settings
--------
Options - Video, second page: display mode (borderless / fullscreen / window)
and resolution. View distance is on the first Video page, monster speed on the
first page of the general options (the first button of Options).
Changes apply at once; if the aspect ratio changes, restart the game.
Third page: frame rate limit (30 / 60 / 120 or Unlimited, default 60). The 2001 engine
moves the party a step per frame: at higher rates tall ledges and stairs get harder to
climb; if a doorstep will not let you in, take a run-up or set 30.
After an update from 1.0.0 or 1.0.1 the old limit of 120 stays until you change it
on this page.

Options - Experimental (the USB drive in the computer picture; with English or
Russian game text also a 5th button): features that are off by default and may
change or be removed in a later version. There are four switches:
- "Animated Main Menu": an animated main menu background.
- "Map Mouse Controls": on the map the mouse wheel zooms and dragging with the
  left button moves the map; a single click no longer zooms in, a double click
  does.
- "Original Bug Fixes": fixes of the original game's own bugs. For now: the
  silent crash after about 20 loads of Arnika Road, Trynton and a few other
  places in one session, the crash when the window is closed with Alt+F4, and a
  small memory leak on every load.
- "Alternative Game Tick": at any frame rate the party moves, and stairs and the
  Umpani doorsteps are climbed, as in the original at 30 fps; monsters, lights,
  damage numbers and sound fades no longer speed up or slow down with the frame
  rate.

To switch the patch off without removing it: in wiz8ws.ini, section [General],
set Enabled=0. The game's own code then runs unchanged, but the game still draws
through the render driver named in 3DVideo.CFG: the patch's Direct3D 11 driver,
at the last resolution the patch set. The game's own 3D Setup chooses another
one.

Uninstall
---------
Run Wiz8WideSetup.exe and press "Uninstall". The game folder returns to the
state it was in before installation (the installer keeps a backup of every file it
replaced in Wiz8Wide.backup).

Notes
-----
- The patch brings its own render driver, Dll\srDD_D3D11.dll (Direct3D 11), and
  always uses it: at every start the game writes 3DVideo.CFG for it, so 3D Setup
  is not needed. dgVoodoo is no longer in the package. The game's own drivers in
  the Dll folder (DirectX7, OpenGL, Glide, Software) are left untouched, but the
  patch does not use them and they are not supported with it: to try one, switch
  the patch off (see Settings) and choose it in 3D Setup. The driver writes its
  log to Dll\srDD_D3D11.log; send it too when you report a problem with the
  picture.
- The render driver is also published on its own. If the Dll folder already had
  an srDD_D3D11.dll, the installer saves it and puts the patch's copy in its
  place: the patch always runs with its own copy. Uninstall puts yours back. A
  Dll\srDD_D3D11.ini is not part of the patch: one that you made stays where it
  is, and its settings apply to the patch's copy too.
- If the game folder already contains a version.dll from another mod, the
  installer will not overwrite it.
- Saved games are not affected and stay compatible with the original game.
- If something goes wrong: run Wiz8WideSetup.exe and press "Report a problem...".
  It saves one zip file to your Desktop (under Linux: your Desktop or home
  folder) with the patch's logs and settings, the crash dumps and a short
  summary of your system, and offers to open the bug report page:
  https://github.com/abr17/wiz8-widescreen/issues
  Describe there what happened and add the file. Reports there are public, and
  the logs contain folder names, so also your user name.
- If the game closes by itself without an error: first run Wiz8WideSetup.exe,
  tick "Diagnostics mode (for bug reports)" (under the status lines) and press
  "Reinstall"; your settings are kept. The same setting is Diagnostics=1 in
  wiz8ws.ini, section [Debug]; an update keeps it as it is. Play until it
  happens again, then press "Report a problem...". The files it packs, if you
  would rather send them by hand: wiz8ws.log, wiz8hy.log, wiz8wide.log,
  Dll\srDD_D3D11.log and the whole Wiz8Logs folder (all in the game folder).

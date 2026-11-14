Wizardry 8 Widescreen
=====================

Natives Breitbild für Wizardry 8: 2D-Oberfläche und 3D-Ansicht werden breit
gezeichnet (16:9, 16:10, 3:2 und das originale 4:3), neue breite Ladebildschirme,
randloses Fenster, Fenster- und Vollbildmodus, Anzeige-Einstellungen im Spiel.

Voraussetzungen
---------------
Wizardry 8 Version 1.2.4 von GOG oder Steam (beide nutzen dieselbe Wiz8.exe).
Die Wiz8.exe selbst wird nicht verändert. Mit anderen Versionen wurde der Patch
nicht getestet: Weicht der Spielcode ab, schaltet sich der Patch beim Start selbst
ab und das Spiel läuft wie das Original.
Der Patch zeichnet das Spiel über seinen eigenen Direct3D-11-Treiber (siehe
Hinweise); dgVoodoo und andere Wrapper werden nicht mehr gebraucht. Der Treiber
ist für eine Grafikkarte der Direct3D-10-Klasse oder neuer ausgelegt
(Feature-Level 10_0) und für Windows 7 SP1 und neuer gebaut; unter Linux läuft
er mit Proton oder Wine.
Getestet wurde auf einem Laptop mit NVIDIA RTX 4080 unter Windows 11, auf dem
das Spiel gespielt wurde; unter Linux nur in einer Testumgebung mit Proton und
Wine 9.0, in der das Bild per Software berechnet wird. Alles andere sollte
funktionieren, wurde aber nicht ausprobiert: Karten von AMD und Intel,
integrierte Grafik, Karten, die nur Feature-Level 10_0 oder 10_1 bieten,
Windows 7, 8 und 10, ein echter Linux-PC, ein Steam Deck.
Fehlt das Bild oder wird es sehr langsam gezeichnet, in Dll\srDD_D3D11.log im
Spielordner nachsehen: Dort steht, mit welchem Grafikgerät der Treiber
gezeichnet hat. Steht dort "WARP" oder statt Ihrer Grafikkarte der Name eines
Software-Renderers, wurde keine brauchbare Grafikkarte gefunden. Die Datei
bitte mit "Problem melden..." schicken (siehe Hinweise).

Installation
------------
1. Das ganze Archiv entpacken.
2. Wiz8WideSetup.exe starten. Die GOG- und Steam-Version findet es selbst;
   sonst den Spielordner mit "Durchsuchen..." wählen.
3. "Installieren" drücken. Meldet der Installer, dass eine Datei des Patches
   fehlt, hat er nichts verändert: das ganze Archiv noch einmal entpacken (ein
   Antivirenprogramm kann die Datei entfernt haben).

Manuell: den Inhalt des Ordners "files" in den Spielordner (mit Wiz8.exe)
kopieren und Dateien ersetzen. Unter Linux zuerst den Linux-Abschnitt lesen.

Aktualisieren
-------------
Die neue Wiz8WideSetup.exe starten; die alte Version muss nicht vorher entfernt
werden. Über einer älteren Version heißt der Knopf "aktualisieren" mit beiden
Versionsnummern: die alten Dateien werden entfernt, die neuen installiert, Ihre
Einstellungen bleiben erhalten. Ein älterer Installer über einer neueren Version
bietet "zurückstufen" an und fragt vorher nach.
Eine mit Wiz8WideSetup.exe installierte Version auch damit aktualisieren, nicht
durch Kopieren von "files" darüber (sonst entfernt die Deinstallation die neuen
Dateien nicht).
Ab 1.0.3 benutzt der Patch dgVoodoo nicht mehr. Die dgVoodoo-Dateien einer
älteren Version entfernt der Installer selbst. Wurde diese Version durch
Kopieren von "files" von Hand installiert, DDraw.dll, D3DImm.dll und
dgVoodoo.conf aus dem Spielordner löschen (außer es sind Ihre eigenen Dateien,
die Sie für etwas anderes brauchen).

Linux / Steam Deck (Proton, Wine)
---------------------------------
Unter Linux wurde der Patch nur in einer Testumgebung getestet (siehe
Voraussetzungen), nicht auf einem echten Linux-PC und nicht auf einem Steam
Deck.

Wiz8WideSetup.exe mit Wine oder Proton starten, in einem beliebigen
Wine-Präfix: es findet das Spiel (die GOG-Version, als Nicht-Steam-Spiel zu
Steam hinzugefügt oder mit Heroic, Lutris oder dem GOG-Installer installiert;
die Steam-Version) und richtet alles ein. Eine Startoption ist nicht nötig.
Unter Linux startet der Patch über die binkw32.dll des Spiels: der Installer
legt an ihre Stelle eine Startdatei des Patches und behält das Original als
binkw32_wiz8wide.dll (die Deinstallation stellt es wieder her). Das Spiel
zeichnet über den eigenen Direct3D-11-Treiber des Patches (siehe Hinweise):
Proton zeigt ihn mit DXVK, Wine allein mit seinem eigenen Direct3D 11, und
sonst muss nichts installiert werden. Ein so installierter Spielordner läuft
unverändert auch unter Windows (Dual-Boot, ein gemeinsames Laufwerk); der
Installer muss dort nicht gestartet werden. Wird er unter Windows trotzdem über
einem solchen Ordner ausgeführt, nimmt er die Linux-Startdatei wieder heraus:
Wiz8WideSetup.exe unter Linux erneut starten und "Neu installieren" drücken
oder das Spiel einmal mit der unten beschriebenen Einstellung starten.

So startet man Wiz8WideSetup.exe mit Wine oder Proton:
- Steam, auch Steam Deck (im Desktop-Modus): Spiele - Ein Nicht-Steam-Spiel zu
  meiner Bibliothek hinzufügen - Durchsuchen (als Dateityp alle Dateien
  wählen), Wiz8WideSetup.exe wählen - Ausgewählte Programme hinzufügen. Dann
  in den Eigenschaften des neuen Eintrags unter "Kompatibilität" die
  Verwendung eines bestimmten Steam-Play-Kompatibilitätstools erzwingen, ein
  Proton wählen und "Spielen" drücken. Oder Rechtsklick auf die exe - Öffnen
  mit - Protontricks Launcher.
- Heroic: Settings des Spiels - Wine - Run EXE on Prefix.
- Lutris: Rechtsklick auf das Spiel - Run EXE inside Wine prefix.
- Bottles: Run Executable der Flasche.
- Wine direkt: wine Wiz8WideSetup.exe
Programme aus Flatpak sehen nicht alle Ordner: für Protontricks das Archiv
nach "Downloads" oder "Dokumente" entpacken, für Heroic nach "Dokumente", für
Bottles den entpackten Ordner zuerst auf das Laufwerk C: der Flasche kopieren;
für ein Spiel auf der SD-Karte den Installer stattdessen zu Steam hinzufügen.
Findet der Installer das Spiel nicht, den Ordner mit "Durchsuchen..." wählen
(das Fenster öffnet sich im Home-Ordner) oder den Linux-Pfad des Spiels in das
Ordnerfeld einfügen, zum Beispiel
  /home/deck/Games/Wizardry 8
Das Durchsuchen-Fenster von Wine zeigt keine Ordner, die mit Punkt beginnen
(etwa ~/.local, wo Steam seine Spiele ablegt): einen solchen Pfad einfügen.

Prüft Steam die Dateien des Spiels ("Spieldateien auf Fehler überprüfen") oder
repariert GOG Galaxy oder Heroic sie, kommt die originale binkw32.dll zurück:
Wiz8WideSetup.exe erneut starten und "Neu installieren" drücken.

Wird der Ordner "files" stattdessen von Hand kopiert (Steam öffnet den
Spielordner mit Rechtsklick auf Wizardry 8 - Verwalten - Lokale Dateien
durchsuchen), gehören die Dateien in die vorhandenen Ordner des Spiels, gleich
in welcher Groß- und Kleinschreibung deren Namen stehen: Unter Linux
funktioniert ein zweiter Ordner "Dll" neben dem "DLL" des Spiels nicht (der
Installer beachtet das von selbst). Danach braucht der Patch für seinen ersten
Start unter Linux die Einstellung unten. Er merkt sie sich im Wine-Präfix des
Spiels, und spätere Starts gehen auch ohne; es schadet nicht, sie stehen zu
lassen, und hilft, falls das Präfix einmal zurückgesetzt wird. (In den seltenen
Fällen, in denen sie auch mit dem Installer nötig ist, etwa wenn im Spielordner
die binkw32.dll eines anderen Mods liegt, sagt es die letzte Meldung des
Installers, und die Zeile steht dann schon in der Zwischenablage.)
- Steam: Rechtsklick auf Wizardry 8 - Eigenschaften - Allgemein - Startoptionen
  (bei einem Nicht-Steam-Spiel auf der Seite "Verknüpfung" seiner
  Eigenschaften), eintragen:
    WINEDLLOVERRIDES="version=n,b;ddraw=b" %command%
- Heroic: Settings des Spiels - Advanced - Environment Variables: Name
  WINEDLLOVERRIDES, Wert version=n,b;ddraw=b
- Lutris: Configure - Runner options - DLL overrides: version = n,b und
  ddraw = b (nicht System options: dort ersetzt Lutris WINEDLLOVERRIDES).
- Bottles: Settings der Flasche - DLL Overrides: version hinzufügen ("Native,
  then Builtin") und *ddraw mit Stern ("Builtin (Wine)"; ein einfaches ddraw
  lehnt Bottles ab).
- Wine direkt: WINEDLLOVERRIDES="version=n,b;ddraw=b" wine Wiz8.exe

Mit Wine 11.6 oder neuer (nicht Proton) kann sich das Spiel in einem Spielordner,
in dem noch die DDraw.dll von dgVoodoo liegt (von Version 1.0.2 oder älter: von
Hand kopiert oder unter Windows installiert), beim allerersten Start in einem
Wine-Präfix, in dem noch nichts eingerichtet ist, sofort schließen: DDraw.dll,
D3DImm.dll und dgVoodoo.conf löschen (der Patch braucht sie nicht mehr) oder
einfach noch einmal starten; schließt es sich wieder, das Spiel einmal mit der
Einstellung oben starten. Startet das Spiel gar nicht (es öffnet sich kein
Fenster), steht im Wine-Präfix des Spiels für ddraw wahrscheinlich nur "native"
(winecfg - Libraries, winetricks oder die DLL Overrides von Bottles oder
Lutris); das verlangt eine DDraw.dll im Spielordner: diese Einstellung
entfernen oder das Spiel einmal mit der Einstellung oben starten (eine
Einstellung nur für Wiz8.exe, in winecfg - Applications gemacht, muss entfernt
werden). Von Hand gelöschte Patch-Dateien oder eine Deinstallation aus einem
anderen Wine-Präfix lassen im Wine-Präfix des Spiels einen kleinen Vermerk des
Patches zurück; er ist harmlos. Zeigt das Hauptmenü weiter nur v1.2.4, ist der
Patch nicht gestartet: den Installer erneut starten oder die Einstellung oben
verwenden. Unter Linux funktionieren alle drei Anzeigemodi: Vollbild lässt die
Auflösung des Monitors unverändert und skaliert das Bild des Spiels passend,
mit schwarzen Rändern, wenn die Proportionen abweichen.

Einstellungen
-------------
Optionen - Video, zweite Seite: Anzeigemodus (randlos / Vollbild / Fenster) und
Auflösung. Die Sichtweite steht auf der ersten Video-Seite, das Monstertempo
auf der ersten Seite der allgemeinen Optionen (erste Schaltfläche der Optionen).
Änderungen gelten sofort; ändert sich das Seitenverhältnis, das Spiel neu starten.
Dritte Seite: Bildratenlimit (30 / 60 / 120 oder Unbegrenzt, Standard 60). Die Engine
von 2001 bewegt die Gruppe pro Bild einen Schritt: Bei hoher Bildrate sind hohe
Absätze und Treppen schwerer zu erklimmen; lässt eine Schwelle Sie nicht hinein,
nehmen Sie Anlauf oder stellen Sie 30 ein.
Nach einem Update von 1.0.0 oder 1.0.1 bleibt das alte Limit 120, bis Sie es auf
dieser Seite ändern.

Optionen - Experimentell (der USB-Stick im Computerbild; in der englischen und
russischen Version auch die 5. Schaltfläche): Funktionen, die standardmäßig aus
sind und sich in einer späteren Version ändern oder entfallen können. Es gibt
vier Schalter:
- "Animiertes Hauptmenü": ein animierter Hintergrund des Hauptmenüs.
- "Kartensteuerung per Maus": auf der Karte zoomt das Mausrad, Ziehen mit der
  linken Maustaste verschiebt die Karte; ein einfacher Klick zoomt nicht mehr,
  ein Doppelklick schon.
- "Fehlerkorrekturen des Originals": Korrekturen von Fehlern des Originalspiels.
  Bisher: der stille Absturz nach etwa 20 Ladevorgängen von Arnika Road, Trynton
  und einigen anderen Orten in einer Sitzung, der Absturz beim Schließen des
  Fensters mit Alt+F4 und ein kleines Speicherleck bei jedem Laden.
- "Alternativer Spieltakt": bei jeder Bildrate bewegt sich die Gruppe und nimmt
  Treppen und die Türschwellen der Umpani wie im Original bei 30 Bildern pro
  Sekunde; Monster, Lichter, Schadenszahlen und Klangüberblendungen werden mit
  der Bildrate nicht mehr schneller oder langsamer.

Patch abschalten, ohne ihn zu entfernen: in wiz8ws.ini im Abschnitt [General]
Enabled=0 setzen. Der eigene Code des Spiels läuft dann unverändert, das Spiel
zeichnet aber weiter über den Render-Treiber, der in 3DVideo.CFG steht: den
Direct3D-11-Treiber des Patches, mit der letzten Auflösung, die der Patch
gesetzt hat. Einen anderen wählt man im 3D Setup des Spiels.

Entfernen
---------
Wiz8WideSetup.exe starten und "Entfernen" drücken. Der Spielordner wird wie vor
der Installation (jede ersetzte Datei liegt als Sicherung in Wiz8Wide.backup).

Hinweise
--------
- Der Patch bringt seinen eigenen Render-Treiber mit, Dll\srDD_D3D11.dll
  (Direct3D 11), und benutzt immer ihn: Bei jedem Start schreibt das Spiel die
  3DVideo.CFG dafür selbst, 3D Setup ist also nicht nötig. dgVoodoo ist nicht
  mehr im Paket. Die eigenen Treiber des Spiels im Ordner Dll (DirectX7, OpenGL,
  Glide, Software) bleiben unberührt, der Patch benutzt sie aber nicht und wird
  mit ihnen nicht unterstützt: Wer einen ausprobieren will, schaltet den Patch
  ab (siehe Einstellungen) und wählt ihn in 3D Setup. Das Protokoll des Treibers
  ist Dll\srDD_D3D11.log; bei einem Problem mit dem Bild bitte mitschicken.
- Der Render-Treiber wird auch einzeln veröffentlicht. Lag im Ordner Dll schon
  eine srDD_D3D11.dll, sichert der Installer sie und legt die Kopie des Patches
  an ihre Stelle: Der Patch läuft immer mit seiner eigenen Kopie. Die
  Deinstallation stellt Ihre Datei wieder her. Eine Dll\srDD_D3D11.ini gehört
  nicht zum Patch: Haben Sie eine angelegt, bleibt sie liegen, und ihre
  Einstellungen gelten auch für die Kopie des Patches.
- Liegt im Spielordner bereits eine version.dll eines anderen Mods, wird sie nicht
  überschrieben.
- Spielstände bleiben unverändert und mit dem Originalspiel kompatibel.
- Wenn etwas nicht funktioniert: Wiz8WideSetup.exe starten und "Problem
  melden..." drücken. Das speichert eine zip-Datei auf dem Desktop (unter Linux:
  Desktop oder Home-Ordner) mit den Protokollen und Einstellungen des Patches,
  den Absturzabbildern und einer kurzen Übersicht über Ihr System und bietet an,
  die Seite für Fehlerberichte zu öffnen:
  https://github.com/abr17/wiz8-widescreen/issues
  Beschreiben Sie dort, was passiert ist, und fügen Sie die Datei hinzu.
  Berichte dort sind öffentlich, und in den Protokollen stehen Ordnernamen, also
  auch Ihr Benutzername.
- Schließt sich das Spiel ohne Fehlermeldung von selbst: zuerst
  Wiz8WideSetup.exe starten, "Diagnosemodus (für Fehlerberichte)" ankreuzen
  (unter den Statuszeilen) und "Neu installieren" drücken; Ihre Einstellungen
  bleiben erhalten. Das ist dieselbe Einstellung wie Diagnostics=1 in
  wiz8ws.ini, Abschnitt [Debug]; ein Update lässt sie, wie sie ist.
  Weiterspielen, bis es wieder passiert, dann "Problem melden..." drücken. Wer
  die Dateien lieber von Hand schickt: wiz8ws.log, wiz8hy.log, wiz8wide.log,
  Dll\srDD_D3D11.log und der ganze Ordner Wiz8Logs (alles im Spielordner).

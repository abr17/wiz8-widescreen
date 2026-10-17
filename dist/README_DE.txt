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

Installation
------------
1. Das ganze Archiv entpacken.
2. Wiz8WideSetup.exe starten. Die GOG- und Steam-Version findet es selbst;
   sonst den Spielordner mit "Durchsuchen..." wählen.
3. "Installieren" drücken.

Manuell: den Inhalt des Ordners "files" in den Spielordner (mit Wiz8.exe)
kopieren und Dateien ersetzen.

Einstellungen
-------------
Optionen - Video, zweite Seite: Anzeigemodus (randlos / Vollbild / Fenster) und
Auflösung. Sichtweite und Monstertempo finden Sie dort ebenfalls.
Änderungen gelten sofort; ändert sich das Seitenverhältnis, das Spiel neu starten.

Patch abschalten, ohne ihn zu entfernen: in wiz8ws.ini im Abschnitt [General] Enabled=0 setzen.

Entfernen
---------
Wiz8WideSetup.exe starten und "Entfernen" drücken. Der Spielordner wird wie vor
der Installation (jede ersetzte Datei liegt als Sicherung in Wiz8Wide.backup).

Hinweise
--------
- Das Paket enthält dgVoodoo 2 (DDraw.dll, D3DImm.dll, dgVoodoo.conf): ohne es
  kann das Originalspiel unter modernem Windows sein Videogerät nicht öffnen.
- Liegt im Spielordner bereits eine version.dll eines anderen Mods, wird sie nicht
  überschrieben.
- Spielstände bleiben unverändert und mit dem Originalspiel kompatibel.

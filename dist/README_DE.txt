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

Einstellungen
-------------
Optionen - Video, zweite Seite: Anzeigemodus (randlos / Vollbild / Fenster) und
Auflösung. Sichtweite und Monstertempo finden Sie dort ebenfalls.
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
- Schließt sich das Spiel ohne Fehlermeldung von selbst: Wiz8WideSetup.exe erneut
  starten, "Diagnosemodus (für Fehlerberichte)" ankreuzen (unter den Statuszeilen,
  über den Schaltflächen) und "Neu installieren" drücken; Ihre Einstellungen
  bleiben erhalten. Das ist dieselbe Einstellung wie Diagnostics=1 in wiz8ws.ini,
  Abschnitt [Debug]; ein Update lässt sie, wie sie ist. Weiterspielen, bis es
  wieder passiert. Dann
  wiz8ws.log, wiz8hy.log, wiz8wide.log und den ganzen Ordner Wiz8Logs (alles im
  Spielordner) mit der Fehlerbeschreibung schicken.

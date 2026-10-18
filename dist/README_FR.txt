Wizardry 8 Widescreen
=====================

Écran large natif pour Wizardry 8 : l'interface 2D et la vue 3D sont dessinées
en large (16:9, 16:10, 3:2 et le 4:3 d'origine), nouveaux écrans de chargement
larges, fenêtre sans bordure, modes fenêtre et plein écran, réglages d'affichage
dans le jeu.

Configuration requise
---------------------
Wizardry 8 version 1.2.4 de GOG ou Steam (les deux utilisent le même Wiz8.exe).
Wiz8.exe lui-même n'est pas modifié. Le patch n'a pas été testé avec d'autres
versions : si le code du jeu diffère, le patch se désactive au démarrage et le jeu
tourne comme l'original.

Installation
------------
1. Décompressez toute l'archive.
2. Lancez Wiz8WideSetup.exe. Il trouve seul les versions GOG et Steam ; sinon,
   choisissez le dossier du jeu avec « Parcourir... ».
3. Cliquez sur « Installer ».

À la main : copiez le contenu du dossier « files » dans le dossier du jeu (celui
de Wiz8.exe) en remplaçant les fichiers.

Mise à jour
-----------
Lancez le nouveau Wiz8WideSetup.exe ; inutile de désinstaller l'ancienne version
avant. Sur une version plus ancienne, le bouton indique « Mettre à jour » avec les
deux numéros de version : les anciens fichiers sont retirés, les nouveaux
installés, vos réglages conservés. Un installateur plus ancien sur une version
plus récente propose « Rétrograder » et demande d'abord confirmation.

Réglages
--------
Options - Vidéo, deuxième page : mode d'affichage (sans bordure / plein écran /
fenêtre) et résolution. Distance de vue et vitesse des monstres s'y trouvent aussi.
Les changements s'appliquent tout de suite ; si le format d'image change,
relancez le jeu.

Désactiver le patch sans le retirer : dans wiz8ws.ini, section [General], mettez Enabled=0.

Désinstallation
---------------
Lancez Wiz8WideSetup.exe et cliquez sur « Désinstaller ». Le dossier du jeu
revient à son état d'avant l'installation (chaque fichier remplacé est sauvegardé
dans Wiz8Wide.backup).

Remarques
---------
- Le paquet contient dgVoodoo 2 (DDraw.dll, D3DImm.dll, dgVoodoo.conf) : sans lui,
  le jeu d'origine ne peut pas ouvrir son périphérique vidéo sur un Windows récent.
- Si le dossier du jeu contient déjà un version.dll d'un autre mod, l'installateur
  ne l'écrase pas.
- Les sauvegardes ne sont pas modifiées et restent compatibles avec le jeu
  d'origine.

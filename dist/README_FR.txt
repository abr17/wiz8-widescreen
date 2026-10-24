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
Une version installée avec Wiz8WideSetup.exe se met à jour avec lui aussi, pas
en copiant « files » par-dessus (sinon la désinstallation n'enlèverait pas les
nouveaux fichiers).

Réglages
--------
Options - Vidéo, deuxième page : mode d'affichage (sans bordure / plein écran /
fenêtre) et résolution. Distance de vue et vitesse des monstres s'y trouvent aussi.
Les changements s'appliquent tout de suite ; si le format d'image change,
relancez le jeu.
Troisième page : limite d'images (30 / 60 / 120 ou Illimité, 60 par défaut). Le moteur
de 2001 déplace le groupe d'un pas par image : à fréquence élevée, les hauts rebords et
les escaliers sont plus difficiles à gravir ; si un seuil ne vous laisse pas entrer,
prenez de l'élan ou réglez 30.
Après une mise à jour depuis 1.0.0 ou 1.0.1, l'ancienne limite de 120 reste en
place jusqu'à ce que vous la changiez sur cette page.

Options - Expérimental (la clé USB dans l'image de l'ordinateur ; dans les
versions anglaise et russe aussi le 5e bouton) : des fonctions désactivées par
défaut, qui peuvent changer ou disparaître dans une version ultérieure. Il y a
quatre cases à cocher :
- « Menu principal animé » : un fond animé pour le menu principal.
- « Carte à la souris » : sur la carte, la molette zoome et le glisser avec le
  bouton gauche déplace la carte ; un simple clic ne zoome plus, un double-clic
  si.
- « Corrections du jeu original » : des corrections de bugs du jeu d'origine.
  Pour l'instant : le plantage silencieux après une vingtaine de chargements
  d'Arnika Road, de Trynton et de quelques autres lieux en une session, le
  plantage à la fermeture de la fenêtre avec Alt+F4 et une petite fuite de
  mémoire à chaque chargement.
- « Cadence de jeu alternative » : à toute fréquence d'images, le groupe se
  déplace, et franchit les escaliers et les seuils du camp umpani, comme
  l'original à 30 images par seconde ; monstres, lumières, chiffres de dégâts
  et fondus sonores ne s'accélèrent ni ne ralentissent plus avec la fréquence
  d'images.

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
- Si le jeu se ferme tout seul sans message d'erreur : relancez Wiz8WideSetup.exe,
  cochez « Mode diagnostic (pour les rapports de bug) » (sous les lignes d'état,
  au-dessus des boutons) et cliquez sur « Réinstaller » ; vos réglages sont
  conservés. C'est le même réglage que Diagnostics=1 dans wiz8ws.ini, section
  [Debug] ; une mise à jour le laisse tel quel. Jouez jusqu'à ce que cela se
  reproduise. Envoyez
  ensuite wiz8ws.log, wiz8hy.log, wiz8wide.log et tout le dossier Wiz8Logs (tous
  dans le dossier du jeu) avec votre rapport.

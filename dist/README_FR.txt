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
Le patch affiche le jeu avec son propre pilote Direct3D 11 (voir Remarques) ;
dgVoodoo et les autres wrappers ne sont plus nécessaires. Le pilote est conçu
pour une carte graphique de classe Direct3D 10 ou plus récente (niveau de
fonctionnalité 10_0) et compilé pour Windows 7 SP1 et les versions suivantes ;
sous Linux, il fonctionne avec Proton ou Wine.
Ce qui a été testé : un ordinateur portable avec une NVIDIA RTX 4080 sous
Windows 11, sur lequel on a joué au jeu ; sous Linux, seulement un banc d'essai
avec Proton et Wine 9.0, où l'image est calculée par logiciel. Tout le reste
devrait fonctionner, mais n'a pas été essayé : cartes AMD et Intel, graphiques
intégrés, cartes qui n'offrent que le niveau de fonctionnalité 10_0 ou 10_1,
Windows 7, 8 et 10, un vrai PC sous Linux, un Steam Deck.
Si l'image manque ou s'affiche très lentement, consultez Dll\srDD_D3D11.log
dans le dossier du jeu : il indique le périphérique graphique avec lequel le
pilote a dessiné. « WARP », ou le nom d'un moteur de rendu logiciel à la place
de votre carte graphique, signifie qu'aucune carte utilisable n'a été trouvée.
Envoyez ce fichier avec « Signaler un problème... » (voir Remarques).

Installation
------------
1. Décompressez toute l'archive.
2. Lancez Wiz8WideSetup.exe. Il trouve seul les versions GOG et Steam ; sinon,
   choisissez le dossier du jeu avec « Parcourir... ».
3. Cliquez sur « Installer ». Si l'installateur signale qu'il manque un fichier
   du patch, il n'a rien modifié : décompressez de nouveau toute l'archive (un
   antivirus a pu supprimer le fichier).

À la main : copiez le contenu du dossier « files » dans le dossier du jeu (celui
de Wiz8.exe) en remplaçant les fichiers. Sous Linux, lisez d'abord la section
Linux.

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
À partir de la 1.0.3, le patch n'utilise plus dgVoodoo. L'installateur retire
lui-même les fichiers dgVoodoo d'une version plus ancienne. Si vous aviez
installé cette version en copiant « files » à la main, supprimez DDraw.dll,
D3DImm.dll et dgVoodoo.conf du dossier du jeu (sauf si ce sont vos propres
fichiers et que vous en avez besoin pour autre chose).

Linux / Steam Deck (Proton, Wine)
---------------------------------
Sous Linux, le patch n'a été testé que sur un banc d'essai (voir Configuration
requise), pas sur un vrai PC sous Linux ni sur un Steam Deck.

Lancez Wiz8WideSetup.exe avec Wine ou Proton, dans n'importe quel préfixe
Wine : il trouve le jeu (la version GOG ajoutée à Steam comme jeu non-Steam, ou
installée avec Heroic, Lutris ou l'installateur GOG ; la version Steam) et
règle tout. Aucune option de lancement n'est nécessaire. Sous Linux, le patch
démarre par le binkw32.dll du jeu : l'installateur met à sa place un fichier de
démarrage du patch et garde l'original sous le nom binkw32_wiz8wide.dll (la
désinstallation le remet en place). Le jeu s'affiche avec le pilote Direct3D 11
du patch (voir Remarques) : Proton le rend avec DXVK, Wine seul avec son propre
Direct3D 11, et il n'y a rien d'autre à installer. Un dossier du jeu installé
ainsi fonctionne aussi tel quel depuis Windows (double amorçage, disque
partagé) ; inutile d'y lancer l'installateur. Si vous le lancez quand même
sous Windows sur un tel dossier, il retire le fichier de démarrage Linux :
relancez Wiz8WideSetup.exe sous Linux et cliquez sur « Réinstaller », ou
lancez le jeu une fois avec le réglage décrit plus bas.

Lancer Wiz8WideSetup.exe avec Wine ou Proton :
- Steam, y compris Steam Deck (en mode Bureau) : Jeux - Ajouter un jeu
  non-Steam à ma bibliothèque - Parcourir (type de fichier : tous les
  fichiers), choisissez Wiz8WideSetup.exe - Ajouter les programmes
  sélectionnés. Puis, dans les Propriétés de ce raccourci, page
  « Compatibilité », forcez l'utilisation d'un outil de compatibilité Steam
  Play précis, choisissez un Proton et cliquez sur « Jouer ». Ou clic droit
  sur l'exe - Ouvrir avec - Protontricks Launcher.
- Heroic : Settings du jeu - Wine - Run EXE on Prefix.
- Lutris : clic droit sur le jeu - Run EXE inside Wine prefix.
- Bottles : Run Executable de la bouteille.
- Wine seul : wine Wiz8WideSetup.exe
Les programmes Flatpak ne voient pas tous les dossiers : pour Protontricks,
décompressez l'archive dans Téléchargements ou Documents ; pour Heroic, dans
Documents ; pour Bottles, copiez d'abord le dossier décompressé sur le lecteur
C: de la bouteille ; pour un jeu sur la carte SD, ajoutez plutôt
l'installateur à Steam. Si l'installateur ne trouve pas le jeu, choisissez son
dossier avec « Parcourir... » (la fenêtre s'ouvre dans votre dossier
personnel) ou collez le chemin Linux du jeu dans le champ du dossier, par
exemple
  /home/deck/Games/Wizardry 8
La fenêtre Parcourir de Wine ne montre pas les dossiers dont le nom commence
par un point (comme ~/.local, où Steam range ses jeux) : collez alors le
chemin.

Si Steam vérifie les fichiers du jeu (« Vérifier l'intégrité des fichiers du
jeu ») ou si GOG Galaxy ou Heroic les répare, le binkw32.dll d'origine
revient : relancez Wiz8WideSetup.exe et cliquez sur « Réinstaller ».

Si vous copiez plutôt le dossier « files » à la main (Steam ouvre le dossier du
jeu par clic droit sur Wizardry 8 - Gérer - Parcourir les fichiers locaux),
mettez les fichiers dans les dossiers existants du jeu, quelle que soit la
casse de leurs noms : sous Linux, un second dossier « Dll » à côté du « DLL » du
jeu ne fonctionne pas (l'installateur en tient compte tout seul). Le patch a
ensuite besoin du réglage ci-dessous pour son premier lancement sous Linux. Il
le retient dans le préfixe Wine du jeu, et les lancements suivants marchent
sans ; le garder ne gêne pas et aide si le préfixe est un jour réinitialisé.
(Dans les rares cas où il est nécessaire même avec l'installateur, par exemple
quand le dossier du jeu contient le binkw32.dll d'un autre mod, le dernier
message de l'installateur le dit, et la ligne est alors déjà dans le
presse-papiers.)
- Steam : clic droit sur Wizardry 8 - Propriétés - Général - Options de
  lancement (pour un jeu non-Steam, page « Raccourci » de ses Propriétés),
  saisissez :
    WINEDLLOVERRIDES="version=n,b;ddraw=b" %command%
- Heroic : Settings du jeu - Advanced - Environment Variables : nom
  WINEDLLOVERRIDES, valeur version=n,b;ddraw=b
- Lutris : Configure - Runner options - DLL overrides : version = n,b et
  ddraw = b (pas System options : Lutris y remplace WINEDLLOVERRIDES).
- Bottles : Settings de la bouteille - DLL Overrides : ajoutez version
  (« Native, then Builtin ») et *ddraw avec l'étoile (« Builtin (Wine) » ;
  Bottles refuse un ddraw simple).
- Wine seul : WINEDLLOVERRIDES="version=n,b;ddraw=b" wine Wiz8.exe

Avec Wine 11.6 ou plus récent (pas Proton), si le dossier du jeu contient encore
le DDraw.dll de dgVoodoo (laissé par la version 1.0.2 ou une plus ancienne :
copié à la main, ou installé depuis Windows), le jeu peut se fermer aussitôt au
tout premier lancement dans un préfixe Wine où rien n'est encore réglé :
supprimez DDraw.dll, D3DImm.dll et dgVoodoo.conf (le patch ne s'en sert plus),
ou relancez simplement le jeu, et s'il se ferme encore, lancez-le une fois avec
le réglage ci-dessus. Si le jeu ne démarre pas du tout (aucune fenêtre ne
s'ouvre), son préfixe Wine règle probablement ddraw sur « native » seulement
(winecfg - Libraries, winetricks, ou les DLL Overrides de Bottles ou de Lutris),
ce qui exige un DDraw.dll dans le dossier du jeu : supprimez ce réglage, ou
lancez le jeu une fois avec le réglage ci-dessus (un réglage fait pour Wiz8.exe
seul, dans winecfg - Applications, doit être supprimé). Des fichiers du patch
supprimés à la main, ou une désinstallation lancée depuis un autre préfixe Wine,
laissent dans le préfixe Wine du jeu une petite note du patch ; elle est sans
danger. Si le menu principal affiche encore seulement v1.2.4, le patch n'a pas
démarré : relancez l'installateur ou utilisez le réglage ci-dessus. Les trois
modes d'affichage marchent sous Linux : le plein écran laisse le moniteur dans
sa propre résolution et met l'image du jeu à l'échelle, avec des bandes noires
quand les proportions diffèrent.

Réglages
--------
Options - Vidéo, deuxième page : mode d'affichage (sans bordure / plein écran /
fenêtre) et résolution. La distance de vue est sur la première page Vidéo, la
vitesse des monstres sur la première page des options générales (premier bouton
des Options).
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

Désactiver le patch sans le retirer : dans wiz8ws.ini, section [General], mettez
Enabled=0. Le code du jeu lui-même tourne alors sans modification, mais le jeu
s'affiche toujours avec le pilote de rendu indiqué dans 3DVideo.CFG : le pilote
Direct3D 11 du patch, à la dernière résolution réglée par le patch. Le 3D Setup
du jeu permet d'en choisir un autre.

Désinstallation
---------------
Lancez Wiz8WideSetup.exe et cliquez sur « Désinstaller ». Le dossier du jeu
revient à son état d'avant l'installation (chaque fichier remplacé est sauvegardé
dans Wiz8Wide.backup).

Remarques
---------
- Le patch apporte son propre pilote de rendu, Dll\srDD_D3D11.dll (Direct3D 11),
  et l'utilise toujours : à chaque lancement, le jeu écrit lui-même 3DVideo.CFG
  pour lui, 3D Setup est donc inutile. dgVoodoo n'est plus dans le paquet. Les
  pilotes d'origine du jeu dans le dossier Dll (DirectX7, OpenGL, Glide,
  Software) restent intacts, mais le patch ne les utilise pas et n'est pas pris
  en charge avec eux : pour en essayer un, désactivez le patch (voir Réglages)
  et choisissez-le dans 3D Setup. Le journal du pilote est Dll\srDD_D3D11.log ;
  joignez-le aussi si vous signalez un problème d'image.
- Le pilote de rendu est aussi publié séparément. Si le dossier Dll contenait
  déjà un srDD_D3D11.dll, l'installateur le met de côté et installe à sa place
  la copie du patch : le patch fonctionne toujours avec sa propre copie. La
  désinstallation remet le vôtre. Un Dll\srDD_D3D11.ini ne fait pas partie du
  patch : si vous en avez créé un, il reste en place, et ses réglages
  s'appliquent aussi à la copie du patch.
- Si le dossier du jeu contient déjà un version.dll d'un autre mod, l'installateur
  ne l'écrase pas.
- Les sauvegardes ne sont pas modifiées et restent compatibles avec le jeu
  d'origine.
- En cas de problème : lancez Wiz8WideSetup.exe et cliquez sur « Signaler un
  problème... ». Il enregistre sur le Bureau (sous Linux : le Bureau ou le
  dossier personnel) un fichier zip avec les journaux et les réglages du patch,
  les images mémoire des plantages et un court résumé de votre système, puis
  propose d'ouvrir la page des rapports de bug :
  https://github.com/abr17/wiz8-widescreen/issues
  Décrivez-y ce qui s'est passé et ajoutez le fichier. Les rapports y sont
  publics, et les journaux contiennent des noms de dossiers, donc aussi votre
  nom d'utilisateur.
- Si le jeu se ferme tout seul sans message d'erreur : lancez d'abord
  Wiz8WideSetup.exe, cochez « Mode diagnostic (pour les rapports de bug) » (sous
  les lignes d'état) et cliquez sur « Réinstaller » ; vos réglages sont
  conservés. C'est le même réglage que Diagnostics=1 dans wiz8ws.ini, section
  [Debug] ; une mise à jour le laisse tel quel. Jouez jusqu'à ce que cela se
  reproduise, puis cliquez sur « Signaler un problème... ». Si vous préférez
  envoyer les fichiers à la main : wiz8ws.log, wiz8hy.log, wiz8wide.log,
  Dll\srDD_D3D11.log et tout le dossier Wiz8Logs (tous dans le dossier du jeu).

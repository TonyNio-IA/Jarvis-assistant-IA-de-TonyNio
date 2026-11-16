# Jarvis, assistant IA de TonyNio

**English: [README.en.md](README.en.md)** · **Version actuelle : 1.18**

<p align="center"><img src="docs/jarvis.gif" alt="Le réacteur de Jarvis : veille, écoute, réflexion, réponse, rappel" width="320"></p>

**Jarvis est un assistant vocal en français pour Windows 11.** Tu dis « Jarvis », il comprend ta demande, y répond à voix haute et agit sur ton PC : ouvrir une application, gérer les fenêtres, lancer de la musique, poser un rappel, lire ou traduire un texte copié, décrire ce qui est à l'écran. Les demandes simples sont traitées sur le PC en une seconde ; les autres sont confiées à Claude.

Un réacteur animé, toujours visible dans un coin de l'écran, montre ce qu'il fait : il écoute, il réfléchit, il répond.

> **In English.** The full presentation in English is in [README.en.md](README.en.md). Jarvis itself speaks and understands French only.

## Ce qu'il te faut

- **Windows 11** et un **micro**.
- **Python 3.14**.
- **Claude Code**, connecté à un abonnement Claude (Pro ou supérieur). Sans lui, seules les commandes immédiates fonctionnent.
- Rien d'autre à payer : la reconnaissance vocale et la voix utilisent des outils gratuits.

## Installation

1. Télécharge le projet (bouton vert **Code**, puis **Download ZIP**) et décompresse-le dans le dossier de ton choix, par exemple `C:\Jarvis`.
2. Installe les modules : `python -m pip install -r requirements.txt` (depuis ce dossier).
3. Télécharge le modèle de reconnaissance vocale **vosk-model-small-fr-0.22** sur https://alphacephei.com/vosk/models et décompresse-le dans le même dossier. Le modèle Whisper se télécharge tout seul au premier lancement.
4. Copie `config.exemple.json`, renomme la copie en `config.json` et mets-y ton prénom et tes sujets (voir « Réglages personnels »).
5. Lance Jarvis : `pythonw jarvis_gardien.py`
6. Pour qu'il démarre avec Windows : crée un raccourci vers `pythonw.exe "C:\Jarvis\jarvis_gardien.py"` (dossier de travail : celui de Jarvis) et place-le dans `shell:startup`.

## Réglages personnels

Ces fichiers restent sur ton PC, dans le dossier de Jarvis. Ils ne font pas partie du projet publié.

| Fichier | Contenu |
|---|---|
| `config.json` | Ton prénom, les rubriques de ton point du jour, un site à consulter, les noms propres que tu prononces souvent. Modèle : `config.exemple.json`. |
| `ville.txt` | Ta ville pour la météo, sur une ligne : `Nom;latitude;longitude` (exemple : `Paris;48.8566;2.3522`). Sans ce fichier, Jarvis donne la météo de Paris. |

Jarvis crée aussi ses propres fichiers au fil de l'usage (mémoire, rappels, notes, liste d'applications, journal). Eux non plus ne quittent pas ton PC.

## Ce qu'il sait faire

- Se réveiller quand une phrase commence par « Jarvis » (un petit bip indique qu'on peut parler).
- Répondre aux questions et agir sur le PC (ouvrir un programme, chercher une information...).
- Enchaîner une autre demande dans les 3 secondes sans redire « Jarvis ».
- Se souvenir de la conversation pendant 10 minutes (« Jarvis, nouvelle conversation » pour repartir de zéro).
- « Jarvis, fais-moi le point du jour » : météo de ta ville, actualités, puis tes propres sujets (réglés dans `config.json`).
  La ville se règle dans `ville.txt` (fichier gardé sur le PC, jamais publié : `Nom;latitude;longitude`).
  Il le prépare en arrière-plan et le lit dès qu'il est prêt ; « Jarvis, annule le point du jour » l'arrête.
  (Réglage `POINT_DU_JOUR_AUTO = True` pour qu'il le prépare tout seul au premier démarrage du matin.)
- Réponse immédiate, sans Claude, pour : l'heure, la date, la météo (aujourd'hui, demain, après-demain, via Open-Meteo), le volume, la musique (pause, suivant, précédent), les minuteurs et rappels (« rappelle-moi dans 20 minutes de sortir le linge »), l'ouverture d'applications courantes et le verrouillage du PC.
- « Jarvis, répète » : il redit sa dernière réponse.
- Rappels à heure fixe : « rappelle-moi à 18 h d'appeler le garage », « réveille-moi demain à 7 h », « quels sont mes rappels », « annule mes rappels ». Ils sont conservés si le PC redémarre.
- « Ferme Chrome », « fais une capture d'écran », « cherche le fichier facture », « ouvre WinRAR » (toute application du menu Démarrer).
- Routines : « Jarvis, bonjour » (date, heure, météo, rappels du jour, état du PC) et « Jarvis, bonne nuit » (ferme les applications et met le PC en veille, après confirmation).
- Dictée : « Jarvis, dicte : je serai là dans dix minutes » tape la phrase dans la fenêtre active ; « appuie sur entrée » valide.
- Musique : « Jarvis, mets Get Lucky de Daft Punk » ou « mets de la musique » lance la lecture sur YouTube.
- « Éteins l'ordinateur », « redémarre l'ordinateur », « mets l'ordinateur en veille » : Jarvis demande toujours confirmation, et l'extinction peut être annulée pendant 30 secondes.
- « Jarvis, état du PC » (ou « pourquoi ça rame ») : processeur, mémoire, programme le plus gourmand, place sur le disque.
- Fenêtres : « mets Imou en plein écran », « réduis la fenêtre », « mets Chrome à gauche » (à droite, en haut, en bas), « mets Imou au premier plan », « ferme la fenêtre », « affiche le bureau ». Le nom d'une application ouverte est reconnu même mal entendu.
- Écran : « qu'est-ce qu'il y a à l'écran ? », « explique-moi cette erreur » : Jarvis photographie la fenêtre active et Claude la regarde.
- Texte copié : « lis ce que j'ai copié », « résume le texte copié », « traduis le texte sélectionné en anglais », « corrige le texte copié » (le résultat est remis dans le presse-papiers, prêt à coller).
- « Jarvis, redémarre-toi ». Un gardien le relance tout seul s'il plante ou si le micro est débranché.
- « Jarvis, note que... » et « Jarvis, lis mes notes » (fichier `notes.txt`).
- Mémoire durable : « Jarvis, retiens que... », « qu'est-ce que tu as retenu ? », « oublie que... », « efface toute ta mémoire » (avec confirmation). Jarvis garde aussi le fil des derniers échanges : il sait de quoi vous parliez même après un redémarrage. Tout reste dans `memoire.json`, sur le PC.
- Sous le réacteur : l'heure, les mots compris au fil de l'écoute, puis la charge du processeur, la mémoire et le débit du réseau en temps réel.
- Autour du réacteur : une couronne de graduations qui dessine le spectre du son (ta voix quand il écoute, la sienne quand il répond).
- « Stop », « Jarvis, stop » ou « Tais-toi » pendant qu'il parle : il se tait.
- Se mettre en pause tout seul quand l'application Claude lit un message à voix haute (touche F9).
- Démarrer avec Windows, sans fenêtre.

## Fichiers

| Fichier | Rôle |
|---|---|
| `jarvis_gardien.py` | Point d'entrée : lance Jarvis et le relance s'il s'arrête tout seul |
| `jarvis_reacteur.py` | Le réacteur animé, qui lance l'écoute |
| `jarvis_ecran.py` | La capture de l'écran et le presse-papiers |
| `jarvis_claude.py` | L'écoute, la reconnaissance vocale et le dialogue avec Claude |
| `jarvis_voix.py` | La voix naturelle « Henri » (edge-tts) |
| `jarvis_commandes.py` | Les commandes instantanées (heure, date, volume, applications) |
| `jarvis_memoire.py` | La mémoire durable (faits retenus, derniers échanges) |
| `jarvis_fenetres.py` | La gestion des fenêtres à la voix (agrandir, réduire, placer, fermer) |
| `jarvis_affichage.py` | L'affichage rapide du réacteur et du panneau (pygame, 60 images/s) |
| `jarvis_systeme.py` | La surveillance du PC (processeur, mémoire, carte graphique, réseau) |
| `jarvis_tts.py` | La voix Windows de secours |
| `jarvis_config.py` | La lecture des réglages personnels (`config.json`) |
| `config.exemple.json` | Le modèle de réglages personnels à copier |
| `requirements.txt` | Les modules Python nécessaires |
| `LICENSE.md` | La licence (PolyForm Strict 1.0.0) |
| `README.en.md` | La présentation en anglais |

## Comment ça marche

1. **Vosk** (hors ligne) écoute en permanence et repère le mot « Jarvis ».
2. **Whisper** (modèle « base », sur le PC) retranscrit la demande plus précisément. Si Vosk et Whisper ne sont pas d'accord, les deux versions sont envoyées à Claude.
3. **Claude Code** reste ouvert en continu (modèle Sonnet) : une réponse simple arrive en 1 à 2 secondes.
   Il est lancé en version allégée (sans extensions, quatre outils seulement) : environ 4 fois moins de quota par question.
4. **edge-tts** lit la réponse avec la voix d'Henri.

## Réglages techniques

En haut de `jarvis_claude.py` : `MODELE` et `MODELE_POINT_DU_JOUR` (« sonnet » ou « opus »), `DELAI_SUITE`, `MEMOIRE_MINUTES`, `REVEIL_PENDANT_SON`, `ECONOMIE_SILENCE`...
En haut de `jarvis_affichage.py` : `MODE_DISCRET`, `TAILLE_DISCRETE`, `HALO`... En haut de `jarvis_reacteur.py` : `TAILLE`, les couleurs des états.

Le journal `jarvis.log`, dans le dossier de Jarvis, note tout ce qu'il entend et répond : c'est le premier endroit où regarder quand quelque chose ne marche pas.

## Licence et participation

Jarvis est publié sous licence **PolyForm Strict 1.0.0** (fichier `LICENSE.md`). En clair :

- tu peux le télécharger et l'utiliser chez toi, pour un usage personnel et non commercial ;
- tu ne peux pas le modifier, ni en publier une copie ou une version à toi ;
- les nouveautés arrivent avec les versions publiées ici.

Une idée, un bug, une commande qui manque ? Ouvre une demande dans l'onglet **Issues**, en français ou en anglais : c'est la bonne façon de faire avancer le projet.

## Versions

| Version | Contenu |
|---|---|
| 1.18 | Jarvis devient utilisable par d'autres : prénom, sujets du point du jour et vocabulaire réglés dans `config.json`, installation dans le dossier de son choix ; licence PolyForm Strict ; présentation refaite |
| 1.17 | Affichage : mode discret en veille (le réacteur rétrécit, le panneau disparaît, il revient au survol de la souris), minuteurs et rappels visibles sur la couronne et dans le panneau, alerte visuelle de 5 secondes quand un rappel sonne, animations de lancement et d'arrêt ; correction d'un plantage au déplacement du réacteur ; « redémarre-toi » reconnu même mal entendu |
| 1.15 | Jarvis se réveille aussi pendant qu'une vidéo ou de la musique joue, et coupe presque le son du PC le temps de t'écouter ; il voit l'écran (« qu'est-ce qu'il y a à l'écran ? ») et le texte copié (« résume / traduis / corrige ce que j'ai copié ») ; gardien qui le relance s'il plante ou si le micro est débranché ; « Jarvis, redémarre-toi » ; « mets » entendu « mais » rétabli pour toutes les commandes ; rappels « mets un rappel à 13 h 56 » corrigés |
| 1.12 | Le son du PC est baissé pendant que tu parles à Jarvis, et il n'écoute plus de suite quand une vidéo ou de la musique joue ; Claude connaît les fenêtres ouvertes ; gestion des fenêtres à la voix ; applications déjà ouvertes reconnues même mal entendues ; réponses courtes (« oui », « non ») mieux comprises ; corrections après essais : « mets l'application en grand écran » ne lance plus une vidéo, les demandes doubles (« ferme ça et ouvre Chrome ») vont à Claude en entier, « Jarvis » redit en cours de conversation relance l'écoute, réveil et « éteins » mieux reconnus |
| 1.11 | Mémoire durable (faits retenus à la demande, fil des derniers échanges) ; écoute plus fine (le bip ne coupe plus le début de la demande, « mets » mieux compris, réaction en 0,1 s) ; mots affichés pendant l'écoute ; couronne de spectre, halo, onde de réveil et heure dans l'affichage ; ville de la météo réglable dans un fichier local |
| 1.10 | Rappels à heure fixe conservés au redémarrage, fermeture d'applications, capture d'écran, recherche de fichier, extinction / redémarrage / veille avec confirmation, ouverture des applications du menu Démarrer ; réveil plus tolérant ; panneau agrandi ; voix un peu plus rapide |
| 1.09 | Jauge de température (celle de la puce graphique, comme dans le Gestionnaire des tâches) |
| 1.08 | Le contour extérieur du réacteur ondule lui aussi |
| 1.07 | Correction : le réacteur reste de nouveau au premier plan ; jauge réseau calée sur le débit mesuré de la connexion |
| 1.06 | Affichage réécrit avec pygame : 60 images par seconde quand Jarvis est actif ; jauges GPU et réseau |
| 1.05 | Panneau sous le réacteur plus compact, style affichage de bord (jauges segmentées) ; le réacteur retient sa position |
| 1.04 | Processeur, mémoire et réseau affichés sous le réacteur, « état du PC », notes vocales, Jarvis 3 fois plus léger en veille, démarrage en 3 secondes |
| 1.03 | Claude allégé (environ 4 fois moins de quota), météo, minuteurs et musique sans Claude, voix par morceaux, réacteur réactif au son, sous-titre |
| 1.02 | Point du jour à la demande et annulable, filtre des phrases inventées par Whisper |
| 1.01 | Commandes instantanées, interruption « stop », point du jour automatique |
| 1.0 | Première sauvegarde : écoute, Claude en continu, voix Henri, réacteur animé |

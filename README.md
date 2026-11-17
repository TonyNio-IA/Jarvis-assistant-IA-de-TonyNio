# Jarvis, assistant IA de TonyNio

**English: [README.en.md](README.en.md)** · **Version actuelle : 1.22**

<p align="center"><img src="docs/jarvis.gif" alt="Le réacteur de Jarvis : veille, écoute, réponse, rappel, mode discret" width="320"></p>

**▶ Démonstration en vidéo (6 min) : [Je parle à mon PC et il m'obéit : j'ai créé mon propre JARVIS](https://www.youtube.com/watch?v=3Xd91q7618U)**

**Jarvis est un assistant vocal en français pour Windows 11.** Tu dis « Jarvis », il comprend ta demande, y répond à voix haute et agit sur ton PC : ouvrir une application, gérer les fenêtres, lancer de la musique, poser un rappel, lire ou traduire un texte copié, décrire ce qui est à l'écran. Les demandes simples sont traitées sur le PC en une seconde ; les autres sont confiées à Claude.

Un réacteur animé, toujours visible dans un coin de l'écran, montre ce qu'il fait : il écoute, il réfléchit, il répond.

> **In English.** The full presentation in English is in [README.en.md](README.en.md). Jarvis itself speaks and understands French only.

## Ce qu'il te faut

- **Windows 11** (64 bits) et un **micro**.
- Une connexion Internet pendant l'installation, et environ **3 Go** libres sur le disque.
- Facultatif : un **abonnement Claude** (Pro ou supérieur), pour lui poser toutes tes questions. Sans lui, Jarvis répond aux commandes immédiates : heure, météo, minuteurs, fenêtres, musique.
- Rien d'autre à payer : la reconnaissance vocale et la voix utilisent des outils gratuits.

## Installation

1. **Télécharge l'installateur : [Installer-Jarvis.exe](https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio/releases/latest/download/Installer-Jarvis.exe)** (environ 200 Ko).
2. **Double-clique dessus.** Windows affiche sans doute un écran bleu « Windows a protégé votre ordinateur » : c'est normal pour un petit programme gratuit qui n'est pas signé par un éditeur payant. Clique sur **Informations complémentaires**, puis sur **Exécuter quand même**.
3. **Réponds aux deux questions** : ton prénom, et si tu veux utiliser ton abonnement Claude. Ensuite, l'installation se fait toute seule (une dizaine de minutes, selon ta connexion et ton PC). Elle met en place :
   - Python 3.14 (depuis python.org), dans ton dossier personnel ;
   - les composants Microsoft Visual C++ : Windows demande ton autorisation, réponds **Oui** ;
   - Jarvis, ses modules et son modèle vocal, dans `C:\Jarvis` ;
   - Claude Code (depuis claude.ai), si tu l'as choisi ;
   - un raccourci « Jarvis » sur le Bureau et au démarrage de Windows.
4. **Si tu as choisi Claude**, ton navigateur s'ouvre pour te connecter à ton compte Claude. Sur un PC neuf, il montre peut-être d'abord son propre écran d'accueil : passe-le. Connecte-toi, accepte l'autorisation, puis reviens dans la fenêtre de l'installateur.
5. **À la fin, Jarvis démarre.** Le premier lancement prend une minute ou deux : il télécharge son second modèle vocal (Whisper). La toute première vérification peut aussi être lente sur un PC neuf, le temps que Windows examine les nouveaux fichiers.

Pour avoir la météo de chez toi, dis-lui une fois : « **Jarvis, ma ville est** … » suivi du nom de ta ville.

**Mettre à jour, réparer, ajouter Claude ou désinstaller :** relance le même fichier. Une copie est aussi rangée dans `C:\Jarvis` (touche Windows + R, tape `C:\Jarvis`, puis Entrée). Un menu te propose de mettre à jour, de désinstaller, ou d'ajouter Claude s'il manque. La mise à jour garde tes réglages, sa mémoire et tes rappels.

**Si ton antivirus refuse le fichier .exe :** télécharge à la place [Installer-Jarvis.bat](https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio/releases/latest/download/Installer-Jarvis.bat). Il fait exactement la même installation, sans l'icône du réacteur. Le code des deux est lisible dans le dossier `installateur` du projet.

<details>
<summary>Installation à la main (pour les curieux)</summary>

1. Télécharge le projet (bouton vert **Code**, puis **Download ZIP**) et décompresse-le, par exemple dans `C:\Jarvis`.
2. Installe Python 3.14, puis les modules depuis ce dossier : `python -m pip install -r requirements.txt`
3. Télécharge le modèle de reconnaissance vocale **vosk-model-small-fr-0.22** sur https://alphacephei.com/vosk/models et décompresse-le dans le même dossier.
4. Copie `config.exemple.json`, renomme la copie en `config.json` et mets-y ton prénom.
5. Lance Jarvis : `pythonw jarvis_gardien.py`. Pour qu'il démarre avec Windows, place un raccourci vers cette commande dans `shell:startup`.

</details>

## Réglages personnels

Ces fichiers restent sur ton PC, dans le dossier de Jarvis. Ils ne font pas partie du projet publié.

| Fichier | Contenu |
|---|---|
| `config.json` | Ton prénom, les rubriques de ton point du jour, un site à consulter, les noms propres que tu prononces souvent, et si tu le veux des heures fixes pour le mode nuit. Modèle : `config.exemple.json`. |
| `ville.txt` | Ta ville pour la météo. Le plus simple : dis « Jarvis, ma ville est … », il crée ce fichier. Format : `Nom;latitude;longitude` (exemple : `Paris;48.8566;2.3522`). Sans ce fichier, Jarvis donne la météo de Paris. |

Jarvis crée aussi ses propres fichiers au fil de l'usage (mémoire, rappels, notes, listes, réglages de la voix, liste d'applications, journal). Eux non plus ne quittent pas ton PC.

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
- En veille : couleurs façon coucher de soleil de Vice City (rose, orange, violet) ; au bout de 35 secondes, le réacteur se fait discret et seules les jauges restent, dans un petit bandeau ; un reflet de lumière fait sans cesse le tour des panneaux et du réacteur ; le réacteur danse quand le PC joue de la musique, son cœur se tourne vers la souris, il se fait plus doux après le coucher du soleil, et une petite fête l'anime à minuit et le jour de ton anniversaire.
- Pour lui couper la parole, dis « Jarvis » : il se tait aussitôt et écoute ta nouvelle demande (« stop » le fait taire).
- « Stop », « Jarvis, stop » ou « Tais-toi » pendant qu'il parle : il se tait.
- Se mettre en pause tout seul quand l'application Claude lit un message à voix haute (touche F9).
- Démarrer avec Windows, sans fenêtre.
- Calculs et conversions, sans Claude : « combien font 15 % de 80 », « racine carrée de 144 », « 3 miles en kilomètres », « 20 degrés en Fahrenheit », « 50 dollars en euros » (taux de la Banque centrale européenne).
- Chronomètre : « lance un chrono », « où en est le chrono », « arrête le chrono ».
- Listes : « ajoute du pain et du lait à la liste », « enlève le lait de la liste », « lis-moi la liste », « ajoute appeler le garage à la liste des tâches » (fichier `liste.json`, gardé sur le PC).
- Raccourcis dans la fenêtre active : « copie », « colle », « coupe », « annule ça », « sélectionne tout », « enregistre », « nouvel onglet », « ferme l'onglet », « actualise ».
- Vidéos : « avance de 30 secondes », « recule de 10 secondes ».
- Le son d'une seule application : « baisse le son de Chrome », « mets le son de Spotify à 30 », « coupe le son de Discord ».
- Navigateur : « cherche des recettes de crêpes sur YouTube » (aussi Amazon, Google, Wikipédia, Leboncoin, Google Maps...), « clique sur Connexion », « clique sur la deuxième vidéo », « clique sur le premier résultat », « fais défiler », « remonte », « tout en haut », « reviens en arrière », « page suivante », « lis-moi cette page », « résume cette page » (Claude reçoit le texte de la page).
- Windows : « active le mode sombre », « passe en mode clair », « active le Bluetooth », « coupe le Bluetooth », « monte la luminosité », « luminosité à 60 » (écrans qui l'acceptent depuis Windows).
- Mode nuit, seulement quand tu le demandes : « Active le mode nuit ». Jarvis répond alors par écrit sous le réacteur, sans voix ni bip (les rappels et le réveil sonnent quand même), et le reste même après un redémarrage, jusqu'à « désactive le mode nuit ». Des heures fixes sont possibles dans `config.json` : `"mode_nuit": {"debut": 22, "fin": 7}`.
- Voix : « prends une voix de femme », « reprends la voix d'Henri », « parle plus vite », « parle plus lentement », « parle à vitesse normale ».
- « Jarvis, qu'est-ce que tu sais faire ? » : il résume ses commandes.
- Mails, seulement quand tu les demandes : « est-ce que j'ai des nouveaux mails ? », « lis-moi mes mails » (expéditeur et objet des 5 derniers non lus), « lis-moi le premier mail ». Jarvis ne fait que lire : il n'envoie, ne supprime et ne déplace rien, les mails restent « non lus », et leur contenu n'est pas envoyé à Claude. Mise en place une fois, voir la rubrique [Mails](#mails).
- Mode enfant : « Active le mode enfant ». Les vidéos et la musique passent par YouTube Kids (« mets une vidéo de dinosaures »), les recherches Google sont filtrées (SafeSearch), les sites d'achat ne s'ouvrent pas, et Claude répond avec des mots simples. Quiz et devinettes (« on fait un quiz sur les animaux ? ») : une question à la fois, Jarvis attend la réponse. Longues histoires d'environ 10 minutes (« raconte-moi une histoire de pirates »), lues au fur et à mesure, avec la suite le lendemain (« raconte la suite »). « Désactive le mode enfant » pour revenir à la normale. Jarvis ne filtre que ce qu'on lui demande : ce n'est pas un contrôle parental.
- Mises à jour : au démarrage, Jarvis regarde s'il existe une nouvelle version sur GitHub. S'il en trouve une, il te le dit à ta demande suivante et te demande s'il peut l'installer ; il ne fait rien sans ton « oui ». Tes réglages, ta mémoire, tes rappels et tes listes sont gardés. Aussi à la voix : « Jarvis, cherche les mises à jour », « mets-toi à jour », « quelle est ta version ? ».

## Mails

Pour que Jarvis puisse lire tes mails, range une fois ton adresse et un mot de passe dans Windows (il n'est écrit dans aucun fichier). Ouvre PowerShell et tape, avec ton adresse :

```
cmdkey /generic:Jarvis-Mails /user:ton.adresse@icloud.com /pass
```

Windows demande alors le mot de passe (il ne s'affiche pas pendant la frappe). Avec iCloud, ce n'est pas ton mot de passe Apple mais un **mot de passe pour app**, à créer sur account.apple.com, rubrique « Connexion et sécurité », puis « Mots de passe pour app ». Jarvis utilise iCloud par défaut ; pour une autre messagerie, ajoute dans `config.json` par exemple `"mails": {"serveur": "imap.gmail.com"}`. Pour retirer l'accès : `cmdkey /delete:Jarvis-Mails`.

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
| `jarvis_pratique.py` | Calculs, conversions, chronomètre, listes, raccourcis clavier, son d'une application, mode sombre |
| `jarvis_web.py` | Le navigateur à la voix (clic sur un bouton ou un lien, défilement, lecture d'une page, recherche sur un site) |
| `jarvis_reglages.py` | Mode nuit, voix et vitesse, luminosité, Bluetooth |
| `jarvis_sources.py` | Les titres du jour (franceinfo, Le Monde) et la page du site suivi, lus directement depuis le PC pour le point du jour |
| `jarvis_mails.py` | La lecture des mails à la demande (sans rien modifier dans la messagerie) |
| `jarvis_enfant.py` | Le mode enfant : YouTube Kids, recherches filtrées, quiz, devinettes et longues histoires avec la suite |
| `jarvis_maj.py` | Les mises à jour : vérifie la dernière version sur GitHub au démarrage et l'installe après ton accord |
| `jarvis_affichage.py` | L'affichage rapide du réacteur et du panneau (pygame, 60 images/s) |
| `jarvis_systeme.py` | La surveillance du PC (processeur, mémoire, carte graphique, réseau) |
| `jarvis_tts.py` | La voix Windows de secours |
| `jarvis_config.py` | La lecture des réglages personnels (`config.json`) |
| `config.exemple.json` | Le modèle de réglages personnels à copier |
| `installateur/` | L'installateur : `Installer-Jarvis.bat` fait tout le travail ; `lanceur.cs` est le petit programme `.exe` qui porte l'icône du réacteur et lance ce `.bat` |
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
| 1.22 | Mode enfant (YouTube Kids, recherches filtrées, quiz, devinettes, longues histoires lues au fur et à mesure avec la suite) ; lecture des mails à la demande, sans rien modifier ; point du jour plus fiable (titres de franceinfo et du Monde, site suivi lu directement depuis le PC) ; « Jarvis » coupe la parole et enchaîne sur une nouvelle demande ; écoute mieux réglée (commandes mal entendues, « des actives » ne rallume plus le mode nuit) ; réponses plus naturelles et variées, salutation du jour, remerciements avec humour, petit son à la fin des longues tâches ; affichage : couleurs Vice City en veille, mode discret avec les jauges, icônes des jauges, reflet lumineux, réacteur qui danse avec la musique, regarde la souris et se fait doux la nuit, animations de minuit et d'anniversaire ; bip plus fort |
| 1.21 | Mises à jour automatiques : au démarrage, Jarvis vérifie s'il existe une nouvelle version sur GitHub, te l'annonce à ta demande suivante et l'installe seulement si tu dis « oui » (« Jarvis, cherche les mises à jour », « mets-toi à jour », « quelle est ta version ? ») ; le mode nuit ne s'active plus à heures fixes mais seulement quand tu le demandes, et reste actif après un redémarrage jusqu'à « désactive le mode nuit » |
| 1.20 | Nouvelles commandes, sans Claude : calculs et conversions (y compris monnaies), chronomètre, listes de courses et de tâches, raccourcis clavier (copier, coller, annuler...), avance et recul dans une vidéo, son d'une seule application, mode sombre ou clair, Bluetooth, luminosité ; navigateur à la voix (« clique sur… », « la deuxième vidéo », « le premier résultat », défilement, retour, lecture et résumé d'une page, recherche sur YouTube, Amazon, Google...) ; mode nuit (réponses écrites, sans voix) ; voix de femme et vitesse de parole ; « qu'est-ce que tu sais faire ? » ; corrections : la dictée n'abîme plus les longs textes, sans micro Jarvis attend au lieu de redémarrer en boucle, mots mal entendus mieux compris (« ma ville et Toulouse », « des oufs ») |
| 1.19 | Installateur automatique (`Installer-Jarvis.exe`) : installation, mise à jour, ajout de Claude et désinstallation en un double-clic ; Jarvis fonctionne aussi sans Claude (commandes immédiates) ; ville de la météo réglable à la voix (« Jarvis, ma ville est … ») ; plus rapide et plus léger ; sans micro, il attend qu'on en branche un au lieu de redémarrer en boucle ; calculatrice absente détectée ; mise au premier plan des fenêtres plus fiable |
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

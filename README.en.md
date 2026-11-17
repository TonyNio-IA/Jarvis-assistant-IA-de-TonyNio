# Jarvis, a French voice assistant for Windows 11

**Français : [README.md](README.md)** · **Current version: 1.23**

<p align="center"><img src="docs/jarvis.gif" alt="The Jarvis reactor: idle, listening, answering, reminder, compact mode" width="320"></p>

**▶ Video demo (6 min, in French): [watch on YouTube](https://www.youtube.com/watch?v=3Xd91q7618U)**

**Jarvis is a voice assistant for Windows 11 that speaks and understands French.** Say "Jarvis", then your request: it answers aloud and acts on your PC. It opens apps, manages windows, plays music, sets reminders, reads or translates copied text, and describes what is on screen. Simple requests are handled on the PC in about a second; everything else is sent to Claude.

An animated reactor sits in a corner of the screen and shows what Jarvis is doing: listening, thinking, answering.

> **Language note.** The voice commands, the spoken answers and the on-screen labels are in French only. This page is in English so the project is easier to find and understand, but you need to speak French to Jarvis.

## What you need

- **Windows 11** (64-bit) and a **microphone**.
- An Internet connection during setup, and about **3 GB** of free disk space.
- Optional: a **Claude subscription** (Pro or higher), to ask it anything. Without it, Jarvis answers the instant commands: time, weather, timers, windows, music.
- Nothing else to pay for: speech recognition and the voice use free tools.

## Installation

1. **Download the installer: [Installer-Jarvis.exe](https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio/releases/latest/download/Installer-Jarvis.exe)** (about 200 KB).
2. **Double-click it.** Windows will probably show a blue screen, "Windows protected your PC": this is normal for a small free program that is not signed by a paid publisher. Click **More info**, then **Run anyway**.
3. **Answer the two questions** (in French): your first name, and whether you want to use your Claude subscription. Then setup runs by itself (about ten minutes, depending on your connection and PC). It installs:
   - Python 3.14 (from python.org), in your user folder;
   - the Microsoft Visual C++ components: Windows asks for your permission, answer **Yes**;
   - Jarvis, its modules and its speech model, in `C:\Jarvis`;
   - Claude Code (from claude.ai), if you chose it;
   - a "Jarvis" shortcut on the desktop and at Windows startup.
4. **If you chose Claude**, your browser opens so you can sign in to your Claude account. On a new PC, it may first show its own welcome screen: skip it. Sign in, accept the authorization, then go back to the installer window.
5. **At the end, Jarvis starts.** The first launch takes a minute or two: it downloads its second speech model (Whisper). The very first check can also be slow on a new PC, while Windows examines the new files.

To get your local weather, say once: "**Jarvis, ma ville est** …" followed by the name of your town.

**Update, repair, add Claude or uninstall:** run the same file again. A copy is also kept in `C:\Jarvis` (Windows key + R, type `C:\Jarvis`, then Enter). A menu lets you update, uninstall, or add Claude if it is missing. Updating keeps your settings, its memory and your reminders.

**If your antivirus rejects the .exe file:** download [Installer-Jarvis.bat](https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio/releases/latest/download/Installer-Jarvis.bat) instead. It runs exactly the same setup, without the reactor icon. The code of both is readable in the project's `installateur` folder.

<details>
<summary>Manual installation (for the curious)</summary>

1. Download the project (green **Code** button, then **Download ZIP**) and unzip it, for example into `C:\Jarvis`.
2. Install Python 3.14, then the modules from that folder: `python -m pip install -r requirements.txt`
3. Download the French speech model **vosk-model-small-fr-0.22** from https://alphacephei.com/vosk/models and unzip it into the same folder.
4. Copy `config.exemple.json`, rename the copy to `config.json`, and put your first name in it.
5. Start Jarvis: `pythonw jarvis_gardien.py`. To start it with Windows, put a shortcut to this command in `shell:startup`.

</details>

## Personal settings

These files stay on your PC, in the Jarvis folder. They are not part of the published project.

| File | Content |
|---|---|
| `config.json` | Your first name, the topics of your daily briefing, a website to check, proper nouns you say often, and optional fixed night mode hours. Template: `config.exemple.json`. |
| `ville.txt` | Your town for the weather. The easiest way: say "Jarvis, ma ville est …" and it creates this file. Format: `Name;latitude;longitude` (example: `Paris;48.8566;2.3522`). Without this file, Jarvis gives the weather for Paris. |

Jarvis also creates its own files as you use it (memory, reminders, notes, lists, voice settings, app list, log). They never leave your PC either.

## What it can do

The commands below are the French phrases Jarvis understands, with their meaning.

**Talking to it**
- It wakes up when a sentence starts with "Jarvis" (a short beep tells you to speak), including while a video or music is playing; it then turns the PC sound down while it listens.
- You can chain another request within 3 seconds without saying "Jarvis" again.
- It remembers the conversation for 10 minutes. « Jarvis, nouvelle conversation » starts over.
- « Stop » or « Tais-toi » while it speaks: it stops. « Jarvis, répète »: it repeats its last answer.

**Instant commands, handled on the PC without Claude**
- Time, date and weather: « quelle heure est-il », « quel temps fait-il demain ».
- Volume and media: « monte le son », « mets en pause », « musique suivante ».
- Timers and reminders: « mets un minuteur de 10 minutes », « rappelle-moi à 18 h d'appeler le garage ». They survive a restart and show on the reactor.
- Apps and windows: « ouvre Chrome », « ferme la fenêtre », « mets Chrome à gauche », « mets la fenêtre en plein écran », « affiche le bureau ». The name of an open app is recognized even when misheard.
- Music: « mets Get Lucky de Daft Punk » plays it on YouTube.
- Files and screen: « cherche le fichier facture », « fais une capture d'écran ».
- Dictation: « dicte : je serai là dans dix minutes » types the sentence into the active window.
- Notes and memory: « note que... », « retiens que... », « qu'est-ce que tu as retenu ? », « oublie que... ».
- Power, always after confirmation: « éteins l'ordinateur », « redémarre l'ordinateur », « mets l'ordinateur en veille ».
- Routines: « Jarvis, bonjour » (date, time, weather, today's reminders, PC status) and « Jarvis, bonne nuit » (closes apps and puts the PC to sleep).
- PC status: « état du PC » gives processor, memory, the heaviest program and disk space.

**With Claude**
- Any question, and any action on the PC that is not an instant command.
- Screen: « qu'est-ce qu'il y a à l'écran ? », « explique-moi cette erreur ». Jarvis captures the active window and Claude looks at it.
- Copied text: « résume le texte copié », « traduis le texte sélectionné en anglais », « corrige le texte copié ». The result goes back to the clipboard, ready to paste.
- Daily briefing: « fais-moi le point du jour » gives the weather, the news, then your own topics.

**New in 1.20 (also instant, without Claude)**
- Maths and conversions: « combien font 15 % de 80 », « 3 miles en kilomètres », « 50 dollars en euros » (European Central Bank rates).
- Stopwatch: « lance un chrono », « arrête le chrono ». Lists: « ajoute du pain à la liste », « lis-moi la liste ».
- Keyboard shortcuts in the active window: « copie », « colle », « annule ça », « sélectionne tout », « enregistre ».
- Videos: « avance de 30 secondes ». One app's volume: « baisse le son de Chrome ».
- Browser by voice: « cherche des recettes sur YouTube », « clique sur Connexion », « clique sur la deuxième vidéo », « clique sur le premier résultat », « fais défiler », « reviens en arrière », « lis-moi cette page », « résume cette page ».
- Windows: dark or light mode, Bluetooth on or off, screen brightness (on screens that allow it from Windows).
- Night mode, only when you ask for it (« active le mode nuit »): answers are written under the reactor, with no voice or beep (reminders still ring). It stays on, even after a restart, until « désactive le mode nuit ». Fixed hours are possible in `config.json`: `"mode_nuit": {"debut": 22, "fin": 7}`.
- Voice: a female voice (« prends une voix de femme »), faster or slower speech. « Qu'est-ce que tu sais faire ? » lists the commands.

**New in 1.23**
- Météo-France weather warnings (Vigilance) for your département, found from your city: yellow, orange or red, announced once, with the reactor animated in the warning colour and a symbol. No account or key needed: Jarvis reads the Vigilance map that Météo-France publishes as open data on data.gouv.fr.
- Time in another city (« quelle heure est-il à Tokyo ? »), last download, reopen Chrome tabs (« où j'en étais ? »), « ferme tout » with confirmation, step-by-step recipes (« étape suivante »), relatives' birthdays reminded the day before and on the day, anecdotes, YouTube video summary, read the selected text (« lis ça »).
- One profile per household member (« crée un profil pour Marie », then « Jarvis, c'est Marie »): separate memory and notes; reminders, shopping list and city stay shared.
- Named kitchen timers, homework help and bedtime story for kids' profiles, a summary of the day, a morning song per profile, and optional speaker recognition to switch profiles by voice.
- Cinema mode, guest mode (no mails, notes or memory), reactor colours of your choice, and a guided first run for new users (one question at a time).

**New in 1.22**
- Kids mode, mails on request and a more reliable daily briefing (see below).
- Say « Jarvis » while it speaks: it stops at once and listens to your new request.
- More natural, varied answers, a greeting for the day, a small chime after long tasks.
- Display: Vice City sunset colours when idle, a compact gauges-only strip after 35 s, gauge icons, a light glint running around the panels and the reactor, the reactor dances with music, looks towards the mouse, dims at night, and celebrates midnight and your birthday.

**New in 1.21: updates**
- At startup, Jarvis checks GitHub for a new version. If there is one, it tells you at your next request and asks whether to install it; nothing happens without your « oui ». Your settings, memory, reminders and lists are kept. By voice too: « Jarvis, cherche les mises à jour », « mets-toi à jour », « quelle est ta version ? ».
- Night mode now turns on only when you ask for it, no longer at fixed hours.

**Mails, only when you ask** (« est-ce que j'ai des nouveaux mails ? », « lis-moi mes mails », « lis-moi le premier mail »)
- Read-only: Jarvis never sends, deletes or moves a mail, mails stay unread, and their content is not sent to Claude.
- One-time setup in PowerShell: `cmdkey /generic:Jarvis-Mails /user:your.address@icloud.com /pass` (Windows then asks for the password, stored by Windows, never in a file). For iCloud, use an app-specific password from account.apple.com. Other providers: `"mails": {"serveur": "imap.gmail.com"}` in `config.json`.

**Kids mode** (« active le mode enfant »)
- Videos and music open on YouTube Kids, Google searches use SafeSearch, shopping sites are not opened, and Claude answers in simple words.
- Quizzes and riddles, one question at a time; long stories of about 10 minutes, read aloud as they are written, with the next chapter the following day (« raconte la suite »).
- Jarvis only filters what it is asked to do: it is not a parental control.

**The reactor**
- A ring of marks draws the live sound spectrum: your voice when it listens, its own when it answers.
- The panel shows the time, the words understood as you speak, and live gauges for processor, memory, graphics, network and temperature.
- When idle it shrinks and hides its panel; it comes back when it hears you or when the mouse is over it.
- A pending timer or reminder empties the ring like a clock; when it goes off, a 5-second visual alert plays.

**Reliability**
- A watchdog restarts Jarvis if it crashes or if the microphone is unplugged. « Jarvis, redémarre-toi » restarts it on request.
- It starts with Windows, without a window.

## How it works

1. **Vosk** (offline) listens all the time and spots the word "Jarvis".
2. **Whisper** ("base" model, on the PC) transcribes the request more precisely. When Vosk and Whisper disagree, both versions are sent to Claude.
3. **Claude Code** stays open in the background (Sonnet model): a simple answer takes 1 to 2 seconds. It runs in a light mode (no extensions, four tools only) to use less of your quota.
4. **edge-tts** reads the answer with the French voice "Henri".

## Files

| File | Role |
|---|---|
| `jarvis_gardien.py` | Entry point: starts Jarvis and restarts it if it stops by itself |
| `jarvis_reacteur.py` | The animated reactor, which starts the listening |
| `jarvis_claude.py` | Listening, speech recognition and the dialogue with Claude |
| `jarvis_commandes.py` | The instant commands |
| `jarvis_fenetres.py` | Window management by voice |
| `jarvis_ecran.py` | Screen capture and clipboard |
| `jarvis_memoire.py` | Long-term memory |
| `jarvis_voix.py` | The natural voice (edge-tts) |
| `jarvis_pratique.py` | Maths, conversions, stopwatch, lists, keyboard shortcuts, per-app volume, dark mode |
| `jarvis_web.py` | The browser by voice (click a button or link, scroll, read a page, search a site) |
| `jarvis_reglages.py` | Night mode, voice and speed, brightness, Bluetooth |
| `jarvis_sources.py` | Today's headlines (franceinfo, Le Monde) and the followed site's home page, read directly from the PC for the daily briefing |
| `jarvis_mails.py` | Reads mails on request (never changes anything in the mailbox) |
| `jarvis_enfant.py` | Kids mode: YouTube Kids, filtered searches, quizzes, riddles and long stories with the next chapter |
| `jarvis_vigilance.py` | Météo-France weather warnings for your département |
| `jarvis_extras.py` | World time, last download, tabs, close all, step-by-step recipes, birthdays, cinema and guest modes, reactor colours, YouTube summary |
| `jarvis_profils.py` | One profile per household member (separate memory and notes) |
| `jarvis_locuteur.py` | Optional speaker recognition for profiles (needs `vosk-model-spk-0.4`) |
| `jarvis_famille.py` | Homework, bedtime, day summary, morning song per profile |
| `jarvis_accueil.py` | Guided first run for new users |
| `jarvis_maj.py` | Updates: checks the latest version on GitHub at startup and installs it once you agree |
| `jarvis_affichage.py` | Fast drawing of the reactor and the panel (pygame) |
| `jarvis_systeme.py` | PC monitoring (processor, memory, graphics, network) |
| `jarvis_tts.py` | The fallback Windows voice |
| `jarvis_config.py` | Reads the personal settings (`config.json`) |
| `config.exemple.json` | The template for personal settings |
| `installateur/` | The installer: `Installer-Jarvis.bat` does all the work; `lanceur.cs` is the small `.exe` program that carries the reactor icon and runs that `.bat` |
| `requirements.txt` | The required Python modules |
| `LICENSE.md` | The license (PolyForm Strict 1.0.0) |

The log file `jarvis.log`, in the Jarvis folder, records everything it hears and answers: it is the first place to look when something does not work.

## License and contributing

Jarvis is published under the **PolyForm Strict 1.0.0** license (file `LICENSE.md`). In short:

- you may download it and use it at home, for personal and noncommercial use;
- you may not modify it, or publish a copy or your own version of it;
- new features arrive with the versions published here.

An idea, a bug, a missing command? Open a request in the **Issues** tab, in French or in English: that is the way to move the project forward.

## Versions

The version history is in the French page: [README.md](README.md#versions).

# Jarvis, a French voice assistant for Windows 11

**Français : [README.md](README.md)** · **Current version: 1.18**

<p align="center"><img src="docs/jarvis.gif" alt="The Jarvis reactor: idle, listening, thinking, answering, reminder" width="320"></p>

**▶ Video demo (6 min, in French): [watch on YouTube](https://www.youtube.com/watch?v=3Xd91q7618U)**

**Jarvis is a voice assistant for Windows 11 that speaks and understands French.** Say "Jarvis", then your request: it answers aloud and acts on your PC. It opens apps, manages windows, plays music, sets reminders, reads or translates copied text, and describes what is on screen. Simple requests are handled on the PC in about a second; everything else is sent to Claude.

An animated reactor sits in a corner of the screen and shows what Jarvis is doing: listening, thinking, answering.

> **Language note.** The voice commands, the spoken answers and the on-screen labels are in French only. This page is in English so the project is easier to find and understand, but you need to speak French to Jarvis.

## What you need

- **Windows 11** and a **microphone**.
- **Python 3.14**.
- **Claude Code**, signed in with a Claude subscription (Pro or higher). Without it, only the instant commands work.
- Nothing else to pay for: speech recognition and the voice use free tools.

## Installation

1. Download the project (green **Code** button, then **Download ZIP**) and unzip it into the folder of your choice, for example `C:\Jarvis`.
2. Install the modules from that folder: `python -m pip install -r requirements.txt`
3. Download the French speech model **vosk-model-small-fr-0.22** from https://alphacephei.com/vosk/models and unzip it into the same folder. The Whisper model downloads by itself on first launch.
4. Copy `config.exemple.json`, rename the copy to `config.json`, and fill in your first name and your topics (see "Personal settings").
5. Start Jarvis: `pythonw jarvis_gardien.py`
6. To start it with Windows: create a shortcut to `pythonw.exe "C:\Jarvis\jarvis_gardien.py"` (working folder: the Jarvis folder) and put it in `shell:startup`.

## Personal settings

These files stay on your PC, in the Jarvis folder. They are not part of the published project.

| File | Content |
|---|---|
| `config.json` | Your first name, the topics of your daily briefing, a website to check, and proper nouns you say often. Template: `config.exemple.json`. |
| `ville.txt` | Your town for the weather, on one line: `Name;latitude;longitude` (example: `Paris;48.8566;2.3522`). Without this file, Jarvis gives the weather for Paris. |

Jarvis also creates its own files as you use it (memory, reminders, notes, app list, log). They never leave your PC either.

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
| `jarvis_affichage.py` | Fast drawing of the reactor and the panel (pygame) |
| `jarvis_systeme.py` | PC monitoring (processor, memory, graphics, network) |
| `jarvis_tts.py` | The fallback Windows voice |
| `jarvis_config.py` | Reads the personal settings (`config.json`) |
| `config.exemple.json` | The template for personal settings |
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

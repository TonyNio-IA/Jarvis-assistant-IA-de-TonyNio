/**
 * Jarvis — dépôt des rapports des utilisateurs (Google Apps Script, déployé en « application Web »).
 * Les PC de Jarvis peuvent seulement DÉPOSER ici : rien n'est lisible ni effaçable de l'extérieur,
 * sauf « effacer » qui supprime uniquement les rapports portant le numéro anonyme de ce PC.
 *
 * Genres reçus (champ "genre") :
 *   signal        : compteur anonyme (id, version, windows) -> tableau des utilisateurs
 *   rapport       : rapport technique ou complet            -> dossier Rapports
 *   probleme      : « Signaler un problème »                -> dossier Problèmes
 *   idee          : « Proposer une amélioration »           -> dossier Idées
 *   questionnaire : réponses au questionnaire               -> dossier Questionnaires
 *   effacer       : « Effacer mes données »                 -> supprime les fichiers de cet id
 */
var DOSSIER_RACINE = 'Jarvis - rapports des utilisateurs';
var TAILLE_MAX = 400 * 1024;          // 400 Ko par envoi, au-delà c'est refusé
var CONSERVATION_JOURS = 365;         // les rapports sont effacés au bout de 12 mois
var SOUS_DOSSIERS = {rapport: 'Rapports', probleme: 'Problèmes', idee: 'Idées', questionnaire: 'Questionnaires'};

function doPost(e) {
  try {
    var brut = (e && e.postData && e.postData.contents) || '';
    if (brut.length > TAILLE_MAX) return reponse({ok: false, raison: 'trop gros'});
    var d = JSON.parse(brut);
    var id = String(d.id || '').replace(/[^a-f0-9]/gi, '').slice(0, 32);
    if (id.length < 16) return reponse({ok: false, raison: 'id'});
    var genre = String(d.genre || '');
    if (genre === 'signal') return reponse(signal(id, d));
    if (genre === 'effacer') return reponse(effacer(id));
    if (!SOUS_DOSSIERS[genre]) return reponse({ok: false, raison: 'genre'});
    var dossier = sousDossier(SOUS_DOSSIERS[genre]);
    var date = Utilities.formatDate(new Date(), 'Europe/Paris', 'yyyy-MM-dd_HH-mm-ss');
    dossier.createFile(date + '_' + id + '.json', JSON.stringify(d, null, 1), 'application/json');
    signal(id, d);
    return reponse({ok: true});
  } catch (err) {
    return reponse({ok: false, raison: String(err).slice(0, 120)});
  }
}

function doGet() {
  return ContentService.createTextOutput('Dépôt des rapports de Jarvis : en service.');
}

function reponse(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function racine() {
  var it = DriveApp.getFoldersByName(DOSSIER_RACINE);
  return it.hasNext() ? it.next() : DriveApp.createFolder(DOSSIER_RACINE);
}

function sousDossier(nom) {
  var r = racine();
  var it = r.getFoldersByName(nom);
  return it.hasNext() ? it.next() : r.createFolder(nom);
}

function tableau() {
  var r = racine();
  var it = r.getFilesByName('Utilisateurs de Jarvis');
  var ss;
  if (it.hasNext()) {
    ss = SpreadsheetApp.open(it.next());
  } else {
    ss = SpreadsheetApp.create('Utilisateurs de Jarvis');
    DriveApp.getFileById(ss.getId()).moveTo(r);
    var f = ss.getSheets()[0];
    f.setName('PC');
    f.appendRow(['Numéro anonyme', 'Premier signal', 'Dernier signal', 'Version de Jarvis', 'Windows', 'Niveau']);
    var b = ss.insertSheet('Résumé');
    b.getRange('A1:A5').setValues([['Installations (PC différents)'], ['Actifs dans la dernière heure'],
      ["Actifs aujourd'hui"], ['Actifs ces 30 derniers jours'], ['Mis à jour']]);
    b.getRange('B1:B5').setFormulas([['=COUNTA(PC!A2:A)'], ['=SUMPRODUCT(N(PC!C2:C>NOW()-1/24))'],
      ['=SUMPRODUCT(N(PC!C2:C>=TODAY()))'], ['=SUMPRODUCT(N(PC!C2:C>NOW()-30))'], ['=NOW()']]);
  }
  return ss;
}

function signal(id, d) {
  var verrou = LockService.getScriptLock();
  verrou.waitLock(20000);
  try {
    var f = tableau().getSheetByName('PC');
    var trouve = f.getRange('A:A').createTextFinder(id).matchEntireCell(true).findNext();
    var maintenant = new Date();
    var version = String(d.version || '').slice(0, 20);
    var windows = String(d.windows || '').slice(0, 40);
    var niveau = String(d.niveau || '').slice(0, 20);
    if (trouve) {
      f.getRange(trouve.getRow(), 3, 1, 4).setValues([[maintenant, version, windows, niveau]]);
    } else {
      f.appendRow([id, maintenant, maintenant, version, windows, niveau]);
    }
  } finally {
    verrou.releaseLock();
  }
  return {ok: true};
}

function effacer(id) {
  var n = 0;
  var dossiers = racine().getFolders();
  while (dossiers.hasNext()) {
    var fichiers = dossiers.next().searchFiles('title contains "' + id + '"');
    while (fichiers.hasNext()) { fichiers.next().setTrashed(true); n++; }
  }
  var f = tableau().getSheetByName('PC');
  var trouve = f.getRange('A:A').createTextFinder(id).matchEntireCell(true).findNext();
  if (trouve) f.deleteRow(trouve.getRow());
  return {ok: true, effaces: n};
}

/** Lancé chaque jour par un déclencheur : efface les rapports de plus de 12 mois. */
function nettoyer() {
  var limite = new Date(Date.now() - CONSERVATION_JOURS * 86400000);
  var dossiers = racine().getFolders();
  while (dossiers.hasNext()) {
    var fichiers = dossiers.next().getFiles();
    while (fichiers.hasNext()) {
      var x = fichiers.next();
      if (x.getDateCreated() < limite) x.setTrashed(true);
    }
  }
}

/** À lancer une fois à la main : crée le dossier, le tableau et le nettoyage quotidien. */
function installer() {
  tableau();
  ['Rapports', 'Problèmes', 'Idées', 'Questionnaires'].forEach(sousDossier);
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('nettoyer').timeBased().everyDays(1).atHour(4).create();
}

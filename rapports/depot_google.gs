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
    var ligne;
    if (trouve) {
      ligne = trouve.getRow();
      f.getRange(ligne, 3, 1, 4).setValues([[maintenant, version, windows, niveau]]);
    } else {
      f.appendRow([id, maintenant, maintenant, version, windows, niveau]);
      ligne = f.getLastRow();
    }
    // Depuis la 1.50 : le nom que l'utilisateur a donné lui-même à son PC (colonne G, seulement s'il y en a un)
    // et le type de matériel envoyé par le compteur anonyme (colonne I). La colonne H reste libre pour les notes.
    if (f.getRange(1, 9).getValue() === '') f.getRange(1, 9).setValue('Matériel (compteur anonyme)');
    var nom = String(d.nom || '').replace(/[\r\n\t]/g, ' ').trim().slice(0, 40);
    if (nom) f.getRange(ligne, 7).setValue(nom);
    var m = d.materiel;
    if (m && typeof m === 'object') {
      var morceaux = [];
      if (m.processeur) morceaux.push(String(m.processeur).slice(0, 80) + (m.coeurs ? ' (' + m.coeurs + ' cœurs)' : ''));
      if (m.memoire_go) morceaux.push(m.memoire_go + ' Go');
      if (m.carte_graphique) morceaux.push(String(m.carte_graphique).slice(0, 120));
      else if (m.cartes_graphiques && m.cartes_graphiques.length) {        // (rapport technique : liste de cartes)
        morceaux.push(m.cartes_graphiques.map(function (c) { return String((c && c.nom) || ''); })
          .filter(String).join(' + ').slice(0, 120));
      }
      if (m.portable === true) morceaux.push('portable');
      if (m.portable === false) morceaux.push('fixe');
      if (morceaux.length) f.getRange(ligne, 9).setValue(morceaux.join(', ').slice(0, 300));
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


// =============================================================================================
//  Exploitation des rapports (tâches automatiques, aucun accès de l'extérieur)
//   - rangerMessages : chaque jour, les problèmes et idées reçus sont recopiés dans l'onglet
//                      « Idées et problèmes » du tableau ; la colonne « Fait dans la version » se
//                      remplit quand c'est corrigé, pour « Vous l'avez demandé, on l'a fait ».
//   - alerteVersions : chaque jour, un mail si les erreurs montent nettement après une nouvelle version.
//   - resumeHebdo    : chaque lundi matin, un mail avec le résumé de la semaine.
// =============================================================================================

function destinataire() { return Session.getEffectiveUser().getEmail(); }
function dateFr(d) { return Utilities.formatDate(d, 'Europe/Paris', 'dd/MM/yyyy HH:mm'); }
function court(id) { return String(id || '').slice(0, 6); }

/** Les fichiers JSON d'un sous-dossier reçus depuis une date, du plus ancien au plus récent. */
function fichiersDepuis(nomDossier, depuis) {
  var res = [], it = sousDossier(nomDossier).getFiles();
  while (it.hasNext()) {
    var f = it.next();
    if (f.getDateCreated() < depuis) continue;
    try { res.push({nom: f.getName(), date: f.getDateCreated(), d: JSON.parse(f.getBlob().getDataAsString())}); } catch (e) {}
  }
  res.sort(function (a, b) { return a.date - b.date; });
  return res;
}

function compter(liste) {
  var c = {};
  liste.forEach(function (x) { if (x === undefined || x === null || x === '') return; c[x] = (c[x] || 0) + 1; });
  return c;
}

function premiers(c, n) {
  return Object.keys(c).sort(function (a, b) { return c[b] - c[a]; }).slice(0, n)
    .map(function (k) { return k + (c[k] > 1 ? ' (' + c[k] + ' fois)' : ''); });
}

function comparerVersions(a, b) {
  var x = String(a).split(/\D+/).map(Number), y = String(b).split(/\D+/).map(Number);
  for (var i = 0; i < Math.max(x.length, y.length); i++) {
    var d = (x[i] || 0) - (y[i] || 0);
    if (d) return d;
  }
  return 0;
}

/** Par version : nombre de rapports, de demandes et d'erreurs. */
function parVersion(rapports) {
  var pv = {};
  rapports.forEach(function (r) {
    var d = r.d, s = d.statistiques || {}, v = String(d.version || '?');
    pv[v] = pv[v] || {rapports: 0, demandes: 0, erreurs: 0, pc: {}};
    pv[v].rapports++;
    pv[v].demandes += s.demandes || 0;
    pv[v].erreurs += (d.erreurs || []).length;
    pv[v].pc[d.id] = true;
  });
  return pv;
}

/** Recopie les problèmes et idées reçus dans l'onglet « Idées et problèmes » du tableau. */
function rangerMessages() {
  var ss = tableau();
  var f = ss.getSheetByName('Idées et problèmes');
  if (!f) {
    f = ss.insertSheet('Idées et problèmes');
    f.appendRow(['Reçu le', 'Genre', 'Version', 'PC', 'Message', 'Fait dans la version', 'Fichier']);
    f.setFrozenRows(1);
    f.setColumnWidth(5, 520);
  }
  var deja = {};
  f.getRange('G:G').getValues().forEach(function (l) { deja[l[0]] = true; });
  var depuis = new Date(Date.now() - CONSERVATION_JOURS * 86400000);
  [['Problèmes', 'Problème'], ['Idées', 'Idée']].forEach(function (g) {
    fichiersDepuis(g[0], depuis).forEach(function (m) {
      if (deja[m.nom]) return;
      f.appendRow([m.date, g[1], String(m.d.version || ''), court(m.d.id), String(m.d.texte || '').slice(0, 2000), '', m.nom]);
    });
  });
}

/** Un mail si, sur 7 jours, la dernière version fait nettement plus d'erreurs que la précédente. */
function alerteVersions() {
  var pv = parVersion(fichiersDepuis('Rapports', new Date(Date.now() - 7 * 86400000)));
  var vs = Object.keys(pv).filter(function (v) { return v !== '?'; }).sort(comparerVersions);
  if (vs.length < 2) return;
  var nv = vs[vs.length - 1], av = vs[vs.length - 2], n = pv[nv], a = pv[av];
  var tn = n.erreurs / Math.max(n.demandes, 1), ta = a.erreurs / Math.max(a.demandes, 1);
  var props = PropertiesService.getScriptProperties();
  if (props.getProperty('alerte_' + nv) || n.rapports < 3 || n.erreurs < 3 || tn <= 2 * ta) return;
  props.setProperty('alerte_' + nv, dateFr(new Date()));
  MailApp.sendEmail(destinataire(), 'Jarvis : plus d\'erreurs depuis la version ' + nv,
    'Depuis la version ' + nv + ', les PC qui envoient des rapports font plus d\'erreurs :\n\n' +
    '- version ' + nv + ' : ' + n.erreurs + ' erreur(s) pour ' + n.demandes + ' demandes (' + Object.keys(n.pc).length + ' PC)\n' +
    '- version ' + av + ' : ' + a.erreurs + ' erreur(s) pour ' + a.demandes + ' demandes (' + Object.keys(a.pc).length + ' PC)\n\n' +
    'Le détail des erreurs est dans les rapports du dossier « ' + DOSSIER_RACINE + ' » de ton Google Drive.\n' +
    'Demande à Claude de les regarder pour trouver la cause.');
}

/** Chaque lundi matin : le résumé de la semaine, par mail. */
function resumeHebdo() {
  rangerMessages();
  var depuis = new Date(Date.now() - 7 * 86400000);
  var pc = tableau().getSheetByName('PC').getDataRange().getValues().slice(1);
  var actifs = pc.filter(function (r) { return r[2] instanceof Date && r[2] >= depuis; });
  var nouveaux = pc.filter(function (r) { return r[1] instanceof Date && r[1] >= depuis; }).length;
  var rapports = fichiersDepuis('Rapports', depuis), problemes = fichiersDepuis('Problèmes', depuis);
  var idees = fichiersDepuis('Idées', depuis), questions = fichiersDepuis('Questionnaires', depuis);
  var demandes = 0, claude = 0, tablette = 0, faux = 0, incompris = [], erreurs = [], ateliers = [];
  rapports.forEach(function (r) {
    var d = r.d, s = d.statistiques || {};
    demandes += s.demandes || 0;
    claude += s.claude || 0;
    tablette += (s.par_origine || {}).tablette || 0;
    faux += (d.faux_reveils || {}).nombre || 0;
    (d.incompris || []).forEach(function (x) { incompris.push(x.texte); });
    (d.erreurs || []).forEach(function (x) {
      erreurs.push((x.type || x.source || '?') + ' : ' + String(x.message || '').slice(0, 90) + (x.ou ? ' [' + x.ou.join(', ') + ']' : ''));
    });
    (d.ateliers || []).forEach(function (x) { ateliers.push(x.nom + ' : ' + x.fin); });
  });
  var pv = parVersion(rapports), L = [];
  function liste(titre, elements, vide) {
    L.push('', titre);
    if (!elements.length) L.push('- ' + vide);
    elements.forEach(function (x) { L.push('- ' + x); });
  }
  L.push('Résumé de la semaine de Jarvis, du ' + dateFr(depuis) + ' au ' + dateFr(new Date()) + '.');
  liste('UTILISATEURS', ['PC installés en tout : ' + pc.length, 'Actifs cette semaine : ' + actifs.length + ' (dont ' + nouveaux + ' nouveaux)',
    'Versions des PC actifs : ' + (premiers(compter(actifs.map(function (r) { return String(r[3]); })), 10).join(', ') || 'aucune')], '');
  liste('RAPPORTS REÇUS : ' + rapports.length, ['Demandes : ' + demandes + ' (dont ' + claude + ' envoyées à Claude, ' + tablette + ' faites sur une tablette)',
    'Faux réveils : ' + faux].concat(Object.keys(pv).sort(comparerVersions).map(function (v) {
      return 'Version ' + v + ' : ' + pv[v].rapports + ' rapport(s) de ' + Object.keys(pv[v].pc).length + ' PC, ' + pv[v].erreurs + ' erreur(s) pour ' + pv[v].demandes + ' demandes';
    })), '');
  liste('ERREURS LES PLUS FRÉQUENTES', premiers(compter(erreurs), 10), 'aucune');
  liste('PHRASES MAL COMPRISES', premiers(compter(incompris), 15), 'aucune');
  liste('ATELIERS DES ENFANTS ARRÊTÉS', premiers(compter(ateliers), 10), 'aucun');
  liste('PROBLÈMES SIGNALÉS : ' + problemes.length, problemes.map(function (m) {
    return dateFr(m.date) + ', version ' + (m.d.version || '?') + ', PC ' + court(m.d.id) + ' : ' + String(m.d.texte || '').slice(0, 600);
  }), 'aucun');
  liste('IDÉES PROPOSÉES : ' + idees.length, idees.map(function (m) {
    return dateFr(m.date) + ', version ' + (m.d.version || '?') + ', PC ' + court(m.d.id) + ' : ' + String(m.d.texte || '').slice(0, 600);
  }), 'aucune');
  liste('QUESTIONNAIRES : ' + questions.length, questions.map(function (q) {
    var c = {};
    Object.keys(q.d).forEach(function (k) { if (['id', 'genre', 'windows', 'niveau'].indexOf(k) < 0) c[k] = q.d[k]; });
    return JSON.stringify(c).slice(0, 600);
  }), 'aucun');
  L.push('', 'Les idées et problèmes sont aussi rangés dans l\'onglet « Idées et problèmes » du tableau « Utilisateurs de Jarvis ».',
    'Tout le détail est dans le dossier « ' + DOSSIER_RACINE + ' » de ton Google Drive.');
  MailApp.sendEmail(destinataire(), 'Jarvis : résumé de la semaine', L.join('\n'));
}

/** À lancer une fois à la main : met en place les tâches automatiques (et garde le nettoyage). */
function installerTaches() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('nettoyer').timeBased().everyDays(1).atHour(4).create();
  ScriptApp.newTrigger('rangerMessages').timeBased().everyHours(6).create();
  ScriptApp.newTrigger('alerteVersions').timeBased().everyDays(1).atHour(9).create();
  ScriptApp.newTrigger('resumeHebdo').timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(8).create();
  rangerMessages();
}

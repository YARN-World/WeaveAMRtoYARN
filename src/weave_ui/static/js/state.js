// What the page remembers between reloads, and what it does not.
//
// The rule here is that stored data should never be able to masquerade as
// something it is not. Two things follow from that:
//
//   * anchors are filed under the corpus they belong to, so two corpora that
//     happen to share sentence ids — snt1, or the FraCaS ids — cannot inherit
//     each other's anchoring;
//   * every entry records where it came from, so an anchor a person edited is
//     distinguishable from one the machine guessed. Without that, a computed
//     anchor is reused on the next run as though it had been curated, and
//     changing the anchorer has no visible effect.
//
// The UD parse is deliberately NOT stored: a CoNLL-U file for a corpus of any
// size does not fit, and half a corpus of UD would be worse than none. The
// page says so rather than quietly falling back to a parser.

const KEY = {
  corpus: 'weave_ui.corpus',      // {id, name, loadedAt, sentences:[{id,snt,amr}]}
  anchors: 'weave_ui.anchors',    // {corpusId: {sentenceId: Entry}}
  current: 'weave_ui.current',    // {corpusId, sentenceId}
};

// Entry = {anchors: {var: token}, source: 'manual'|'imported'|'computed', savedAt}

/** Sources that a person stands behind, and which a run must not overwrite. */
export const CURATED = ['manual', 'imported'];

export const corpus = {
  id: null,
  name: null,
  sentences: [],
  conllu: {},      // memory only, see above
  results: {},
  curId: null,
  running: false,
};

/** Listeners for anything that should redraw the storage panel. */
const watchers = [];
export const onStorageChange = fn => watchers.push(fn);
const announce = () => watchers.forEach(fn => fn());

/** The last write that failed, so the page can say so instead of guessing. */
export let lastStorageError = null;

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    lastStorageError = null;
    return true;
  } catch (error) {
    // Quota exhaustion and private browsing both land here. Swallowing it
    // would leave the page showing data that was never saved.
    lastStorageError = error && error.name === 'QuotaExceededError'
      ? 'Browser storage is full — this was not saved.'
      : `Could not save: ${error}`;
    announce();
    return false;
  }
}

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (_) {
    return fallback;
  }
}

// ── corpora ─────────────────────────────────────────────────────────────────

/** Identify a corpus by name and size, so reloading the same file matches. */
export function corpusIdFor(name, sentences) {
  return `${name}#${sentences.length}`;
}

export function saveCorpus(name, sentences) {
  corpus.id = corpusIdFor(name, sentences);
  corpus.name = name;
  corpus.sentences = sentences;
  const ok = write(KEY.corpus, {
    id: corpus.id, name, loadedAt: new Date().toISOString(), sentences,
  });
  announce();
  return ok;
}

export function restoreCorpus() {
  const stored = read(KEY.corpus, null);
  if (!stored || !stored.sentences) return null;
  corpus.id = stored.id;
  corpus.name = stored.name;
  corpus.sentences = stored.sentences;
  return stored;
}

// ── anchors ─────────────────────────────────────────────────────────────────

const allAnchors = () => read(KEY.anchors, {});

/** Every stored entry for the loaded corpus. */
export function storedAnchors(corpusId = corpus.id) {
  return corpusId ? (allAnchors()[corpusId] || {}) : {};
}

export function anchorEntry(sentenceId, corpusId = corpus.id) {
  return storedAnchors(corpusId)[sentenceId] || null;
}

/** Just the mapping, for a caller that does not care where it came from. */
export function anchorsFor(sentenceId, corpusId = corpus.id) {
  const entry = anchorEntry(sentenceId, corpusId);
  return entry ? entry.anchors : null;
}

export function saveAnchors(sentenceId, anchors, source, corpusId = corpus.id) {
  if (!corpusId) return false;
  const all = allAnchors();
  const forCorpus = all[corpusId] || (all[corpusId] = {});
  forCorpus[sentenceId] = {
    anchors, source, savedAt: new Date().toISOString(),
  };
  const ok = write(KEY.anchors, all);
  announce();
  return ok;
}

/** Import a whole dictionary at once, marked as coming from a file. */
export function importAnchors(dictionary, corpusId = corpus.id) {
  if (!corpusId) return 0;
  const all = allAnchors();
  const forCorpus = all[corpusId] || (all[corpusId] = {});
  const savedAt = new Date().toISOString();
  let count = 0;
  for (const [sentenceId, anchors] of Object.entries(dictionary)) {
    forCorpus[sentenceId] = {anchors, source: 'imported', savedAt};
    count++;
  }
  write(KEY.anchors, all);
  announce();
  return count;
}

export function clearAnchors(corpusId = corpus.id) {
  const all = allAnchors();
  delete all[corpusId];
  write(KEY.anchors, all);
  announce();
}

export function clearEverything() {
  Object.values(KEY).forEach(key => {
    try { localStorage.removeItem(key); } catch (_) {}
  });
  corpus.id = corpus.name = corpus.curId = null;
  corpus.sentences = [];
  corpus.conllu = {};
  corpus.results = {};
  announce();
}

/** Plain {sentenceId: {var: token}}, for download. */
export function exportAnchors(corpusId = corpus.id) {
  return Object.fromEntries(
    Object.entries(storedAnchors(corpusId)).map(([id, e]) => [id, e.anchors])
  );
}

// ── what is stored, for the panel ───────────────────────────────────────────

export function storageSummary() {
  const entries = Object.values(storedAnchors());
  const bySource = {};
  for (const entry of entries) {
    bySource[entry.source] = (bySource[entry.source] || 0) + 1;
  }
  let bytes = 0;
  for (const key of Object.values(KEY)) {
    bytes += (localStorage.getItem(key) || '').length;
  }
  const otherCorpora = Object.keys(allAnchors()).filter(id => id !== corpus.id);
  return {
    corpusName: corpus.name,
    sentences: corpus.sentences.length,
    anchored: entries.length,
    bySource,
    curated: entries.filter(e => CURATED.includes(e.source)).length,
    computed: entries.filter(e => !CURATED.includes(e.source)).length,
    conlluLoaded: Object.keys(corpus.conllu).length,
    bytes,
    otherCorpora: otherCorpora.length,
    error: lastStorageError,
  };
}

// ── current selection ───────────────────────────────────────────────────────

export function saveCurrent(sentenceId) {
  corpus.curId = sentenceId;
  write(KEY.current, {corpusId: corpus.id, sentenceId});
}

export function restoreCurrent() {
  const stored = read(KEY.current, null);
  // A selection only means something within the corpus it was made in.
  return stored && stored.corpusId === corpus.id ? stored.sentenceId : null;
}

// ── migration ───────────────────────────────────────────────────────────────

/**
 * Move a store written before anchors were filed by corpus.
 *
 * Those anchors have no corpus and no provenance. They are attached to
 * whatever corpus is restored and marked `imported` rather than `manual`:
 * some were hand-made and some were computed, and there is no way to tell
 * which, so claiming they were curated would be the very confusion this is
 * meant to remove.
 */
export function migrateLegacyStore() {
  const legacy = read('amr2yarn_anchors', null);
  if (!legacy || !Object.keys(legacy).length) return 0;

  const stored = read(KEY.corpus, null);
  if (!stored) return 0;

  const all = allAnchors();
  const forCorpus = all[stored.id] || (all[stored.id] = {});
  const savedAt = new Date().toISOString();
  let moved = 0;
  for (const [sentenceId, anchors] of Object.entries(legacy)) {
    if (forCorpus[sentenceId]) continue;
    forCorpus[sentenceId] = {anchors, source: 'imported', savedAt};
    moved++;
  }
  write(KEY.anchors, all);
  try { localStorage.removeItem('amr2yarn_anchors'); } catch (_) {}
  announce();
  return moved;
}

/** Base anchors from a server response, with the user's edits applied. */
export function mergeAnchors(anchorData, edits) {
  const merged = {};
  if (anchorData) {
    for (const [variable, info] of Object.entries(anchorData.vars)) {
      if (info.anchor) merged[variable] = info.anchor;
    }
  }
  for (const [variable, tokenId] of Object.entries(edits || {})) {
    if (tokenId === null) delete merged[variable];
    else merged[variable] = tokenId;
  }
  return merged;
}
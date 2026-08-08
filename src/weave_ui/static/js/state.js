// Corpus state, and the localStorage it survives a reload in.
//
// Kept apart from the modules that use it so the corpus runner and the corpus
// browser can both read it without importing each other.

const LS_CORPUS = 'amr2yarn_corpus';    // [{id, snt, amr}]
const LS_ANCHORS = 'amr2yarn_anchors';  // {sentence_id: {var: token_id}}
const LS_CUR = 'amr2yarn_cur_id';       // last selected sentence

export const corpus = {
  sentences: [],   // [{id, snt, amr}]
  conllu: {},      // {sentence_id: conllu block}
  results: {},     // {sentence_id: {yarn_grs?, yarn_grs_error?, anchor_dict, error?}}
  curId: null,
  running: false,
};

// localStorage throws in private browsing and when the quota is full; a corpus
// that fails to persist should still be usable in this session.
function safely(action, fallback) {
  try { return action(); } catch (_) { return fallback; }
}

export const loadStoredAnchors = () =>
  safely(() => JSON.parse(localStorage.getItem(LS_ANCHORS) || '{}'), {});

export const saveStoredAnchors = data =>
  safely(() => localStorage.setItem(LS_ANCHORS, JSON.stringify(data)));

export const saveCorpus = sentences =>
  safely(() => localStorage.setItem(LS_CORPUS, JSON.stringify(sentences)));

export const restoreCorpus = () =>
  safely(() => JSON.parse(localStorage.getItem(LS_CORPUS) || '[]'), []);

export const saveCurrentId = id => safely(() => localStorage.setItem(LS_CUR, id));

export const restoreCurrentId = () => safely(() => localStorage.getItem(LS_CUR), null);

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

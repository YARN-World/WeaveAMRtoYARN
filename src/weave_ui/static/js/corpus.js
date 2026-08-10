// Loading a corpus, choosing a sentence, and converting the whole thing.

import { byId, escH, postJson } from './util.js';
import { toggleAnc, updateSntBar } from './tabs.js';
import {
  CURATED, anchorEntry, anchorsFor, corpus, importAnchors, restoreCorpus,
  restoreCurrent, saveAnchors, saveCorpus, saveCurrent, storedAnchors,
} from './state.js';
import { CorpusBrowser } from './browser.js';
import { downloadSampleZip } from './editor.js';

const LABEL_LIMIT = 40;

function optionLabel(sentence) {
  if (!sentence.snt) return sentence.id;
  const clipped = sentence.snt.slice(0, LABEL_LIMIT);
  const ellipsis = sentence.snt.length > LABEL_LIMIT ? '…' : '';
  return `${sentence.id}  –  ${clipped}${ellipsis}`;
}

function setMeta(text) {
  byId('corpus-meta').textContent = text;
}

/** Split an AMR file into blocks. A block with no ::id cannot be addressed. */
export function parseAmrCorpus(text) {
  const found = [];
  for (const block of text.split(/\n\n+/)) {
    const body = block.trim();
    if (!body) continue;
    const identifier = body.match(/^#\s*::id\s+(\S+)/m);
    if (!identifier) continue;
    const sentence = body.match(/^#\s*::snt\s+(.+)/m);
    found.push({
      id: identifier[1],
      snt: sentence ? sentence[1].trim() : '',
      amr: body,
    });
  }
  return found;
}

function readFile(input, onText) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = event => onText(event.target.result, file);
  reader.readAsText(file);
  input.value = '';  // so choosing the same file again still fires
}

export function onCorpusFile(input) {
  readFile(input, (text, file) => {
    const sentences = parseAmrCorpus(text);
    const saved = saveCorpus(file.name, sentences);
    renderCorpusList(sentences);
    setMeta(`${sentences.length} sentences loaded from ${file.name}`
      + (saved ? '' : ' (too large to keep between reloads)'));
  });
}

export function onAnchorFile(input) {
  readFile(input, (text, file) => {
    let data;
    try {
      data = JSON.parse(text);
    } catch (error) {
      alert('Invalid anchor JSON: ' + error);
      return;
    }
    if (!data || typeof data !== 'object') return;

    // Two shapes are accepted: a whole corpus, {sent_id: {var: token}}, or one
    // sentence's {var: token}. They are told apart by whether the first value
    // is itself an object.
    const keys = Object.keys(data);
    const wholeCorpus = keys.length > 0
      && typeof data[keys[0]] === 'object' && data[keys[0]] !== null;

    if (!corpus.id) {
      alert('Load a corpus first — anchors are stored against the corpus they belong to.');
      return;
    }
    let count;
    if (wholeCorpus) {
      count = importAnchors(data);
      const known = new Set(corpus.sentences.map(s => s.id));
      const strays = Object.keys(data).filter(id => !known.has(id)).length;
      setMeta(`${count} anchored sentences from ${file.name}`
        + (strays ? ` — ${strays} id(s) are not in this corpus` : ''));
    } else if (corpus.curId) {
      saveAnchors(corpus.curId, data, 'imported');
      setMeta(`anchors for ${corpus.curId} from ${file.name}`);
    } else {
      alert('Select a sentence first to attach single-sentence anchors.');
      return;
    }
    if (corpus.curId) applyStoredAnchors(corpus.curId);
  });
}

export function onConlluCorpusFile(input) {
  readFile(input, (text, file) => {
    const parses = {};
    let position = 0;
    for (const block of text.split(/\n\n+/)) {
      const body = block.trim();
      if (!body) continue;
      const declared = body.match(/^#\s*sent_id\s*=\s*(\S+)/m);
      if (declared) {
        parses[declared[1]] = body;
      } else if (corpus.sentences[position]) {
        // No sent_id: fall back to the corpus order, which is how hand-made
        // CoNLL-U usually arrives.
        parses[corpus.sentences[position].id] = body;
      }
      position++;
    }
    corpus.conllu = parses;
    const count = Object.keys(parses).length;
    setMeta(`${count} CoNLL-U parses loaded from ${file.name}`);
    byId('clear-conllu-btn').style.display = count ? '' : 'none';
  });
}

export function clearCorpusConllu() {
  corpus.conllu = {};
  byId('clear-conllu-btn').style.display = 'none';
  setMeta('CoNLL-U cleared (will use Stanza)');
  setTimeout(() => {
    if (corpus.sentences.length) setMeta(`${corpus.sentences.length} sentences loaded`);
  }, 2000);
}

function fillSelect(sentences) {
  const select = byId('corpus-select');
  select.innerHTML = '';
  for (const sentence of sentences) {
    const option = document.createElement('option');
    option.value = sentence.id;
    option.textContent = optionLabel(sentence);
    select.appendChild(option);
  }
  return select;
}

export function renderCorpusList(sentences) {
  const select = fillSelect(sentences);
  const shown = sentences.length ? 'block' : 'none';
  select.style.display = shown;
  byId('corpus-search').style.display = shown;
  byId('corpus-run-row').style.display = sentences.length ? 'flex' : 'none';

  const lastId = restoreCurrent();
  if (lastId && sentences.some(s => s.id === lastId)) select.value = lastId;
}

export function filterCorpus(query) {
  const needle = query.toLowerCase();
  fillSelect(!needle ? corpus.sentences : corpus.sentences.filter(s =>
    s.id.toLowerCase().includes(needle) || s.snt.toLowerCase().includes(needle)
  ));
}

export function selectSentence(id) {
  const sentence = corpus.sentences.find(s => s.id === id);
  if (!sentence) return;
  saveCurrent(id);
  byId('amr-input').value = sentence.amr;
  byId('corpus-cur').textContent = id;
  applyStoredAnchors(id);
  updateSntBar(sentence.amr);
  if (byId('corpus-browser').classList.contains('active')) CorpusBrowser.load(id);
}

/** Point the sidebar at whatever anchors this sentence already has. */
export function applyStoredAnchors(id) {
  const entry = anchorEntry(id);
  // Only anchors a person stands behind are pre-filled. A computed one is
  // left out so the run recomputes it rather than treating a guess as gold.
  const stored = entry && CURATED.includes(entry.source) ? entry.anchors : null;
  if (stored && Object.keys(stored).length) {
    byId('anchor-input').value = JSON.stringify(stored, null, 2);
    byId('anc_man').checked = true;
    byId('anc_leamr').checked = false;
    byId('anc_sub').classList.add('show');
  } else {
    byId('anc_lev').checked = true;
    byId('anc_sub').classList.remove('show');
  }
  toggleAnc();
}

// ── converting the whole corpus ──────────────────────────────────────────────

export async function runCorpus() {
  if (!corpus.sentences.length) { alert('Load a corpus first.'); return; }
  if (corpus.running) return;

  const stored = storedAnchors();
  corpus.running = true;
  corpus.results = {};

  const runButton = byId('corpus-run-btn-grs');
  const downloadButton = byId('corpus-dl-btn');
  const bar = byId('corpus-progress-bar');
  const label = byId('corpus-progress-label');
  if (runButton) runButton.disabled = true;
  downloadButton.style.display = 'none';
  byId('corpus-progress').style.display = 'block';

  let converted = 0, failed = 0;
  const total = corpus.sentences.length;

  for (let index = 0; index < total; index++) {
    const sentence = corpus.sentences[index];
    label.textContent = `${index + 1} / ${total}  —  ${sentence.id}`;
    bar.style.width = ((index / total) * 100) + '%';

    // Reuse only what a person edited or imported; a previously computed
    // anchor is computed again, so changing the anchorer actually takes
    // effect on a second run.
    const entry = stored[sentence.id];
    const curated = entry && CURATED.includes(entry.source) ? entry.anchors : null;
    const conllu = corpus.conllu[sentence.id] || '';
    try {
      const data = await postJson('/run', {
        amr: sentence.amr,
        ud_src: conllu ? 'manual' : 'stanza',
        conllu,
        anc_src: curated ? 'manual' : 'levenshtein',
        anchor_json: curated ? JSON.stringify(curated) : '',
        batch: true,
      });
      if (data.error) {
        corpus.results[sentence.id] = {error: data.error};
        failed++;
      } else {
        corpus.results[sentence.id] = {
          yarn_grs: data.yarn_grs || null,
          yarn_grs_error: data.yarn_grs_error || null,
          anchor_dict: data.anchor_dict || {},
        };
        // Recorded so they can be inspected and edited, but marked computed
        // so nothing later mistakes them for curated anchors.
        if (!curated && data.anchor_dict) {
          saveAnchors(sentence.id, data.anchor_dict, 'computed');
        }
        converted++;
      }
    } catch (error) {
      corpus.results[sentence.id] = {error: String(error)};
      failed++;
    }
  }

  bar.style.width = '100%';
  bar.style.background = failed > 0 ? '#f59e0b' : '#22c55e';
  label.textContent = `Done: ${converted} ok, ${failed} failed (of ${total})`;
  if (runButton) runButton.disabled = false;
  downloadButton.style.display = 'block';
  const sampleButton = byId('corpus-zip-btn');
  if (sampleButton) sampleButton.style.display = 'block';
  const browseButton = byId('corpus-browse-btn');
  if (browseButton) browseButton.style.display = 'block';
  corpus.running = false;
}

/** Download the run as a sample the YARN editor can import. */
export async function exportSample() {
  const graphs = {};
  for (const [id, result] of Object.entries(corpus.results)) {
    if (result && result.yarn_grs) graphs[id] = result.yarn_grs;
  }
  await downloadSampleZip(graphs, 'weave-corpus');
}

export function downloadResults() {
  if (!Object.keys(corpus.results).length) return;
  const blob = new Blob([JSON.stringify(corpus.results, null, 2)],
    {type: 'application/json'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'corpus_yarn_results.json';
  link.click();
  URL.revokeObjectURL(link.href);
}

/** Bring back the corpus and selection from the last visit. */
export function restoreSession() {
  const stored = restoreCorpus();
  if (!stored) return;
  const sentences = stored.sentences;
  renderCorpusList(sentences);
  // The UD parse is not stored, so say so rather than silently parsing.
  setMeta(`${stored.name}: ${sentences.length} sentences (restored)`
    + ' — load its CoNLL-U again, or Stanza will parse');

  const lastId = restoreCurrent();
  if (!lastId) return;
  const sentence = sentences.find(s => s.id === lastId);
  if (!sentence) return;
  saveCurrent(lastId);
  byId('amr-input').value = sentence.amr;
  byId('corpus-cur').textContent = lastId;
  applyStoredAnchors(lastId);
  updateSntBar(sentence.amr);
}

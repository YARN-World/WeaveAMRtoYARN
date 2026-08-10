// The corpus browser: step through converted sentences and inspect each one.
//
// Owns its own state and never touches the single-run tabs. Views are fetched
// and cached per sentence, because rendering a YARN graph costs a LaTeX run.

import { byId, escH, postJson } from './util.js';
import { applyTokenClick, applyVarClick, renderAnchorIn } from './anchors.js';
import { anchorsFor, corpus, mergeAnchors, saveAnchors } from './state.js';

const INFO_TABS = ['amr', 'ud', 'anchor'];
const LOADING = '<div class="cb-loading">…</div>';

export const CorpusBrowser = (() => {
  let curId = null;
  let curTab = 'yarn-grs';

  // Cleared whenever a new corpus run starts.
  let yarnCache = {};   // {id: html}
  let infoCache = {};   // {id: {amr_svg, ud_svg, anchor_data}}

  let anchorData = null;
  let anchorEdits = {};
  let selectedVar = null;

  function open() {
    yarnCache = {};
    infoCache = {};
    curId = null;
    anchorData = null;
    anchorEdits = {};
    selectedVar = null;

    byId('cbtbtn-yarn-grs').disabled = false;
    switchTab('yarn-grs');
    byId('tab-bar').style.display = 'none';
    byId('tab-content').style.display = 'none';
    byId('corpus-browser').classList.add('active');
    setStatusLine();

    const select = byId('corpus-select');
    if (select && select.value) load(select.value);
  }

  function close() {
    byId('corpus-browser').classList.remove('active');
    byId('tab-bar').style.display = '';
    byId('tab-content').style.display = '';
  }

  function setStatusLine(text) {
    byId('cb-status').textContent =
      text || `${Object.keys(corpus.results).length} sentences`;
  }

  function switchTab(tab) {
    curTab = tab;
    document.querySelectorAll('.cb-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.cb-panel').forEach(p => p.classList.remove('active'));
    byId('cbtbtn-' + tab)?.classList.add('active');
    byId('cbtab-' + tab)?.classList.add('active');
    if (curId) showTab(curId, tab);
  }

  function showTab(id, tab) {
    if (tab === 'yarn-grs') ensureYarn(id);
    else if (INFO_TABS.includes(tab)) ensureInfo(id, tab);
  }

  function load(id) {
    curId = id;
    anchorEdits = {};
    selectedVar = null;

    INFO_TABS.forEach(tab => { byId('cbtab-' + tab).innerHTML = LOADING; });

    const result = corpus.results[id];
    byId('cbtab-yarn-grs').innerHTML = result && result.error
      ? `<div class="cb-error">Pipeline error: ${escH(result.error)}</div>`
      : LOADING;

    showTab(id, curTab);
  }

  // ── the AMR, UD and anchor views ───────────────────────────────────────────

  async function ensureInfo(id, tab) {
    if (infoCache[id]) { renderInfo(id, tab, infoCache[id]); return; }

    const sentence = corpus.sentences.find(s => s.id === id);
    if (!sentence) return;
    const stored = anchorsFor(id);
    const conllu = corpus.conllu[id] || '';

    const fail = message => {
      const html = `<div class="cb-error">${escH(message)}</div>`;
      byId('cbtab-ud').innerHTML = html;
      byId('cbtab-anchor').innerHTML = html;
    };

    try {
      const data = await postJson('/sentence_info', {
        amr: sentence.amr,
        anchor_json: stored ? JSON.stringify(stored) : '',
        ud_src: conllu ? 'manual' : 'stanza',
        conllu,
      });
      if (data.error) { fail(data.error); return; }
      infoCache[id] = data;
      renderInfo(id, tab, data);
    } catch (error) {
      fail(String(error));
    }
  }

  function renderInfo(id, tab, info) {
    if (tab === 'amr') {
      byId('cbtab-amr').innerHTML =
        `<div class="cb-scroll">${info.amr_svg || ''}</div>`;
    } else if (tab === 'ud') {
      byId('cbtab-ud').innerHTML =
        `<div class="cb-scroll">${info.ud_svg || ''}</div>`;
    } else if (tab === 'anchor') {
      anchorData = info.anchor_data;
      renderAnchor();
    }
  }

  // ── the YARN view ─────────────────────────────────────────────────────────

  async function ensureYarn(id) {
    const panel = byId('cbtab-yarn-grs');
    if (yarnCache[id] !== undefined) { panel.innerHTML = yarnCache[id]; return; }

    const result = corpus.results[id];
    const graph = result && result.yarn_grs;
    const error = result && result.yarn_grs_error;
    if (!graph) {
      const html = `<div class="${error ? 'cb-error' : 'cb-loading'}">${escH(error || 'Not available.')}</div>`;
      panel.innerHTML = yarnCache[id] = html;
      return;
    }

    panel.innerHTML = '<div class="cb-loading">Rendering…</div>';
    try {
      // The id becomes the SVG's prefix: several graphs share this document,
      // and SVG ids are global to it.
      const data = await postJson('/yarn_svg', {
        yarn: graph,
        uid: 'cb_grs_' + id.replace(/[^a-z0-9]/gi, '_'),
      });
      const html = data.error
        ? `<div class="cb-error">${escH(data.error)}</div>`
        : `<div class="cb-yarn-wrap">${data.svg_html}</div>`;
      panel.innerHTML = yarnCache[id] = html;
    } catch (error) {
      panel.innerHTML = `<div class="cb-error">${escH(String(error))}</div>`;
    }
  }

  // ── the anchor editor ─────────────────────────────────────────────────────

  function renderAnchor() {
    renderAnchorIn('cbtab-anchor', anchorData, anchorEdits, selectedVar, 'cb',
      'Save anchors to storage', saveEditedAnchors);
  }

  function varClick(variable, event) {
    selectedVar = applyVarClick(event, variable, anchorEdits, selectedVar);
    renderAnchor();
  }

  function tokClick(tokenId) {
    applyTokenClick(tokenId, anchorData, anchorEdits, selectedVar);
    renderAnchor();
  }

  // Named apart from the imported saveAnchors it calls; sharing the name
  // would make this recurse into itself.
  function saveEditedAnchors() {
    if (!curId || !anchorData) return;
    saveAnchors(curId, mergeAnchors(anchorData, anchorEdits), 'manual');
    // The cached view still holds the old anchors.
    delete infoCache[curId];
    setStatusLine('Anchors saved for ' + curId);
    setTimeout(() => setStatusLine(), 2000);
  }

  return { open, close, switchTab, load, varClick, tokClick };
})();

// Converting the one sentence in the AMR box, and showing the result.

import { byId, escH, execScripts, markTab, postJson, setStatus, setTab } from './util.js';
import { switchTab, toggleAnc } from './tabs.js';
import { applyTokenClick, applyVarClick, renderAnchorIn } from './anchors.js';
import { openInEditor } from './editor.js';
import { corpus, mergeAnchors, saveAnchors } from './state.js';

// State for the Anchoring tab. The corpus browser keeps its own.
let anchorData = null;
let anchorEdits = {};
let selectedVar = null;

const NO_JSON = '<span style="color:#64748b">no JSON</span>';

function disableRunButtons(disabled) {
  document.querySelectorAll('.run-btn').forEach(b => (b.disabled = disabled));
}

export async function runPipeline() {
  const amr = byId('amr-input').value.trim();
  if (!amr) { alert('Paste an AMR first.'); return; }

  disableRunButtons(true);
  setStatus('Running…');
  try {
    const data = await postJson('/run', {
      amr,
      ud_src: document.querySelector('input[name=ud_src]:checked').value,
      conllu: byId('conllu-input').value.trim(),
      anc_src: document.querySelector('input[name=anc_src]:checked').value,
      anchor_json: byId('anchor-input').value.trim(),
    });
    if (data.error) showError(data.error);
    else { populateTabs(data); switchTab('steps'); }
  } catch (error) {
    showError(String(error));
  }
  disableRunButtons(false);
  setStatus('');
}

function showError(message) {
  setTab('tab-steps',
    `<pre style="color:#dc2626;padding:16px;white-space:pre-wrap">${escH(message)}</pre>`);
  switchTab('steps');
}

export function populateTabs(data) {
  setTab('tab-amr', data.amr_svg || '<p style="color:#aaa">No AMR SVG</p>');
  markTab('tbtn-amr');

  setTab('tab-ud', data.ud_svg || '<p style="color:#aaa">No UD SVG</p>');
  markTab('tbtn-ud');

  if (data.anchor_data) {
    anchorData = data.anchor_data;
    anchorEdits = {};
    selectedVar = null;
    renderAnchorTab();
    markTab('tbtn-anchor');
  }

  setTab('tab-steps', data.steps_grs || '');
  markTab('tbtn-steps');
  // The step navigator arrives with its own <script>, which innerHTML skips.
  execScripts(byId('tab-steps'));

  setTab('tab-yarn', yarnTabHtml(data));
  markTab('tbtn-yarn');
}

/** The graph of the last run, for the editor link. */
let lastYarn = null;

export function openLastInEditor() {
  openInEditor(lastYarn);
}

function yarnTabHtml(data) {
  lastYarn = data.yarn_grs_json || null;
  const json = data.yarn_grs_json
    ? JSON.stringify(data.yarn_grs_json, null, 2) : '';
  const editorButton = lastYarn
    ? `<button class="sub-tab-btn editor-btn" onclick="openLastInEditor()"
         title="Open this graph in the YARN editor">Open in editor ↗</button>`
    : '';
  return `
<div class="sub-tabs">
  <button class="sub-tab-btn active" id="yarn-btn-graph" onclick="switchYarnView('graph')">Graph</button>
  <button class="sub-tab-btn" id="yarn-btn-json" onclick="switchYarnView('json')">JSON</button>
  ${editorButton}
</div>
<div class="sub-tab-content">
  <div class="sub-tab-panel active" id="yarn-view-graph">
    <div class="yarn-cols">
      <div class="yarn-col"><div class="yarn-wrap">${data.yarn_grs || ''}</div></div>
    </div>
  </div>
  <div class="sub-tab-panel" id="yarn-view-json">
    <div class="yarn-cols">
      <div class="yarn-col">
        <h3><button class="copy-btn" onclick="copyYarnJson('yarn-json-grs', this)">Copy</button></h3>
        <pre class="yarn-json" id="yarn-json-grs">${escH(json) || NO_JSON}</pre>
      </div>
    </div>
  </div>
</div>`;
}

// ── the Anchoring tab ────────────────────────────────────────────────────────

function renderAnchorTab() {
  renderAnchorIn('tab-anchor', anchorData, anchorEdits, selectedVar, 'main',
    'Export anchors → manual', exportAnchors);
}

export function onVarClick(variable, event) {
  selectedVar = applyVarClick(event, variable, anchorEdits, selectedVar);
  renderAnchorTab();
}

export function onTokenClick(tokenId) {
  applyTokenClick(tokenId, anchorData, anchorEdits, selectedVar);
  renderAnchorTab();
}

/** Hand the edited anchors to the Manual box, and remember them. */
function exportAnchors() {
  const anchors = mergeAnchors(anchorData, anchorEdits);
  byId('anchor-input').value = JSON.stringify(anchors, null, 2);
  byId('anc_man').checked = true;
  toggleAnc();
  byId('anc_sub').classList.add('show');
  alert('Anchor dict exported to Manual textarea. Click Run to use it.');

  if (!corpus.curId) return;
  saveAnchors(corpus.curId, anchors, 'manual');
  const label = byId('corpus-cur');
  label.textContent = corpus.curId + ' ✓ anchors saved';
  setTimeout(() => { label.textContent = corpus.curId; }, 2000);
}

// ── LEAMR, straight into the Manual box ──────────────────────────────────────

export async function callLeamr() {
  const amr = byId('amr-input').value.trim();
  if (!amr) { alert('Paste AMR first.'); return; }
  setStatus('Calling LEAMR…');
  try {
    const data = await postJson('/leamr_align', {amr});
    if (data.error) {
      setStatus('LEAMR error');
      alert('LEAMR error: ' + data.error);
      return;
    }
    byId('anchor-input').value = JSON.stringify(data.mapping, null, 2);
    byId('anc_man').checked = true;
    byId('anc_leamr').checked = false;
    toggleAnc();
    byId('anc_sub').classList.add('show');
    setStatus('LEAMR done');
  } catch (error) {
    setStatus('LEAMR failed');
    alert('LEAMR call failed: ' + error);
  }
  setTimeout(() => setStatus(''), 2000);
}

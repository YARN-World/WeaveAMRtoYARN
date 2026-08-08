// The anchor editor: AMR variables on the left, sentence tokens on the right.
//
// Shared by the single-run tab and the corpus browser. They keep their own
// state and their own click handlers, so the namespace argument decides which
// handlers the generated markup calls.

import { byId, escH } from './util.js';
import { mergeAnchors } from './state.js';

export function renderAnchorIn(
  containerId, anchorData, edits, selectedVar, namespace, exportLabel, onExport
) {
  const container = byId(containerId);
  if (!container || !anchorData) return;

  const merged = mergeAnchors(anchorData, edits);

  // token -> the variables pointing at it, so a token can show its claimants
  const tokenVars = {};
  for (const variable of Object.keys(anchorData.vars)) {
    const tokenId = merged[variable];
    if (!tokenId) continue;
    (tokenVars[tokenId] = tokenVars[tokenId] || []).push(variable);
  }

  let variablesHtml = '<h3>AMR Variables</h3>';
  for (const [variable, info] of Object.entries(anchorData.vars)) {
    const tokenId = merged[variable];
    const token = tokenId ? anchorData.ud_tokens[tokenId] : null;
    const selected = variable === selectedVar ? ' selected' : '';
    const badge = tokenId
      ? `${escH((token && token.form) || tokenId)} (${escH(tokenId)})`
      : 'none';
    variablesHtml += `<div class="var-row${selected}" onclick="ancVarClick_${namespace}('${escH(variable)}', event)">
      <span class="var-name">${escH(variable)}</span>
      <span class="var-concept">${escH(info.concept || '')}</span>
      <span class="anc-badge${tokenId ? '' : ' empty'}">${badge}</span>
      ${tokenId ? `<span class="clear-x" data-var="${escH(variable)}">✕</span>` : ''}
    </div>`;
  }

  let tokensHtml = '';
  for (const [tokenId, token] of Object.entries(anchorData.ud_tokens)) {
    const assigned = tokenId in tokenVars;
    const isTarget = assigned && selectedVar
      && tokenVars[tokenId].includes(selectedVar);
    tokensHtml += `<div class="tok${assigned ? ' assigned' : ''}${isTarget ? ' target' : ''}"
      onclick="ancTokClick_${namespace}('${escH(tokenId)}')">
      <span class="tok-form">${escH(token.form)}</span>
      <span class="tok-id">${escH(tokenId)}</span>
      <span class="tok-upos">${escH(token.upos || '')}</span>
      ${assigned ? `<span class="tok-vars">${escH(tokenVars[tokenId].join(', '))}</span>` : ''}
    </div>`;
  }

  container.innerHTML = `
<div id="anchor-editor">
  <div id="anchor-var-panel-${namespace}">${variablesHtml}</div>
  <div id="anchor-right-${namespace}">
    <div style="font-size:1rem;font-style:italic;color:#334155;padding:6px 0 4px">${escH(anchorData.sentence || '')}</div>
    <div style="font-size:10px;color:#94a3b8">Select a variable, then click a token to assign.</div>
    <div id="token-grid-${namespace}">${tokensHtml}</div>
    <button id="export-anc-btn-${namespace}" class="export-anc-btn" style="margin-top:6px">${escH(exportLabel)}</button>
  </div>
</div>`;
  byId(`export-anc-btn-${namespace}`).addEventListener('click', onExport);
}

/**
 * Apply a click on a variable row.
 * The ✕ clears the anchor; anywhere else selects or deselects the variable.
 * Returns the new selection.
 */
export function applyVarClick(event, variable, edits, selectedVar) {
  if (event.target.classList.contains('clear-x')) {
    edits[variable] = null;
    return selectedVar === variable ? null : selectedVar;
  }
  return selectedVar === variable ? null : variable;
}

/** Assign the selected variable to a token, or clear it if already there. */
export function applyTokenClick(tokenId, anchorData, edits, selectedVar) {
  if (!selectedVar) return;
  const merged = mergeAnchors(anchorData, edits);
  edits[selectedVar] = merged[selectedVar] === tokenId ? null : tokenId;
}

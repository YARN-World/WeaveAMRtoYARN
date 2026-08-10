// A readout of what the browser is holding on to.
//
// The point is that nothing about stored state should have to be inferred:
// which corpus the anchors belong to, how many were edited rather than
// computed, and whether a UD parse is loaded at all.

import { byId, escH } from './util.js';
import {
  clearAnchors, clearEverything, corpus, exportAnchors, onStorageChange,
  storageSummary,
} from './state.js';

const KB = 1024;

function sizeLabel(bytes) {
  return bytes > KB * KB
    ? `${(bytes / (KB * KB)).toFixed(1)} MB`
    : `${Math.round(bytes / KB)} KB`;
}

function row(label, value, title = '') {
  return `<div class="store-row"${title ? ` title="${escH(title)}"` : ''}>
    <span class="store-label">${escH(label)}</span>
    <span class="store-value">${value}</span>
  </div>`;
}

export function renderStoragePanel() {
  const panel = byId('storage-panel');
  if (!panel) return;

  const s = storageSummary();
  const brief = byId('storage-brief');
  if (!s.corpusName) {
    if (brief) brief.textContent = '— nothing';
    panel.innerHTML = '<div class="store-empty">No corpus loaded.</div>';
    return;
  }
  // The header carries enough to leave the panel closed: how much is
  // anchored by hand, and whether a UD parse is loaded.
  if (brief) {
    brief.innerHTML = `<span class="store-weak">${s.curated}/${s.sentences}</span>`
      + (s.conlluLoaded ? '' : ' <span class="store-warn">no UD</span>')
      + (s.error ? ' <span class="store-warn">!</span>' : '');
  }

  const unanchored = s.sentences - s.anchored;
  const rows = [
    row('corpus', `${escH(s.corpusName)} <span class="store-weak">${s.sentences}</span>`),
    row('anchors',
      `${s.curated} edited` +
      (s.computed ? ` · <span class="store-weak">${s.computed} computed</span>` : '') +
      (unanchored > 0 ? ` · <span class="store-weak">${unanchored} none</span>` : ''),
      'Edited and imported anchors are kept and reused. Computed ones are '
      + 'recomputed on each run, so changing the anchorer takes effect.'),
    row('UD',
      s.conlluLoaded
        ? `${s.conlluLoaded} parses`
        : '<span class="store-warn">none — Stanza will parse</span>',
      'CoNLL-U is not stored between reloads: a corpus-sized file does not '
      + 'fit in browser storage. Load it again after a reload.'),
    row('size', sizeLabel(s.bytes)
      + (s.otherCorpora
        ? ` <span class="store-weak">· ${s.otherCorpora} other</span>` : ''),
      'Anchors for corpora loaded earlier are filed separately and cannot be '
      + 'used by this one.'),
  ];

  const error = s.error
    ? `<div class="store-error">${escH(s.error)}</div>` : '';

  panel.innerHTML = `
${rows.join('')}
${error}
<div class="store-actions">
  <button class="store-btn" onclick="downloadAnchors()"
          title="Download the anchors for this corpus as JSON">⬇ anchors</button>
  <button class="store-btn" onclick="forgetAnchors()"
          title="Remove stored anchors for this corpus only">clear anchors</button>
  <button class="store-btn danger" onclick="forgetEverything()"
          title="Remove the corpus, its anchors and the selection">clear all</button>
</div>`;
}

/** Download the anchors for the loaded corpus, in the format the CLI reads. */
export function downloadAnchors() {
  const anchors = exportAnchors();
  if (!Object.keys(anchors).length) { alert('No stored anchors to export.'); return; }
  const blob = new Blob([JSON.stringify(anchors, null, 2)],
    {type: 'application/json'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${(corpus.name || 'corpus').replace(/\W+/g, '_')}.anchors.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

export function forgetAnchors() {
  const s = storageSummary();
  const curated = s.curated
    ? `\n\n${s.curated} of them were edited or imported by hand.` : '';
  if (!confirm(`Remove stored anchors for ${s.corpusName}?${curated}`)) return;
  clearAnchors();
}

export function forgetEverything() {
  if (!confirm('Remove the stored corpus, all its anchors and the selection?')) return;
  clearEverything();
  location.reload();
}

onStorageChange(renderStoragePanel);

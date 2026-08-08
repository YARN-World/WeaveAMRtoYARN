// Handing graphs to the yarn-editor.
//
// Two ways across, both of which the editor already understands:
//
//   one graph   -> its #doc=<base64-json> hash loader, so a link is enough
//   many graphs -> a ZIP sample, built server-side, that it imports

import { byId, postJson } from './util.js';

/** Where the editor is served. Set from the template. */
export let editorUrl = 'https://yarn-editor.grew.fr';

export function setEditorUrl(url) {
  if (url) editorUrl = url.replace(/\/+$/, '');
}

/**
 * Base64 for the editor's hash loader.
 *
 * It decodes with atob() and hands the result straight to JSON.parse. atob
 * returns one character per byte, so any character above U+007F would come
 * back as mojibake — btoa refuses them outright. Escaping them to \uXXXX
 * first keeps the payload ASCII, and JSON.parse restores the characters.
 */
export function encodeDoc(graph) {
  const json = JSON.stringify(graph).replace(
    /[\u007f-\uffff]/g,
    ch => '\\u' + ch.charCodeAt(0).toString(16).padStart(4, '0')
  );
  return encodeURIComponent(btoa(json));
}

/**
 * Add the metadata the editor's validator insists on.
 *
 * It requires meta.sent_id and meta.text, both strings, and rejects the
 * document outright without them — this project writes those as id and snt.
 * Mirrors withEditorMetadata() in formats/editor.py, which does the same for
 * the zip; the two exist because a link is built here and an archive there.
 */
export function toEditorGraph(graph, sentenceId) {
  const meta = {...(graph.meta || {})};
  meta.sent_id = String(meta.sent_id || meta.id || sentenceId || 'sentence');
  meta.text = String(meta.text || meta.snt || '');
  return {...graph, meta};
}

export function editorLinkFor(graph, sentenceId) {
  return `${editorUrl}/#doc=${encodeDoc(toEditorGraph(graph, sentenceId))}`;
}

/** Open one graph in the editor, in a new tab. */
export function openInEditor(graph, sentenceId) {
  if (!graph) { alert('Nothing to open — run the pipeline first.'); return; }
  window.open(editorLinkFor(graph, sentenceId), '_blank', 'noopener');
}

/**
 * Download many graphs as a sample ZIP.
 *
 * Built on the server because the ZIP and its metadata.txt are the editor's
 * import format, and that format belongs with the other format code.
 */
export async function downloadSampleZip(graphs, name) {
  const present = Object.fromEntries(
    Object.entries(graphs).filter(([, yarn]) => yarn)
  );
  if (!Object.keys(present).length) { alert('No YARN graphs to export.'); return; }

  const response = await fetch('/export_zip', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({graphs: present, name}),
  });

  // A failure comes back as JSON; success is the archive itself.
  if ((response.headers.get('Content-Type') || '').includes('application/json')) {
    const data = await response.json();
    alert('Export failed: ' + (data.error || 'unknown error'));
    return;
  }

  const blob = await response.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${name}.zip`;
  link.click();
  URL.revokeObjectURL(link.href);
}

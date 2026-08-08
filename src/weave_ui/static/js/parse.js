// The parse panel: raw sentences in, AMR out.
//
// Independent of a conversion run — its output is pasted into the AMR box.

import { byId, escH, postJson } from './util.js';

export const ParsePanel = (() => {
  const panel = () => byId('spring-panel');
  const trigger = () => document.querySelector('.spring-open-btn');
  const input = () => byId('spring-input');
  const output = () => byId('spring-result');
  const button = () => byId('spring-parse-btn');
  const status = () => byId('spring-status');

  function open() {
    panel().classList.add('show');
    trigger()?.classList.add('active');
    setTimeout(() => input().focus(), 0);
  }

  function close() {
    panel().classList.remove('show');
    trigger()?.classList.remove('active');
  }

  function toggle() {
    if (panel().classList.contains('show')) close(); else open();
  }

  function block(result, index) {
    const preId = `spring-out-${index}`;
    const label = escH(result.sent || `Sentence ${index + 1}`);
    if (result.error) {
      return `<div class="spring-out-block">
        <div class="spring-out-hd"><span class="label">${label}</span></div>
        <div class="spring-err">Parser error: ${escH(result.error)}</div>
      </div>`;
    }
    return `<div class="spring-out-block">
      <div class="spring-out-hd">
        <span class="label">${label}</span>
        <button class="copy-btn" onclick="copyYarnJson('${preId}', this)">Copy</button>
        <button class="copy-btn" onclick="ParsePanel.useAmr('${preId}')" title="Paste into AMR input">Use</button>
      </div>
      <pre class="spring-pre" id="${preId}">${escH(result.amr || '')}</pre>
    </div>`;
  }

  async function parse() {
    const raw = input().value.trim();
    if (!raw) { alert('Enter at least one sentence.'); return; }
    const sentences = raw.split('\n').map(s => s.trim()).filter(Boolean);

    button().disabled = true;
    status().textContent =
      `Parsing ${sentences.length} sentence${sentences.length > 1 ? 's' : ''}…`;
    output().innerHTML = '';
    try {
      const data = await postJson('/spring_parse', {sentences});
      // A failure with no results at all is about the parser, not a sentence.
      if (data.error && !data.results) {
        status().textContent = 'Error';
        output().innerHTML = `<div class="spring-err">${escH(data.error)}</div>`;
        return;
      }
      const results = data.results || [];
      output().innerHTML = results.map(block).join('')
        || '<div class="placeholder">No AMR returned.</div>';
      const via = data.parser ? ` · ${escH(data.parser)}` : '';
      status().textContent = `Done · ${results.length} parsed${via}`;
    } catch (error) {
      status().textContent = 'Failed';
      output().innerHTML = `<div class="spring-err">${escH(String(error))}</div>`;
    } finally {
      button().disabled = false;
    }
  }

  /** Move one parsed graph into the AMR box. */
  function useAmr(preId) {
    const source = byId(preId);
    const target = byId('amr-input');
    if (!source || !target) return;
    target.value = source.textContent;
    target.dispatchEvent(new Event('input', {bubbles: true}));
    close();
  }

  return { open, close, toggle, parse, useAmr };
})();

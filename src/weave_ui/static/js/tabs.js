// Tabs, the sub-tabs inside the YARN panel, and the sidebar disclosures.

import { byId } from './util.js';

export let currentTab = 'amr';

export function switchTab(id) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  byId('tab-' + id)?.classList.add('active');
  byId('tbtn-' + id)?.classList.add('active');
  currentTab = id;
}

/** Graph or JSON, inside the YARN tab. */
export function switchYarnView(view) {
  document.querySelectorAll('#tab-yarn .sub-tab-panel')
    .forEach(p => p.classList.remove('active'));
  document.querySelectorAll('#tab-yarn .sub-tab-btn')
    .forEach(b => b.classList.remove('active'));
  byId('yarn-view-' + view)?.classList.add('active');
  byId('yarn-btn-' + view)?.classList.add('active');
}

export function toggleSub(subId, radioId) {
  byId(subId)?.classList.toggle('show', byId(radioId).checked);
}

/** The anchor source picker reveals whichever panel its choice needs. */
export function toggleAnc() {
  byId('anc_sub')?.classList.toggle('show', byId('anc_man').checked);
  byId('leamr_sub')?.classList.toggle('show', byId('anc_leamr').checked);
}

/** The bar under the toolbar showing which sentence is loaded. */
export function updateSntBar(amrText) {
  const sentence = amrText.match(/^#\s*::snt\s+(.+)/m);
  const identifier = amrText.match(/^#\s*::id\s+(\S+)/m);
  const text = sentence ? sentence[1].trim() : '';
  byId('snt-bar-id').textContent = identifier ? identifier[1] + '  ' : '';
  byId('snt-bar-text').textContent = text;
  byId('snt-bar').style.display = text ? '' : 'none';
}

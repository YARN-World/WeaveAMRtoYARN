// Entry point, and the one place the page and the code meet.
//
// The markup drives everything through inline handlers — onclick="runPipeline()"
// and the like — and those run in global scope, which module code is not. So
// everything the markup can name is listed here, deliberately: this is the
// contract between index.html and the modules, and nothing outside this file
// should add to it.

import { copyText } from './util.js';
import { switchTab, switchYarnView, toggleAnc, toggleSub, updateSntBar } from './tabs.js';
import {
  callLeamr, onTokenClick, onVarClick, openLastInEditor, runPipeline,
} from './singleRun.js';
import {
  clearCorpusConllu, downloadResults, exportSample, filterCorpus, onAnchorFile,
  onConlluCorpusFile, onCorpusFile, restoreSession, runCorpus, selectSentence,
} from './corpus.js';
import { CorpusBrowser } from './browser.js';
import { ParsePanel } from './parse.js';
import {
  downloadAnchors, forgetAnchors, forgetEverything, renderStoragePanel,
} from './storagePanel.js';
import { migrateLegacyStore } from './state.js';
import { setEditorUrl } from './editor.js';

Object.assign(window, {
  // tabs and disclosures
  switchTab, switchYarnView, toggleSub, toggleAnc, updateSntBar,
  // the single run
  runPipeline, callLeamr,
  // the anchor editor, in both of its namespaces
  ancVarClick_main: onVarClick,
  ancTokClick_main: onTokenClick,
  ancVarClick_cb: (variable, event) => CorpusBrowser.varClick(variable, event),
  ancTokClick_cb: tokenId => CorpusBrowser.tokClick(tokenId),
  // the corpus
  onCorpusFile, onAnchorFile, onConlluCorpusFile, clearCorpusConllu,
  filterCorpus, selectSentence, runCorpus, downloadResults,
  CorpusBrowser,
  // handing graphs to the YARN editor
  openLastInEditor, exportSample,
  // the parse panel. SpringPanel is the name the markup still uses.
  ParsePanel, SpringPanel: ParsePanel,
  // named for the JSON it was written for, but it copies any <pre>
  copyYarnJson: copyText,
  // what the browser is holding on to
  downloadAnchors, forgetAnchors, forgetEverything,
});

setEditorUrl(document.body.dataset.editorUrl);
// Anchors written before they were filed per corpus carry no corpus and no
// provenance; move them across before anything reads them.
migrateLegacyStore();
restoreSession();
renderStoragePanel();

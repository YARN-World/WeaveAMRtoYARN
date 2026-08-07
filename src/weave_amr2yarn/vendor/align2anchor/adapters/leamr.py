"""Run the LEAMR aligner and adapt its output to the anchor dictionary.

The stage structure mirrors what actually happens, in order:

  LeamrResources     locates the LEAMR repository and loads what is
                     expensive exactly once: the three alignment models,
                     the multiword-expression lexicon, and a stanza
                     pipeline running pretokenized.
  SentenceAnnotator  attaches the features LEAMR's models expect to one
                     AMR sentence: lemmas, POS tags, and token spans
                     (name spans > named entities > multiword expressions).
  LeamrRunner        drives the corpus: feeds each sentence the UD token
                     forms, runs the three models, and adapts the
                     subgraph alignments into the anchor dictionary.
  LeamrAdapter       the package-facing entry: produce(amrPath, udPath).

Two deliberate simplifications over the historical batch script, both
consequences of one decision — LEAMR is always fed the UD tokenisation:
token indices convert to UD identifiers by a bare index shift (no
character-offset remapping), and sentences without a UD parse are
skipped and reported rather than aligned on degraded whitespace tokens.
Span resolution is selectable (`spanResolution`): "first" (default)
collapses a span to its leftmost token; "head" to the span's syntactic
head (the token whose UD HEAD points outside the span); "head-common"
uses the head except for spans containing a PROPN, which keep the first
token.

Re-tested end-to-end 2026-08-01 (LEAMR rerun on pud_siyana + fracas,
both arms from one run): "first" remains the right default. Head
resolution fixes common-noun compounds ("Achaemenid ARMY", "Olympic
GAMES", "eight WEEKS") but breaks name spans, where the gold convention
anchors to the first token ("DAVIS Cup", "PAPUA New Guinea", "CNN
Style") — 4 fixes against 6 breakages on pud. Anchor F1 pud .910
first / .906 head / .912 head-common; fracas .919 / .927 / .919.
Downstream the choice barely registers and does not favour head: the
license filter drops 11 of the 25 affected pud anchors and most
survivors are inert (2 of 100 sentences change, net ~0), while on fracas
head scores BETTER on anchors yet WORSE in YARN (.6973 → .6948) —
anchor accuracy against the gold dict is not the objective.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import penman as penmanLib

from ..format import AnchorDictionary
from .base import Adapter, AdapterError

def projectRoot() -> Path:
    return Path(__file__).resolve().parents[3]


class LeamrResources:
    """The LEAMR repository and everything loaded from it, loaded once."""

    stripLead = {"DT", "PDT", "PRP$", "RB", "RP", "JJ", "JJR", "JJS", "IN"}
    stripTail = {"POS", "RB", "RBR", "RBS"}

    def __init__(self, leamrDir: str | Path | None = None):
        self.leamrDir = Path(leamrDir) if leamrDir else (
            projectRoot().parent / "anchoring" / "leamr")
        if not self.leamrDir.exists():
            raise AdapterError(f"LEAMR repository not found at {self.leamrDir}")
        self.wireImports()
        self.subgraphModel = None
        self.relationModel = None
        self.reentrancyModel = None
        self.stanzaPipeline = None
        self.mweIndex = self.buildMweIndex()

    def wireImports(self) -> None:
        alignmentDir = projectRoot() / "alignment"
        sys.path[:] = [p for p in sys.path
                       if p and Path(p).resolve() != alignmentDir]
        # LEAMR's amr_utils is vendored inside its own repository
        for entry in (self.leamrDir / "amr_utils" / "amr_utils",
                      self.leamrDir / "amr_utils",
                      self.leamrDir):
            if str(entry) not in sys.path:
                sys.path.insert(0, str(entry))

    def loadModels(self) -> None:
        if self.subgraphModel is not None:
            return
        # LEAMR is on sys.path now, so upstream crash-shims can be applied. They
        # are no-ops on a checkout that already carries the fixes.
        from ..leamr_compat import installRuntimeShims
        installRuntimeShims()
        from models.subgraph_model import Subgraph_Model
        from models.relation_model import Relation_Model
        from models.reentrancy_model import Reentrancy_Model
        prefix = str(self.leamrDir / "ldc+little_prince")
        self.subgraphModel = Subgraph_Model.load_model(
            f"{prefix}.subgraph_params.pkl")
        self.relationModel = Relation_Model.load_model(
            f"{prefix}.relation_params.pkl")
        self.reentrancyModel = Reentrancy_Model.load_model(
            f"{prefix}.reentrancy_params.pkl")

    def loadStanza(self):
        if self.stanzaPipeline is None:
            import stanza
            self.stanzaPipeline = stanza.Pipeline(
                "en", processors="tokenize,pos,lemma,ner",
                tokenize_pretokenized=True)
        return self.stanzaPipeline

    def buildMweIndex(self) -> dict[str, list[tuple[str, ...]]]:
        """{first word: [expression tuple, ...]}, longest expressions first."""
        from rule_based import mwes
        hyphenated = [" - ".join(m.split()) for m in mwes.OTHER_MWES]
        expressions = sorted(
            {tuple(m.split())
             for m in set(mwes.PMWES + mwes.VMWES + mwes.OTHER_MWES
                          + mwes.HAND_ADDED_MWES) | set(hyphenated)},
            key=len, reverse=True)
        index: dict[str, list[tuple[str, ...]]] = {}
        for expression in expressions:
            index.setdefault(expression[0], []).append(expression)
        return index


# ---------------------------------------------------------------------------
# Per-sentence annotation (what the models expect to find on the AMR object)
# ---------------------------------------------------------------------------

class SentenceAnnotator:
    """Attaches lemmas, POS tags and spans to one AMR sentence."""

    def __init__(self, resources: LeamrResources):
        self.resources = resources

    def annotate(self, amr) -> None:
        tokens = list(amr.tokens)
        document = self.resources.loadStanza()(" ".join(tokens))
        startOf, endOf = self.tokenOffsets(tokens)
        tokenIndex, lemmaAt, posAt, entitySpans = self.mapStanza(
            document, startOf, endOf, tokens)
        lemmas, posTags = self.spreadOverTokens(
            tokenIndex, lemmaAt, posAt, tokens)

        amr.lemmas = lemmas
        amr.pos = posTags
        amr.spans = self.combineSpans(
            len(tokens),
            self.nameSpans(amr, tokens),
            self.nerSpans(entitySpans, tokenIndex),
            self.mweSpans(tokens, lemmas))
        amr.coref = []

    @staticmethod
    def tokenOffsets(tokens: list[str]
                     ) -> tuple[dict[int, int], dict[int, int]]:
        startOf, endOf, position = {}, {}, 0
        for index, token in enumerate(tokens):
            startOf[index] = position
            endOf[index] = position + len(token)
            position += len(token) + 1
        return startOf, endOf

    def mapStanza(self, document, startOf, endOf, tokens):
        """Relate stanza tokens back to LEAMR token indices, and collect
        lemma, POS, and named-entity spans keyed by character start."""
        tokenIndex: dict[int, int] = {}
        lemmaAt: dict[int, str] = {}
        posAt: dict[int, str] = {}
        entitySpans: list[list[int]] = []

        for sentence in document.sentences:
            for token in sentence.tokens:
                start, end = token.start_char, token.end_char
                candidates = [k for k in startOf
                              if start >= startOf[k] and end <= endOf[k]]
                if not candidates:
                    candidates = [k for k in startOf
                                  if startOf[k] <= start <= endOf[k]]
                if not candidates:
                    continue
                index = candidates[0]
                tokenIndex[start] = index
                for word in token.words:
                    lemmaAt[start] = lemmaAt.get(start, "") + (
                        word.lemma or tokens[index])
                    posAt[start] = word.xpos or "NN"

            for entity in sentence.entities:
                charStarts = [t.start_char for t in entity.tokens]
                posSequence = [posAt.get(c, "") for c in charStarts]
                while posSequence and posSequence[0] in self.resources.stripLead:
                    posSequence, charStarts = posSequence[1:], charStarts[1:]
                if charStarts and posSequence and (
                        posSequence[-1] in self.resources.stripTail):
                    charStarts = charStarts[:-1]
                if len(charStarts) > 1:
                    entitySpans.append(charStarts)

        return tokenIndex, lemmaAt, posAt, entitySpans

    @staticmethod
    def spreadOverTokens(tokenIndex, lemmaAt, posAt, tokens):
        lemmas = [""] * len(tokens)
        posTags = [""] * len(tokens)
        for charStart, index in tokenIndex.items():
            if charStart in lemmaAt:
                lemmas[index] += lemmaAt[charStart]
                posTags[index] = posAt.get(charStart, "NN")
        for index, lemma in enumerate(lemmas):
            if not lemma:
                lemmas[index] = lemmas[index - 1] if index > 0 else tokens[index]
                posTags[index] = posTags[index - 1] if index > 0 else "NN"
        return lemmas, posTags

    @staticmethod
    def nameSpans(amr, tokens: list[str]) -> list[tuple[int, int]]:
        """Multi-token name spans read off the AMR :name/:op structure."""
        spans = []
        for node in amr.nodes:
            if amr.nodes[node] != "name":
                continue
            parts = sorted(
                [(int(role[3:]), target) for source, role, target in amr.edges
                 if source == node and role.startswith(":op")],
                key=lambda pair: pair[0])
            parts = [target for _, target in parts]
            if len(parts) <= 1:
                continue
            label = " ".join(amr.nodes[p].replace('"', "") for p in parts)
            for start in range(len(tokens)):
                span = list(range(start, start + len(parts)))
                if span[-1] >= len(tokens):
                    break
                surface = " ".join(tokens[t] for t in span if tokens[t] != '"')
                if surface.lower() == label.lower():
                    spans.append((span[0], span[-1] + 1))
                    break
        return spans

    @staticmethod
    def nerSpans(entitySpans: list[list[int]],
                 tokenIndex: dict[int, int]) -> list[tuple[int, int]]:
        spans = []
        for span in entitySpans:
            mapped = [tokenIndex[c] for c in span if c in tokenIndex]
            if len(mapped) > 1:
                spans.append((min(mapped), max(mapped) + 1))
        return spans

    def mweSpans(self, tokens: list[str], lemmas: list[str]
                 ) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        taken: list[int] = []
        for index, token in enumerate(tokens):
            if index in taken:
                continue
            found = False
            for source in (token.lower(), lemmas[index].lower()):
                for expression in self.resources.mweIndex.get(source, []):
                    size = len(expression)
                    if index + size > len(tokens):
                        continue
                    if all(tokens[index + k].lower().replace("@", "")
                           == expression[k] for k in range(size)):
                        spans.append((index, index + size))
                        taken.extend(range(index, index + size))
                        found = True
                        break
                if found:
                    break
            if not found:
                taken.append(index)
        return spans

    @staticmethod
    def combineSpans(tokenCount: int, nameSpans, nerSpans, mweSpans
                     ) -> list[list[int]]:
        """Merge multi-token spans by priority (name > NER > MWE)."""
        multiTokenSpans = nameSpans + nerSpans + mweSpans
        taken: set[int] = set()
        final: list[list[int]] = []
        for index in range(tokenCount):
            if index in taken:
                continue
            match = next((s for s in multiTokenSpans if s[0] == index), None)
            if match:
                tokens = list(range(match[0], match[1]))
                final.append(tokens)
                taken.update(tokens)
            else:
                final.append([index])
                taken.add(index)
        return final



class LeamrRunner:
    """Aligns a corpus and adapts the result to the anchor dictionary."""

    def __init__(self, resources: LeamrResources | None = None,
                 spanResolution: str = "first"):
        if spanResolution not in ("first", "head", "head-common"):
            raise AdapterError(f"unknown spanResolution '{spanResolution}'")
        self.resources = resources or LeamrResources()
        self.annotator = SentenceAnnotator(self.resources)
        self.spanResolution = spanResolution

    def run(self, amrPath: str | Path, udPath: str | Path
            ) -> tuple[AnchorDictionary, list[str]]:
        from amr_utils.amr_readers import AMR_Reader

        self.resources.loadModels()
        udForms = self.loadUdForms(Path(udPath))
        udHeads = self.loadUdHeads(Path(udPath))
        udPos = self.loadUdPos(Path(udPath))
        graphTexts = self.loadGraphTexts(Path(amrPath))
        sentences = AMR_Reader().load(str(amrPath), remove_wiki=True)

        anchors = AnchorDictionary()
        problems: list[str] = []
        for amr in sentences:
            if amr.id not in udForms:
                problems.append(f"{amr.id}: no UD parse — skipped")
                continue
            try:
                amr.tokens = udForms[amr.id]
                self.annotator.annotate(amr)
                alignments = self.align(amr)
                anchors.setSentence(amr.id, self.adaptAlignments(
                    amr, alignments, graphTexts.get(amr.id, ""),
                    udHeads.get(amr.id, {}), udPos.get(amr.id, {})))
            except Exception as error:
                problems.append(f"{amr.id}: {error}")
                anchors.setSentence(amr.id, {})
        return anchors, problems

    def align(self, amr) -> dict:
        """The three LEAMR passes; each later model reads the earlier layers."""
        resources = self.resources
        resources.relationModel.subgraph_alignments = {}
        resources.reentrancyModel.subgraph_alignments = {}
        resources.reentrancyModel.relation_alignments = {}

        subgraphAlignments = resources.subgraphModel.align_all([amr])
        resources.relationModel.subgraph_alignments = subgraphAlignments
        relationAlignments = resources.relationModel.align_all([amr])
        resources.reentrancyModel.subgraph_alignments = subgraphAlignments
        resources.reentrancyModel.relation_alignments = relationAlignments
        resources.reentrancyModel.align_all([amr])
        return subgraphAlignments

    def adaptAlignments(self, amr, subgraphAlignments, graphText: str,
                        heads: dict[int, int] | None = None,
                        pos: dict[int, str] | None = None
                        ) -> dict[str, str]:
        """Subgraph alignments → {variable: udTokenId}.

        Every variable of an aligned subgraph inherits one token of the
        span — its first token, or its syntactic head under
        spanResolution="head". The index shift is exact because the
        tokens ARE the UD forms. First alignment wins per variable."""
        pathToVariable = self.isiToVariables(graphText) if graphText else {
            node: node for node in amr.nodes}
        anchors: dict[str, str] = {}
        for alignment in subgraphAlignments.get(amr.id, []):
            if not alignment.nodes or not alignment.tokens:
                continue
            udId = str(self.resolveSpan(alignment.tokens, heads or {},
                                        pos or {}))
            for path in alignment.nodes:
                variable = pathToVariable.get(path)
                if variable is not None and variable not in anchors:
                    anchors[variable] = udId
        return anchors

    def resolveSpan(self, tokens, heads: dict[int, int],
                    pos: dict[int, str] | None = None) -> int:
        """Span (0-based aligner indices) → one 1-based UD token id.

        "head": the span's syntactic head is the token whose UD HEAD lies
        outside the span (root counts as outside). Ties — a coordination
        or a parse where several tokens attach out — take the leftmost,
        which is also the historical choice; a headless span (cycle, or
        tokens beyond the parse) falls back to the first token."""
        ids = sorted(t + 1 for t in tokens)
        if self.spanResolution == "first" or len(ids) == 1 or not heads:
            return ids[0]
        if self.spanResolution == "head-common" and pos and any(
                pos.get(i) == "PROPN" for i in ids):
            return ids[0]   # name span: the convention anchors to its first token
        inside = set(ids)
        outward = [i for i in ids if heads.get(i, 0) not in inside]
        return outward[0] if outward else ids[0]

    @staticmethod
    def loadUdPos(path: Path) -> dict[str, dict[int, str]]:
        """{sent_id: {token id: upos}} from a CoNLL-U file."""
        table: dict[str, dict[int, str]] = {}
        sentenceId, row = None, {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# sent_id"):
                sentenceId, row = line.split("=", 1)[1].strip(), {}
            elif not line.strip():
                if sentenceId and row:
                    table[sentenceId] = row
                sentenceId, row = None, {}
            elif sentenceId and not line.startswith("#"):
                fields = line.split("\t")
                if len(fields) >= 4 and fields[0].isdigit():
                    row[int(fields[0])] = fields[3]
        if sentenceId and row:
            table[sentenceId] = row
        return table

    @staticmethod
    def loadUdHeads(path: Path) -> dict[str, dict[int, int]]:
        """{sent_id: {token id: head id}} from a CoNLL-U file."""
        heads: dict[str, dict[int, int]] = {}
        sentenceId, table = None, {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# sent_id"):
                sentenceId, table = line.split("=", 1)[1].strip(), {}
            elif not line.strip():
                if sentenceId and table:
                    heads[sentenceId] = table
                sentenceId, table = None, {}
            elif sentenceId and not line.startswith("#"):
                fields = line.split("\t")
                if len(fields) >= 7 and fields[0].isdigit() and fields[6].isdigit():
                    table[int(fields[0])] = int(fields[6])
        if sentenceId and table:
            heads[sentenceId] = table
        return heads

    @staticmethod
    def isiToVariables(graphText: str) -> dict[str, str]:
        """Depth-first walk of the penman tree → {isi path: variable}."""
        mapping: dict[str, str] = {}
        visited: set[str] = set()

        def walk(node, path: str) -> None:
            variable, branches = node
            if variable in visited:
                return
            visited.add(variable)
            mapping[path] = variable
            childIndex = 0
            for role, branch in branches:
                if role == "/":
                    continue
                childIndex += 1
                if isinstance(branch, tuple) and branch[0] not in visited:
                    walk(branch, f"{path}.{childIndex}")

        try:
            walk(penmanLib.parse(graphText).node, "1")
        except Exception:
            pass
        return mapping

    @staticmethod
    def loadUdForms(path: Path) -> dict[str, list[str]]:
        forms: dict[str, list[str]] = {}
        sentenceId, tokens = None, []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# sent_id"):
                sentenceId, tokens = line.split("=", 1)[1].strip(), []
            elif not line.strip():
                if sentenceId and tokens:
                    forms[sentenceId] = tokens
                sentenceId, tokens = None, []
            elif sentenceId and not line.startswith("#"):
                fields = line.split("\t")
                if len(fields) >= 2 and fields[0].isdigit():
                    tokens.append(fields[1])
        if sentenceId and tokens:
            forms[sentenceId] = tokens
        return forms

    @staticmethod
    def loadGraphTexts(path: Path) -> dict[str, str]:
        texts: dict[str, str] = {}
        for block in path.read_text(encoding="utf-8").split("\n\n"):
            match = re.search(r"::(?:sent_)?id\s+(\S+)", block)
            if not match:
                continue
            graph = "\n".join(line for line in block.splitlines()
                              if not line.startswith("#")).strip()
            if graph:
                texts[match.group(1)] = graph
        return texts


class LeamrAdapter(Adapter):

    name = "leamr"

    def __init__(self, resources: LeamrResources | None = None,
                 spanResolution: str = "first"):
        self.runner = LeamrRunner(resources, spanResolution)

    def produce(self, amrPath: str | Path, udPath: str | Path
                ) -> AnchorDictionary:
        anchors, problems = self.runner.run(amrPath, udPath)
        for problem in problems:
            print(f"[leamr] {problem}")
        return self.validate(anchors)

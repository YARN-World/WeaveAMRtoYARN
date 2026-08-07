"""Sentence context: the evidence a convention decision may look at.

A judgement about one anchor needs the AMR side (variables, concepts,
graph shape) and the UD side (tokens and their tree). CorpusContext
loads both once per corpus; SentenceContext answers the structural
questions the licenses ask.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import penman

from .vocabulary import transferDeprels


@dataclass
class Token:
    tid: str
    form: str
    lemma: str
    upos: str
    head: str
    deprel: str


@dataclass
class SentenceContext:
    varConcepts: dict[str, str] = field(default_factory=dict)
    edges: list[tuple[str, str, str]] = field(default_factory=list)
    nameLiterals: dict[str, list[str]] = field(default_factory=dict)
    toks: dict[str, Token] = field(default_factory=dict)


    def children(self, variable: str, rolePrefix: str = ""
                 ) -> list[tuple[str, str]]:
        return [(role, target) for source, role, target in self.edges
                if source == variable and role.startswith(rolePrefix)]

    def argofPartners(self, variable: str) -> list[str]:
        """Predicates the variable is an ARG of, in either edge direction."""
        partners = []
        for source, role, target in self.edges:
            if source == variable and re.match(r":ARG\d+-of$", role):
                partners.append(target)
            if target == variable and re.match(r":ARG\d+$", role):
                partners.append(source)
        return partners

    # -- tree queries ----------------------------------------------------

    def spanHead(self, tids: list[str]) -> str:
        """First token of the span whose UD head lies outside it."""
        span = set(tids)
        candidates = [t for t in tids
                      if t in self.toks and self.toks[t].upos != "PUNCT"]
        if not candidates:
            return tids[0]
        for t in candidates:
            if self.toks[t].head not in span:
                return t
        return candidates[0]

    def transferFunctionWord(self, tid: str) -> str:
        """An anchor on a case/det/mark token transfers to its UD head."""
        token = self.toks.get(tid)
        if token and token.deprel in transferDeprels and token.head in self.toks:
            return token.head
        return tid

    def verbalAncestor(self, tid: str, maxHops: int = 4) -> str | None:
        """Nearest VERB/AUX ancestor of tid, including tid itself."""
        current, hops = tid, 0
        while current in self.toks and hops <= maxHops:
            if self.toks[current].upos in ("VERB", "AUX"):
                return current
            current, hops = self.toks[current].head, hops + 1
        return None


class CorpusContext:
    """AMR graphs and UD parses for a corpus, addressable by sentence id."""

    def __init__(self, amrPath: str | Path, udPath: str | Path):
        self.sentences = self.loadAmr(Path(amrPath))
        self.udTokens = self.loadUd(Path(udPath))

    def sentenceContext(self, sentenceId: str) -> SentenceContext | None:
        """None means there is no evidence to judge on — callers must then
        pass anchors through unchanged rather than guess."""
        sentence = self.sentences.get(sentenceId)
        if sentence is None or not self.udTokens.get(sentenceId, {}):
            return None
        sentence.toks = self.udTokens.get(sentenceId, {})
        return sentence

    @staticmethod
    def loadAmr(path: Path) -> dict[str, SentenceContext]:
        sentences: dict[str, SentenceContext] = {}
        for block in path.read_text(encoding="utf-8").split("\n\n"):
            idMatch = re.search(r"::(?:sent_)?id\s+(\S+)", block)
            if not idMatch:
                continue
            graphText = "\n".join(line for line in block.splitlines()
                                  if not line.startswith("#")).strip()
            try:
                graph = penman.decode(graphText)
            except Exception:
                continue
            sentence = SentenceContext()
            sentence.varConcepts = {t[0]: t[2] for t in graph.triples
                                    if t[1] == ":instance"}
            sentence.edges = [(t[0], t[1], t[2]) for t in graph.triples
                              if t[1] != ":instance"]
            nameVars = {t[2] for t in graph.triples if t[1] == ":name"}
            for source, role, target in sentence.edges:
                if role == ":name" and target in nameVars:
                    words = []
                    for s2, r2, t2 in sentence.edges:
                        if s2 == target and r2.startswith(":op") and isinstance(t2, str):
                            words.extend(t2.strip('"').lower().split())
                    if words:
                        sentence.nameLiterals[source] = words
            sentences[idMatch.group(1)] = sentence
        return sentences

    @staticmethod
    def loadUd(path: Path) -> dict[str, dict[str, Token]]:
        parses: dict[str, dict[str, Token]] = {}
        sentenceId, tokens = None, {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# sent_id"):
                sentenceId, tokens = line.split("=", 1)[1].strip(), {}
            elif not line.strip():
                if sentenceId and tokens:
                    parses[sentenceId] = tokens
                sentenceId, tokens = None, {}
            elif sentenceId and not line.startswith("#"):
                fields = line.split("\t")
                if len(fields) >= 8 and fields[0].isdigit():
                    tokens[fields[0]] = Token(fields[0], fields[1], fields[2],
                                              fields[3], fields[6], fields[7])
        if sentenceId and tokens:
            parses[sentenceId] = tokens
        return parses
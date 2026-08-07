"""The convention as an engine: every anchor earns a license or a denial.

ConventionJudge examines each anchored variable in its sentence context
and issues a Ruling. Rulings are then split into the two objects the
rest of the package consumes:

  Verdict   — may this variable be anchored at all? (keep / deny)
  Proposal  — the engine's suggested value (retarget evidence)

The filter consumes verdicts only; the repair stage consumes proposals.

License inventory, in priority order (evidence: postprocessing/NOTES.md):
  DENY  structural / discourse / fixed-expression / role-noun /
        temporal-scaffold / entity-quantity / bare -91 nodes; punctuation.
  EXPO  construction exponents: verbal cause, adverbial temporal, modal
        auxiliary, copula "be", degree word.
  L4    named-entity parent → name-literal token;  L4b demonym head.
  L1    lexical match (exact > suppletive > phrasal > derivational > fuzzy).
  L2    nominalization / role / domain co-anchoring.
  L3    clause head for exponent-less predicates (LVC, ellipsis, copula).
  L5    unit noun under a quantity entity.
  Deletions without positive evidence are restored (the aligner's
  assertion stands unless a rule positively invalidates it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .context import SentenceContext
from . import vocabulary as vocab
from .vocabulary import (fuzzyThreshold, isPredicate, similarity,
                         stemSimilarity, stripConcept)


@dataclass
class Ruling:
    variable: str
    concept: str
    old: str | None
    new: str | None
    license: str
    reason: str


@dataclass
class Verdict:
    variable: str
    concept: str
    keep: bool
    license: str
    reason: str


@dataclass
class Proposal:
    variable: str
    concept: str
    value: str
    license: str
    reason: str


class ConventionJudge:
    """Runs the license inventory over one sentence's anchors."""

    def __init__(self, spanResolution: str = "head"):
        self.spanResolution = spanResolution

    # -- public API ------------------------------------------------------

    def judgeSentence(self, anchors: dict, sentence: SentenceContext
                      ) -> tuple[list[Verdict], list[Proposal]]:
        result, rulings = self.applyLicenses(anchors, sentence)
        result, rulings = self.restoreUncertainDeletions(result, rulings, sentence)

        verdicts, proposals = [], []
        decided = set()
        for ruling in rulings:
            decided.add(ruling.variable)
            kept = ruling.variable in result
            verdicts.append(Verdict(ruling.variable, ruling.concept, kept,
                                    ruling.license, ruling.reason))
            if kept and ruling.new is not None:
                proposals.append(Proposal(ruling.variable, ruling.concept,
                                          str(ruling.new),
                                          ruling.license, ruling.reason))
        for variable in anchors:
            if variable not in decided:
                verdicts.append(Verdict(
                    variable, "", False, "LITERAL",
                    "wiki/name/number literal — bare under the convention"))
        return verdicts, proposals

    # -- the license pass ------------------------------------------------

    def applyLicenses(self, anchors: dict, ctx: SentenceContext
                      ) -> tuple[dict[str, str], list[Ruling]]:
        rulings: list[Ruling] = []
        result: dict[str, str] = {}

        # tokens lexically claimed by some variable (L3's "unclaimed" guard)
        lexicalClaims: dict[str, str] = {}
        for variable, concept in ctx.varConcepts.items():
            target, kind = self.lexicalTarget(concept, ctx)
            if target and kind == "exact":
                lexicalClaims.setdefault(target, variable)

        for variable, concept in ctx.varConcepts.items():
            if variable not in anchors:
                continue          # pure postprocessing: untouched vars stay bare
            raw = anchors.get(variable)

            # span input resolves to one token before licensing
            if isinstance(raw, list):
                incoming = ",".join(raw)
                old = (ctx.spanHead(raw) if self.spanResolution == "head"
                       else raw[0])
                if len(raw) > 1:
                    form = ctx.toks[old].form if old in ctx.toks else old
                    rulings.append(Ruling(variable, concept, incoming, old,
                                          "R-SPAN", f"span [{incoming}] → "
                                          f"{self.spanResolution} '{form}'"))
            else:
                incoming = raw
                old = raw
            old = ctx.transferFunctionWord(old) if old else None
            token = ctx.toks.get(old) if old else None

            # an anchor on punctuation is never valid
            if token is not None and token.upos == "PUNCT":
                rulings.append(Ruling(variable, concept, incoming, None,
                                      "DENY",
                                      f"anchor on punctuation '{token.form}'"))
                continue

            def decide(new, license, reason,
                       variable=variable, concept=concept, incoming=incoming):
                rulings.append(Ruling(variable, concept, incoming, new,
                                      license, reason))
                if new:
                    result[variable] = new

            # ---- denials -----------------------------------------------
            if concept in vocab.structural or concept in vocab.discourseFrames:
                decide(None, "DENY", f"structural/discourse concept '{concept}'")
                continue
            if concept in vocab.verbalDiscourseFrames:
                if token is not None and token.upos in ("VERB", "AUX"):
                    decide(old, "EXPO",
                           f"'{concept}' realized verbally as '{token.form}'")
                else:
                    decide(None, "DENY",
                           f"'{concept}' as connective (non-VERB/AUX)")
                continue
            if concept in vocab.fixedExpressions:
                decide(None, "DENY", f"fixed expression '{concept}'")
                continue
            roleArg2 = any(
                role == ":ARG2" and ctx.varConcepts.get(source) in vocab.roleFrames
                for source, role, target in ctx.edges if target == variable
            ) or any(
                role == ":ARG2-of" and ctx.varConcepts.get(target) in vocab.roleFrames
                for source, role, target in ctx.edges if source == variable
            )
            if roleArg2 and not isPredicate(concept):
                decide(None, "DENY",
                       f"role noun '{concept}' (person anchors its token)")
                continue
            if concept in vocab.temporalScaffolds:
                if token is not None and token.upos == "ADV":
                    decide(old, "EXPO",
                           f"temporal '{concept}' as adverb '{token.form}'")
                else:
                    decide(None, "DENY",
                           f"temporal scaffold '{concept}' (connective)")
                continue
            if re.search(r"-(entity|quantity)$", concept):
                decide(None, "DENY",
                       f"abstract entity/quantity frame '{concept}'")
                continue
            if (re.search(r"-9[12]$", concept)
                    and concept not in vocab.copulaFrames | vocab.degreeFrames):
                decide(None, "DENY",
                       f"reification '{concept}' with no surface exponent")
                continue

            # ---- construction exponents --------------------------------
            if concept in vocab.modalFrames and token is not None and (
                    token.upos == "AUX"
                    or token.lemma.lower() in vocab.modalAdverbs):
                decide(old, "EXPO", f"modal frame '{concept}' → '{token.form}'")
                continue
            if concept in vocab.copulaFrames:
                copula = self.clauseCopula(variable, ctx, anchors, lexicalClaims, old)
                if copula:
                    decide(copula, "EXPO",
                           f"copula -91 → '{ctx.toks[copula].form}'")
                else:
                    decide(None, "DENY",
                           "copula -91 with no copula of its own clause")
                continue
            if concept in vocab.degreeFrames:
                arg3 = {stripConcept(ctx.varConcepts.get(t, "")).lower()
                        for _, t in ctx.children(variable, ":ARG3")}
                degrees = [t for t in ctx.toks.values()
                           if t.lemma.lower() in vocab.degreeWords]
                degrees.sort(key=lambda t: (t.lemma.lower() not in arg3,
                                            int(t.tid)))
                if degrees:
                    decide(degrees[0].tid, "EXPO",
                           f"have-degree-91 → degree word '{degrees[0].form}'")
                else:
                    decide(None, "DENY", "have-degree-91, no degree word present")
                continue

            # ---- L4: named-entity parent -------------------------------
            literals = ctx.nameLiterals.get(variable)
            if literals:
                candidates = [t for t in ctx.toks.values()
                              if t.lemma.lower() in literals
                              or t.form.lower() in literals]
                if candidates:
                    span = {t.tid for t in candidates}
                    stem = stripConcept(concept)

                    def nameKey(t):
                        lexical = similarity(stem, t.lemma) >= fuzzyThreshold
                        isHead = t.head not in span
                        return (not lexical, not isHead,
                                t.upos != "PROPN", int(t.tid))
                    candidates.sort(key=nameKey)
                    decide(candidates[0].tid, "L4",
                           f"NE parent → name literal '{candidates[0].form}'")
                    continue
                # literal absent from the sentence — other licenses may apply

            # ---- L1: lexical -------------------------------------------
            # Evidence asymmetry: adding needs exact evidence; weaker
            # evidence may only keep or move an existing anchor.
            target, kind = self.lexicalTarget(concept, ctx, prefer=old)
            if target and (old is not None or kind == "exact"):
                decide(target, "L1",
                       f"lexical {kind} match '{ctx.toks[target].form}'")
                continue

            # ---- L4b: demonym head -------------------------------------
            geoChildren = [t for _, t in ctx.children(variable, ":mod")
                           if ctx.varConcepts.get(t) in vocab.geoConcepts]
            if geoChildren and not isPredicate(concept):
                for geo in geoChildren:
                    words = ctx.nameLiterals.get(geo, [])
                    scored = [(stemSimilarity(w, t.lemma), t)
                              for t in ctx.toks.values()
                              for w in words if t.upos != "PUNCT"]
                    scored = [(s, t) for s, t in scored if s >= fuzzyThreshold]
                    if scored:
                        scored.sort(key=lambda x: (x[1].upos == "ADJ",
                                                   -x[0], int(x[1].tid)))
                        decide(scored[0][1].tid, "L4b",
                               f"demonym head '{scored[0][1].form}' "
                               f"(geo {ctx.varConcepts[geo]})")
                        break
                else:
                    decide(None, "DROP",
                           "no license (demonym candidate below threshold)")
                if variable in result or rulings[-1].license == "DROP":
                    continue

            # ---- L2: aligner-asserted nominalization pair --------------
            if old and token is not None and token.upos == "NOUN":
                rawSelf = anchors.get(variable)
                if any(anchors.get(p) == rawSelf
                       for p in ctx.argofPartners(variable)):
                    decide(old, "L2", f"nominalization pair on '{token.form}' "
                           f"(ARG partner shares the aligner anchor)")
                    continue

            # ---- L2: co-anchoring --------------------------------------
            coAnchor, coReason = None, ""
            if not isPredicate(concept):
                partners = list(ctx.argofPartners(variable))
                for source, role, target2 in ctx.edges:
                    if role in (":domain", ":domain-of"):
                        if source == variable and target2 in ctx.varConcepts:
                            partners.append(target2)
                        elif target2 == variable and source in ctx.varConcepts:
                            partners.append(source)
                for partner in partners:
                    pTarget, _ = self.lexicalTarget(
                        ctx.varConcepts.get(partner, ""), ctx)
                    if pTarget and ctx.toks[pTarget].upos == "NOUN":
                        coAnchor = pTarget
                        coReason = "nominalization/domain co-anchor"
                        break
                if coAnchor is None:
                    for source, role, target2 in ctx.edges:
                        frame = None
                        if (target2 == variable and role == ":ARG0"
                                and ctx.varConcepts.get(source) in vocab.roleFrames):
                            frame = source
                        if (source == variable and role == ":ARG0-of"
                                and ctx.varConcepts.get(target2) in vocab.roleFrames):
                            frame = target2
                        if frame is None:
                            continue
                        for s2, r2, t2 in ctx.edges:
                            if s2 == frame and r2 == ":ARG2":
                                roleNoun, _ = self.lexicalTarget(
                                    ctx.varConcepts.get(t2, ""), ctx)
                                if roleNoun:
                                    coAnchor = roleNoun
                                    coReason = ("role construction: "
                                                "person on role noun")
                                break
                        if coAnchor:
                            break
            else:
                stem = stripConcept(concept)
                for partner in ctx.argofPartners(variable):
                    pTarget, _ = self.lexicalTarget(
                        ctx.varConcepts.get(partner, ""), ctx)
                    if pTarget and ctx.toks[pTarget].upos == "NOUN":
                        lemma = ctx.toks[pTarget].lemma.lower()
                        prefix = 0
                        for x, y in zip(stem, lemma):
                            if x != y:
                                break
                            prefix += 1
                        if prefix >= 4:
                            coAnchor = pTarget
                            coReason = "predicate on its nominalization"
                            break
            if coAnchor:
                decide(coAnchor, "L2",
                       f"{coReason} '{ctx.toks[coAnchor].form}'")
                continue

            # ---- L3: clause head ---------------------------------------
            if isPredicate(concept) and token is not None:
                ancestor = ctx.verbalAncestor(
                    token.head if token.upos not in ("VERB", "AUX")
                    else token.tid)
                if ancestor and ancestor != old:
                    ancestorToken = ctx.toks[ancestor]
                    unclaimed = lexicalClaims.get(ancestor) in (None, variable)
                    lightish = (ancestorToken.lemma in vocab.lightVerbs
                                or ancestorToken.upos == "AUX")
                    if unclaimed and lightish:
                        decide(ancestor, "L3",
                               f"clause head '{ancestorToken.form}' "
                               f"(LVC/ellipsis/copula; was '{token.form}')")
                        continue
                    if not unclaimed:
                        decide(None, "DROP",
                               f"no license; clause head "
                               f"'{ancestorToken.form}' already claimed")
                        continue

            # ---- L5: unit under a quantity entity ----------------------
            quantityParents = [s for s, r, t in ctx.edges
                               if t == variable
                               and ctx.varConcepts.get(s) in vocab.quantityEntities]
            if quantityParents and old:
                role = next((r for s, r, t in ctx.edges
                             if t == variable and s in quantityParents), "")
                if role == ":unit":
                    unitTarget, _ = self.lexicalTarget(concept, ctx)
                    if unitTarget:
                        decide(unitTarget, "L5",
                               f"unit noun '{ctx.toks[unitTarget].form}'")
                        continue

            # ---- no license --------------------------------------------
            if old:
                decide(None, "DROP", f"no license for '{concept}' on "
                       f"'{token.form if token else old}'")

        return result, rulings

    # -- the restore pass ------------------------------------------------

    def restoreUncertainDeletions(self, result: dict[str, str],
                                  rulings: list[Ruling],
                                  ctx: SentenceContext
                                  ) -> tuple[dict[str, str], list[Ruling]]:
        """A deletion without positive removal evidence is undone: the
        aligner's assertion stands unless a rule invalidates it."""
        out: list[Ruling] = []
        for ruling in rulings:
            if not self.deletionIsUncertain(ruling, ctx):
                out.append(ruling)
                continue
            tid = self.resolveIncoming(ruling.old, ctx)
            tid = ctx.transferFunctionWord(tid)
            token = ctx.toks.get(tid)
            if token is None or token.upos == "PUNCT":
                out.append(ruling)
                continue
            result[ruling.variable] = tid
            out.append(Ruling(
                ruling.variable, ruling.concept, ruling.old, tid, "KEEP",
                f"restore on '{token.form}' — deleted without evidence "
                f"({ruling.license}: {ruling.reason})"))
        return result, out

    def deletionIsUncertain(self, ruling: Ruling, ctx: SentenceContext) -> bool:
        if ruling.new is not None or ruling.old is None:
            return False
        if ruling.license == "DROP":
            return True
        if ruling.license == "DENY":
            if ruling.reason.startswith("fixed expression"):
                return True
            if ruling.reason.startswith("temporal scaffold"):
                token = ctx.toks.get(ruling.old)
                return token is not None and token.upos not in vocab.markerUpos
        return False

    @staticmethod
    def clauseCopula(variable: str, ctx: SentenceContext, anchors: dict,
                     lexicalClaims: dict[str, str],
                     frameToken: str | None = None) -> str | None:
        """The copula that is *this* frame's exponent, or None.

        A reified copular frame has no content word: its exponent is the copula
        of the clause it heads. Picking any `be` in the sentence is wrong as soon
        as the frame is embedded under another copular predicate — in "It is now
        only unclear, in which one" the single `be` supports *unclear*
        (clear-06), while the be-located-at-91 sits in a verbless embedded
        question and has no copula at all.

        A copula qualifies only if it supports the frame's own material: `cop`
        attaches to the predicate it serves, so that predicate must be a token
        this frame occupies — where the frame itself was aligned, or where one of
        its arguments landed. "Here is a copy" qualifies (`is` supports *Here*,
        the frame's :ARG2); "It is unclear, in which one" does not (`is` supports
        *unclear*, which belongs to clear-06, while the frame sits on *one*).
        """
        # the tokens this frame occupies: where the aligner put it (after any
        # function-word transfer) and where each of its arguments landed
        connectors, ownVars = set(), {variable}
        if frameToken:
            connectors.add(str(frameToken))
        # the frame's subtree, not just its immediate children: a location is
        # routinely a name node under an entity ("(c / continent :name (n / name
        # :op1 "Europe"))"), and the surface token belongs to the nested node
        frontier, depth = [variable], 0
        while frontier and depth < 3:
            nextFrontier = []
            for node in frontier:
                for _role, target in ctx.children(node):
                    if target in ownVars:
                        continue
                    ownVars.add(target)
                    nextFrontier.append(target)
                    value = anchors.get(target)
                    if isinstance(value, list):
                        value = value[0] if value else None
                    if value:
                        connectors.add(str(value))
            frontier, depth = nextFrontier, depth + 1

        fits = []
        for tok in ctx.toks.values():
            if tok.lemma != "be" or tok.upos not in ("AUX", "VERB"):
                continue
            supported = tok.head          # `cop` attaches to the predicate it serves
            if supported not in ctx.toks or supported not in connectors:
                continue                  # serves some other predicate, not ours
            claimant = lexicalClaims.get(supported)
            if claimant is not None and claimant not in ownVars:
                continue                  # that token is another variable's exponent
            fits.append(tok.tid)
        # rightmost wins: in a multi-clause sentence the main predicate is last
        return fits[-1] if fits else None

    def resolveIncoming(self, incoming: str, ctx: SentenceContext) -> str:
        if "," in incoming:
            tids = incoming.split(",")
            return (ctx.spanHead(tids) if self.spanResolution == "head"
                    else tids[0])
        return incoming

    # -- lexical matching ------------------------------------------------

    def lexicalTarget(self, concept: str, ctx: SentenceContext,
                      prefer: str | None = None) -> tuple[str | None, str]:
        """Best lexical token for a concept: exact > suppletive >
        phrasal-head > derivational > stem-derivational > fuzzy.
        Derivation is directional: the token must extend the concept stem,
        never the reverse. `prefer` breaks score ties for the incoming anchor."""
        stem = stripConcept(concept)
        if not stem:
            return None, ""
        headComponent = stem.split("-")[0] if "-" in stem else None
        best, bestScore, bestKind = None, 0.0, ""
        for token in ctx.toks.values():
            if token.upos == "PUNCT":
                continue
            lemma = token.lemma.lower()
            if lemma == stem:
                score, kind = 1.0, "exact"
            elif lemma in vocab.suppletive.get(stem, ()):
                score, kind = 0.98, "suppletive"
            elif headComponent and lemma == headComponent and (
                    len(headComponent) >= 3 or token.upos == "ADV"
                    ) and token.upos not in ("ADP", "SCONJ", "DET", "PRON"):
                score, kind = 0.95, "phrasal-head"
            elif lemma.startswith(stem) and len(stem) >= 3:
                score, kind = 0.9, "deriv"
            elif (len(stem) >= 4 and len(lemma) > len(stem)
                  and stemSimilarity(stem, lemma) >= fuzzyThreshold):
                score, kind = 0.85, "stem-deriv"
            else:
                score, kind = similarity(stem, lemma), "fuzzy"
            if score < fuzzyThreshold:
                continue
            if score > bestScore or (score == bestScore and token.tid == prefer):
                best, bestScore, bestKind = token.tid, score, kind
        return best, bestKind

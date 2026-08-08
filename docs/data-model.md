# Data model

The representations a sentence passes through, and the vocabulary each uses. For the
order they occur in and the code that produces them, see [pipeline.md](pipeline.md).

Every example below is the same sentence, *She chaired it.*, carried the whole way.

## 1. Penman text — the input

An AMR corpus is a text file of Penman blocks separated by blank lines, each preceded
by `# ::key value` metadata lines.

```
# ::id fracas-120.premise_1 ::date 2017-03-08T23:09:30
# ::snt She chaired it.
(c / chair-01
   :ARG0 (s / she)
   :ARG1 (i2 / it))
```

`AmrCorpus` reads such a file into `AmrSentence` objects
([`formats/amr.py`](../src/weave_amr2yarn/formats/amr.py)):

| | |
|---|---|
| `AmrSentence.id` | from `::id`, the identifier used for output file names |
| `AmrSentence.penman` | the block itself, metadata included |
| `AmrSentence.metadata()` | the `::key value` pairs as a dict |

Which metadata key holds the sentence is configurable — `snt` by default, but some
corpora use `text`. See `sentenceKey` in [pipeline.md](pipeline.md#configuration).

`AmrCorpus` also reports `ids()` and `duplicateIds()`, because duplicate identifiers
silently overwrite each other's output.

## 2. GREW JSON — the working representation

Everything between parsing and writing is a plain dict of this shape, which is what
grewpy exchanges:

```json
{
  "meta":  { "id": "…", "snt": "…" },
  "nodes": { "<id>": { "<feature>": "<value>", … }, … },
  "edges": [ { "src": "<id>", "label": "<label>", "tar": "<id>" }, … ]
}
```

Nodes are keyed by identifier; features are flat strings. Edge labels are strings on
input, but the engine may return a dict for a labelled edge — code that reads labels
back has to allow for both.

The AMR alone becomes:

```json
{ "nodes": { "c":  { "pred": "chair-01", "type": "V", "var": "c", "focus": "yes" },
             "s":  { "concept": "she", "type": "V", "var": "s" },
             "i2": { "concept": "it",  "type": "V", "var": "i2" } },
  "edges": [ { "src": "c", "label": "ARG0", "tar": "s" },
             { "src": "c", "label": "ARG1", "tar": "i2" } ] }
```

Two things are already decided here. A node is a **predicate** (`pred`) if its concept
carries a PropBank sense number, and a **concept** (`concept`) otherwise — the rules
key on that distinction constantly. And the graph's root is marked `focus="yes"`,
which several rules use as the last-resort place to attach an event.

## 3. The anchored graph

The UD analysis is merged into the same dict, and anchor edges are added from AMR
variables to the tokens that realise them. This is the graph the rules see.

Tokens become nodes keyed by their index, carrying the CoNLL-U columns as features:

```json
"1": { "id": "1", "form": "She",     "lemma": "she",   "upos": "PRON",
       "Case": "Nom", "Number": "Sing", "Person": "3", "PronType": "Prs" },
"2": { "id": "2", "form": "chaired", "lemma": "chair", "upos": "VERB",
       "Mood": "Ind", "Number": "Sing", "Person": "3",
       "Tense": "Past", "VerbForm": "Fin" }
```

Dependency relations become edges between token nodes (`nsubj`, `obj`, `punct`, and a
`root` edge from the artificial node `0`). Anchors become `anchor` edges:

```json
{ "src": "c",  "label": "anchor", "tar": "2" }
{ "src": "s",  "label": "anchor", "tar": "1" }
{ "src": "i2", "label": "anchor", "tar": "3" }
```

That is the whole mechanism by which a rule reaches surface evidence: match an AMR
node, follow its `anchor` edge, and read the token's features or its dependents. The
tense of *chaired* is `Tense=Past` on token 2, and the rule that writes tense finds it
exactly that way.

One node is added before rewriting begins — an event node seeded from the verbal
anchor:

```json
"S1": { "event": "S1", "type": "S", "src": "split", "core": "c" }
```

with a `link` edge to the predicate it covers. `core` records which predicate the event
was built from, and the localization rules use it to decide which event a node belongs
to when two compete.

An AMR node with no anchor is not an error. Anchoring is best-effort, and rules that
need surface evidence simply do not fire.

## 4. YARN — the output

YARN is a nine-tuple `⟨S, V, F, D, E, C, L, H, I⟩`. Those nine sets are not a
description imposed on the output — they are literally the `type` feature the rules
write, so the correspondence is exact:

| set | `type` | what it holds |
|---|---|---|
| S | `"S"` | event nodes, one per event or state |
| V | `"V"` | predicate–argument nodes, senses and roles as in AMR |
| F | `"F"` | features, each one semantic phenomenon, each attached to one event |
| E | `"E"` | edges between V-nodes, carrying roles |
| C | `"C"` | edges from a V-node to an S-node, when an event is an argument |
| D | `"D"` | edges between S-nodes, discourse relations |
| L | `"L"` | layer edges from a feature to a V-node |
| H | `"H"` | hyperedges, from a feature to an L- or H-edge, or from one of those to a V-node or E-edge |
| I | `"I"` | undirected edges between V-nodes, set relations |

Nodes and edges are both nodes in the working representation — an E-edge is a node with
`type="E"` — which is what lets a hyperedge point at an edge.

A tenth value, `"Hp"`, marks a hyperedge that has been drafted but not yet attached to
its feature. It is a non-terminal: no finished graph should contain one.

### The feature vocabulary

The F set is drawn from a fixed list of nineteen semantic phenomena, each the subject
of one rule package:

```
aspect  def     degree  deixis  dir   distr  duration  focus  freq  loc
manner  mod     modal   mood    neg   num    quant     question    temp
```

A feature node carries `feat` naming the phenomenon; the value node beneath it carries
`value` and the same `feat`.

### The written form

`toYarn` ([`formats/yarn.py`](../src/weave_amr2yarn/formats/yarn.py)) turns the
rewritten graph into the YARN document. The nine sets appear as top-level keys, `I`
written as `x`:

```json
{
  "meta":   { "id": "fracas-120.premise_1", "snt": "She chaired it." },
  "s":      ["S1"],
  "v":      ["c", "i2", "s"],
  "f":      { "S1": ["_5_", "_3_", "_4_"] },
  "e":      { "_1_": ["c", "ARG0", "s"], "_2_": ["c", "ARG1", "i2"] },
  "l":      { "_9_": ["_5_", "past",     "c"],
              "_7_": ["_4_", "singular", "i2"],
              "_8_": ["_4_", "singular", "s"],
              "_6_": ["_3_", "",         "c"] },
  "d": {}, "c": {}, "x": {}, "h": {},
  "labels": { "c": "chair-01", "s": "she", "i2": "it",
              "_5_": "temp", "_4_": "num", "_3_": "aspect" }
}
```

Read back: one event `S1`; three predicate–argument nodes; three features hanging off
that event (tense, aspect, number); two role edges; and four layer edges — *chaired* is
past, *she* and *it* are singular, and the aspect layer is present but unfilled, which
is how the rules record that they could not determine it.

### Identifiers

Nodes the rules create have no name of their own, so the engine invents one. Those
names depend on internal ordering, which would make two runs of the same input differ
textually. `canonicalize` ([`graph/canonical.py`](../src/weave_amr2yarn/graph/canonical.py))
renames them from the structure of the graph — the `_3_`, `_4_`, `_5_` above are
canonical, not whatever the engine happened to allocate — and numbers the event nodes
`S1`, `S2`, … in a fixed order. Two conversions of the same input are byte-identical.

## Anchors as a standalone artifact

Anchors can be computed once and reused, in which case they are a JSON dictionary keyed
by sentence and then by AMR variable:

```json
{ "fracas-120.premise_1": { "c": "2", "s": "1", "i2": "3" } }
```

`AnchorDictionary` ([`formats/anchors.py`](../src/weave_amr2yarn/formats/anchors.py))
reads and writes these, and reports `sentenceIds()`, `anchorCount()` and `triples()`
for comparing two dictionaries against each other.

Worth keeping, because rewriting consumes the anchor edges: the output does not say
what the anchors were. `--stamp-meta` records them in each graph's metadata for that
reason.

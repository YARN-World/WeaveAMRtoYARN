# align2anchor — alignments in, convention anchors out

One package for the whole transformation, unified by its interchange
format: every aligner's output is adapted into the same anchor
dictionary, and every downstream stage consumes and produces that same
format. Planning document — implementation to follow (see PLAN below).

## Architecture (ports & adapters around one core)

    aligner output ──ADAPTER──►  AnchorDict  ──FILTER──►  AnchorDict  ──[REPAIR]──►  AnchorDict
    (LEAMR json,     format         raw         keep/deny    shipped        off by      extended
     ISI tsv,        concern                    (licenses)   result         default)
     epidata, …)

- **The format is the contract.** `{sent_id: {var: ud_token_id}}` at
  every boundary. Stages are composable because they share it; a new
  aligner touches one adapter file and nothing else; the ablation is
  literally "run with/without the repair stage".
- **Core domain = the convention** (`licenses.py`): the single source of
  truth. Each license/denial examines one variable in its sentence
  context and returns a **Verdict** (keep | deny, license id, reason)
  and optionally a **Proposal** (retarget/add value). Verdicts and
  proposals are separate objects — this is the split that makes
  removal-only a component instead of a simulation:
  the FILTER consumes verdicts only; the REPAIR stage consumes proposals.
- **Adapters own everything format-shaped**: parsing (LEAMR JSON layers,
  ISI paths, penman epidata), span→token resolution (R-SPAN head
  selection MOVES HERE from the rules layer), aligner-token→UD-id
  remapping, the UD-token feed. Contract: emit only genuine graph
  variables with scalar UD ids — no wiki/literal pseudo-vars (the
  current silent-drop gap becomes an adapter-side validation error).
- **Audit is cross-cutting**: every stage emits Decision rows into one
  explain stream (shared TSV schema incl. LITERAL rows), so the
  per-decision auditability claim holds across the whole chain, not
  just inside the rules.

## Layout

    align2anchor/
      format.py        AnchorDict load/save/validate; strict triple diff
      context.py       SentenceContext: AMR variables/graph + UD tokens
      licenses.py      the convention: license & denial inventory → Verdict/Proposal
      filter.py        convention filter (removal-only; verdicts only)
      repair.py        optional relocation/addition stage (proposals; off by default)
      adapters/
        base.py        Adapter protocol + registry; span resolution; UD remap
        leamr.py       LEAMR-format layers (native LEAMR and SPRING emissions)
        isi.py         ISI paths (SPRING route, FAA if ever revived)
        amrlib_rbw.py  penman epidata route
        levenshtein.py the lexical baseline as just another source
      evaluate.py      P/R/F1 vs gold (port of alignment/evaluate.py)
      cli.py           `python -m align2anchor adapt|filter|repair|eval|run`
      tests/           acceptance + contract tests (see gates)

  Note the unification the format buys: `adapters/leamr.py` serves BOTH
  LEAMR and SPRING, because SPRING emits LEAMR-format files natively —
  one adapter, two aligners.

## PLAN — implementation steps with gates

1. **format.py + context.py** — types, IO, validation. Gate: round-trips
   every dict in `alignment/data/aligner_comparison_2026-07-19/`.
2. **licenses.py** — port the license/denial inventory out of
   anchor_rules*.py, splitting Verdict from Proposal. PURE refactor.
   Gate: verdict keep-sets equal anchor_rules_v4 keep-sets on all 8
   experiment raw dicts (they define the shipped behavior).
3. **filter.py** — verdicts → removal-only output, full explain incl.
   LITERAL rows. Gate: output EQUAL to the saved removal-only dicts
   (`ro_*` of the experiment) on all 8 raw dicts — the acceptance test
   we already own.
4. **adapters/** — extract from batch_leamr_align.py /
   make_spring_anchors.py / batch_amrlib_align.py; move R-SPAN here;
   levenshtein as a source. Gate: adapted raw dicts equal the current
   scripts' outputs byte-for-byte (LEAMR fracas+pud udtok, SPRING
   fracas+pud, RBW both, levenshtein both).
5. **repair.py** — proposals behind an explicit flag (tense-move policy
   = the v4 rule). Gate: filter+repair equals anchor_rules_v4 output on
   the 8 dicts.
6. **evaluate.py + cli.py + docs** — one CLI for the whole chain; the
   experiment README's tables reproducible with one command per cell.
   Old scripts get deprecation headers pointing here (deleted only
   after a full campaign runs on the new package).

Non-goals: no behavior changes anywhere — every gate is equality
against artifacts we already trust. Behavior evolution (LVC/remnant
repairs, new licenses) starts only AFTER the port is green.
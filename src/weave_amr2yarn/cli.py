"""Command line for AMR to YARN conversion.

    weave convert --amr CORPUS.txt --out DIR [--ud FILE.conllu] [--anchors FILE.json]
    weave doctor
    weave strats [--grs PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ConversionConfig
from .errors import WeaveError
from .formats.amr import AmrCorpus
from .providers.anchors import ChainedAnchorer, LevenshteinAnchorer, PrecomputedAnchorer
from .providers.parser import DEFAULT_ENDPOINT, MODEL_VARIABLE
from .providers.ud import ChainedUd, ConlluUd, StanzaUd
from .resources import bundledGrs
from .transform.converter import BatchConverter, Converter


def _mustExist(path: Path, what: str) -> Path:
    if not path.exists():
        raise SystemExit(f"weave: no such {what}: {path}")
    return path


def _addConversionOptions(parser: argparse.ArgumentParser) -> None:
    """Options shared by every command that ends in a conversion."""
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--ud", help="CoNLL-U file; Stanza is used without it")
    parser.add_argument("--anchors", help="anchor dictionary JSON")
    parser.add_argument("--grs", help="GRS entry file (default: the bundled rules)")
    parser.add_argument("--strat", default="eval", help="strategy (default: eval)")
    parser.add_argument(
        "--key-snt",
        default="snt",
        help="metadata key holding the sentence (default: snt)",
    )
    parser.add_argument("--lang", default="en", help="parser language (default: en)")
    parser.add_argument(
        "--layout",
        choices=("flat", "grouped"),
        default="flat",
        help="grouped puts a.b at a/b.json (default: flat)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="per-sentence seconds, 0 to disable (default: 30)",
    )
    parser.add_argument(
        "--anchor-threshold",
        type=float,
        default=0.7,
        help="Levenshtein similarity floor (default: 0.7)",
    )
    parser.add_argument("--grew-only", action="store_true", help="skip the YARN output")
    parser.add_argument(
        "--strict-ud",
        action="store_true",
        help="fail sentences missing from --ud instead of parsing them",
    )
    parser.add_argument(
        "--penman-dereify",
        action="store_true",
        help="apply the Penman-level -91 dereification before rewriting",
    )
    parser.add_argument(
        "--anchorer",
        choices=("levenshtein", "leamr"),
        default="levenshtein",
        help="how to anchor sentences --anchors does not cover (default: levenshtein)",
    )
    _addAlign2AnchorOptions(parser)


def _addAlign2AnchorOptions(parser: argparse.ArgumentParser) -> None:
    """Options shared by the commands that can reach align2anchor."""
    parser.add_argument(
        "--stages",
        default="filter,repair",
        help="align2anchor stages to apply, comma separated (default: filter,repair)",
    )
    parser.add_argument(
        "--leamr-dir",
        help="LEAMR checkout; too large to bundle, so it has to be found",
    )
    parser.add_argument(
        "--span-resolution",
        choices=("first", "head", "head-common"),
        default="first",
        help="how a multi-token span collapses to one token (default: first)",
    )


def _buildConverter(args) -> tuple[Converter, list[str]]:
    """Assemble the converter, plus notes describing what it will use."""
    config = ConversionConfig(
        grsPath=Path(args.grs) if args.grs else bundledGrs(),
        strategy=args.strat,
        sentenceKey=args.key_snt,
        timeoutSeconds=args.timeout,
        penmanDereify=args.penman_dereify,
    )
    notes = [f"rules   {config.grsPath}  [{config.strategy}]"]

    parser = StanzaUd(language=args.lang, sentenceKey=args.key_snt)
    if args.ud:
        conllu = ConlluUd.fromFile(_mustExist(Path(args.ud), "CoNLL-U file"))
        ud = conllu if args.strict_ud else ChainedUd(conllu, parser)
        notes.append(
            f"ud      {args.ud}  ({len(conllu)} sentences)"
            + ("" if args.strict_ud else ", Stanza for the rest")
        )
    else:
        ud, conllu = parser, None
        notes.append(f"ud      Stanza ({args.lang})")

    computed = LevenshteinAnchorer(threshold=args.anchor_threshold)

    if getattr(args, "anchorer", "levenshtein") == "leamr":
        if not args.ud:
            raise SystemExit(
                "weave: --anchorer leamr needs --ud: LEAMR is aligned against the "
                "UD tokenisation"
            )
        from .providers.align2anchor import Align2AnchorAnchorer

        leamr = Align2AnchorAnchorer(
            args.amr,
            args.ud,
            leamrDir=args.leamr_dir,
            spanResolution=args.span_resolution,
            stages=tuple(s for s in args.stages.split(",") if s),
        )
        anchors = ChainedAnchorer(leamr, computed)
        notes.append(
            f"anchors LEAMR via align2anchor "
            f"[{args.stages or 'no stages'}, spans={args.span_resolution}], "
            "Levenshtein for the rest"
        )
    elif args.anchors:
        precomputed = PrecomputedAnchorer.fromFile(
            _mustExist(Path(args.anchors), "anchor dictionary")
        )
        anchors = ChainedAnchorer(precomputed, computed)
        notes.append(
            f"anchors {args.anchors}  ({len(precomputed.anchors)} sentences), "
            "Levenshtein for the rest"
        )
    else:
        anchors = computed
        notes.append(f"anchors Levenshtein (threshold {args.anchor_threshold})")

    return Converter(config, ud=ud, anchors=anchors), notes


def runAnchors(args) -> int:
    """Produce an anchor dictionary without converting anything."""
    from .providers.align2anchor import Align2AnchorAnchorer

    anchorer = Align2AnchorAnchorer(
        _mustExist(Path(args.amr), "AMR corpus"),
        _mustExist(Path(args.ud), "CoNLL-U file"),
        source=args.source,
        rawPath=args.raw,
        stages=tuple(s for s in args.stages.split(",") if s),
        leamrDir=args.leamr_dir,
        spanResolution=args.span_resolution,
    )
    print(
        f"anchoring with {args.source}"
        f" [{args.stages or 'no stages'}, spans={args.span_resolution}]",
        file=sys.stderr,
    )
    anchors = anchorer.build()
    anchors.toFile(args.out)
    print(
        f"{len(anchors)} sentences, {anchors.anchorCount()} anchors -> {args.out}",
        file=sys.stderr,
    )

    if args.audit:
        if anchorer.writeAudit(args.audit):
            print(f"audit -> {args.audit}", file=sys.stderr)
        else:
            print("weave: no audit to write (filter stage did not run)", file=sys.stderr)
    return 0


def _buildParser(args):
    """The AMR parser named on the command line."""
    if args.parser == "spring":
        from .providers.parser import SpringParser

        return SpringParser(args.spring_endpoint), f"SPRING service {args.spring_endpoint}"

    from .providers.parser import AmrlibParser

    parser = AmrlibParser(args.amr_model, device=args.device)
    return parser, f"amrlib {parser.modelDir}"


def runRun(args) -> int:
    """Parse raw text into AMR, then convert it."""
    from .providers.parser import parseToCorpus, readSentences

    sentences = readSentences(_mustExist(Path(args.text), "text file"))
    if not sentences:
        raise SystemExit(f"weave: no sentences in {args.text}")

    # LEAMR aligns an AMR file against a CoNLL-U file, so parsed text has to be
    # written out first for it to have anything to read.
    if args.anchorer == "leamr" and not (args.save_amr and args.ud):
        raise SystemExit(
            "weave: --anchorer leamr needs --save-amr and --ud, since it aligns "
            "files rather than in-memory graphs"
        )

    parser, description = _buildParser(args)
    print(f"parser  {description}", file=sys.stderr)
    print(f"parsing {len(sentences)} sentences", file=sys.stderr)
    corpus = parseToCorpus(parser, sentences, sentenceKey=args.key_snt)

    if args.save_amr:
        Path(args.save_amr).write_text(
            "\n\n".join(sentence.penman for sentence in corpus) + "\n",
            encoding="utf-8",
        )
        print(f"amr     -> {args.save_amr}", file=sys.stderr)

    # Parsed text has no gold UD or anchors, so the converter falls back to
    # Stanza and Levenshtein unless the caller supplied something.
    args.amr = args.save_amr or "<parsed>"
    converter, notes = _buildConverter(args)
    for note in notes:
        print(note, file=sys.stderr)

    print(f"converting {len(corpus)} sentences -> {args.out}", file=sys.stderr)
    report = BatchConverter(converter).run(
        corpus, args.out, layout=args.layout, grewOnly=args.grew_only
    )
    print(report.summary(), file=sys.stderr)
    for sentenceId, message in report.failures:
        print(f"  failed  {sentenceId}: {message}", file=sys.stderr)
    return 1 if report.failures else 0


def runConvert(args) -> int:
    corpus = AmrCorpus.fromFile(_mustExist(Path(args.amr), "AMR corpus"))

    converter, notes = _buildConverter(args)
    for note in notes:
        print(note, file=sys.stderr)

    duplicates = corpus.duplicateIds()
    if duplicates:
        print(
            f"weave: warning: {len(duplicates)} sentence id(s) used more than once; "
            f"later blocks overwrite earlier output ({', '.join(duplicates[:5])})",
            file=sys.stderr,
        )

    missingUd = missingAnchors = []
    if args.ud:
        conllu = converter.ud if isinstance(converter.ud, ConlluUd) else converter.ud.providers[0]
        missingUd = [s.id for s in corpus if s.id not in conllu]
    if args.anchors:
        precomputed = converter.anchors.providers[0]
        missingAnchors = [s.id for s in corpus if s.id not in precomputed]

    for label, missing, fallback in (
        ("--ud", missingUd, "Stanza" if not args.strict_ud else "nothing"),
        ("--anchors", missingAnchors, "Levenshtein"),
    ):
        if missing:
            print(
                f"weave: warning: {len(missing)} sentence(s) absent from {label}, "
                f"falling back to {fallback} ({', '.join(missing[:5])}"
                f"{', ...' if len(missing) > 5 else ''})",
                file=sys.stderr,
            )

    print(f"converting {len(corpus)} sentences -> {args.out}", file=sys.stderr)
    report = BatchConverter(converter).run(
        corpus, args.out, layout=args.layout, grewOnly=args.grew_only
    )
    print(report.summary(), file=sys.stderr)
    for sentenceId, message in report.failures:
        print(f"  failed  {sentenceId}: {message}", file=sys.stderr)

    return 1 if report.failures else 0


def runBatch(args) -> int:
    """Convert every corpus a config file names."""
    from types import SimpleNamespace

    from .batch import loadPlan

    plan = loadPlan(_mustExist(Path(args.config), "config file"))
    root = Path(args.out_root) if args.out_root else plan.outRoot
    specs = plan.select(args.only)

    print(f"{plan.source}: {len(specs)} corpus/corpora -> {root}", file=sys.stderr)

    failures = 0
    for position, spec in enumerate(specs, 1):
        outDir = spec.outputDir(root)
        print(f"\n[{position}/{len(specs)}] {spec.name} -> {outDir}", file=sys.stderr)

        # A spec carries the same settings the flags do, so it is turned into
        # the shape _buildConverter already understands rather than growing a
        # second way to assemble a converter.
        namespace = SimpleNamespace(
            amr=spec.amr,
            ud=spec.ud,
            anchors=spec.anchors,
            anchorer=spec.anchorer,
            grs=spec.grs,
            strat=spec.strat,
            key_snt=spec.keySnt,
            lang=spec.lang,
            timeout=spec.timeout,
            anchor_threshold=spec.anchorThreshold,
            penman_dereify=spec.penmanDereify,
            strict_ud=spec.strictUd,
            stages=spec.stages,
            leamr_dir=spec.leamrDir,
            span_resolution=spec.spanResolution,
        )

        try:
            corpus = AmrCorpus.fromFile(_mustExist(Path(spec.amr), "AMR corpus"))
            converter, notes = _buildConverter(namespace)
            for note in notes:
                print(f"  {note}", file=sys.stderr)
            report = BatchConverter(converter).run(
                corpus, outDir, layout=spec.layout, grewOnly=spec.grewOnly
            )
            print(f"  {report.summary()}", file=sys.stderr)
            for sentenceId, message in report.failures:
                print(f"    failed  {sentenceId}: {message}", file=sys.stderr)
            failures += report.failed
        except (WeaveError, SystemExit) as exc:
            # One bad corpus should not abandon the rest of the sweep.
            print(f"  ERROR: {exc}", file=sys.stderr)
            failures += 1

    print(f"\ndone, {failures} failure(s)", file=sys.stderr)
    return 1 if failures else 0


def runDoctor(args) -> int:
    from .doctor import report

    text, healthy = report(args.lang)
    print(text)
    return 0 if healthy else 1


def runStrats(args) -> int:
    from .transform.session import GrsSession

    path = Path(args.grs) if args.grs else bundledGrs()
    # Any declared strategy is fine here; we only want to read the file.
    session = GrsSession(path, strategy="main")
    print(f"{path}\n")
    print("strategies:")
    for name in session.strategies():
        print(f"  {name}")
    qualified = session.qualifiedStrategies()
    if qualified:
        print("\nstrategies inside packages:")
        for name in qualified:
            print(f"  {name}")
    return 0


def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weave", description=__doc__.split("\n")[0])
    parser.add_argument("--version", action="version", version=f"weave {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    convert = commands.add_parser("convert", help="convert an AMR corpus to YARN")
    convert.add_argument("--amr", required=True, help="AMR corpus in Penman format")
    _addConversionOptions(convert)
    convert.set_defaults(handler=runConvert)

    run = commands.add_parser(
        "run", help="parse raw text into AMR, then convert it to YARN"
    )
    run.add_argument("--text", required=True, help="one sentence per line")
    run.add_argument(
        "--parser",
        choices=("amrlib", "spring"),
        default="amrlib",
        help="amrlib runs in this process; spring talks to a service "
        "(default: amrlib)",
    )
    run.add_argument(
        "--amr-model",
        help=f"amrlib model directory, or set {MODEL_VARIABLE}",
    )
    run.add_argument(
        "--spring-endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"SPRING service URL (default: {DEFAULT_ENDPOINT})",
    )
    run.add_argument("--device", help="torch device for amrlib, e.g. cpu or cuda:0")
    run.add_argument("--save-amr", help="also write the parsed AMR corpus here")
    _addConversionOptions(run)
    run.set_defaults(handler=runRun)

    anchors = commands.add_parser(
        "anchors", help="produce an anchor dictionary with align2anchor"
    )
    anchors.add_argument("--amr", required=True, help="AMR corpus in Penman format")
    anchors.add_argument("--ud", required=True, help="CoNLL-U file")
    anchors.add_argument("--out", required=True, help="anchor dictionary to write")
    anchors.add_argument(
        "--source",
        choices=("leamr", "raw"),
        default="leamr",
        help="run the aligner, or read its output (default: leamr)",
    )
    anchors.add_argument("--raw", help="aligner output, required by --source raw")
    anchors.add_argument("--audit", help="write the filter's decisions to this TSV")
    _addAlign2AnchorOptions(anchors)
    anchors.set_defaults(handler=runAnchors)

    batch = commands.add_parser(
        "batch", help="convert every corpus named in a config file"
    )
    batch.add_argument("--config", required=True, help="TOML config file")
    batch.add_argument(
        "--only", nargs="+", metavar="NAME", help="run only these corpora"
    )
    batch.add_argument(
        "--out-root", help="write under here instead of the config's out_root"
    )
    batch.set_defaults(handler=runBatch)

    doctor = commands.add_parser("doctor", help="check the environment")
    doctor.add_argument("--lang", default="en")
    doctor.set_defaults(handler=runDoctor)

    strats = commands.add_parser("strats", help="list strategies in a GRS")
    strats.add_argument("--grs", help="GRS entry file (default: the bundled rules)")
    strats.set_defaults(handler=runStrats)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = buildParser().parse_args(argv)
    try:
        return args.handler(args)
    except WeaveError as exc:
        print(f"weave: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
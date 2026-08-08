"""The editor sample format.

The assertions mirror what yarn-editor's importer actually does, since that is
the contract: it reads metadata.txt as `# key = value` with lowercased keys,
and names each record by the graph's own meta.sent_id.
"""

from __future__ import annotations

import json
import re
import zipfile

from weave_amr2yarn.formats.editor import (
    METADATA_NAME,
    metadataText,
    readYarnDirectory,
    safeName,
    withEditorMetadata,
    writeEditorZip,
)

GRAPHS = {
    "s1": {"meta": {"id": "s1", "snt": "A dog runs."}, "s": ["S1"], "labels": {}},
    "fracas-001.premise_0": {"meta": {"id": "fracas-001.premise_0"}, "s": ["S1"]},
}


def readMetadata(text):
    """The importer's own parser, reproduced."""
    found = {}
    for line in text.split("\n"):
        matched = re.match(r"^#\s*([\w-]+)\s*=\s*(.+?)\s*$", line)
        if not matched:
            continue
        key, value = matched.group(1).strip().lower(), matched.group(2).strip()
        if key == "sampleid":
            found["id"] = value
        elif key == "samplename":
            found["name"] = value
    return found


def test_sentIdIsAddedBecauseTheImporterNamesRecordsByIt():
    out = withEditorMetadata({"meta": {"id": "s1"}}, "s1")
    assert out["meta"]["sent_id"] == "s1"


def test_existingSentIdIsKept():
    out = withEditorMetadata({"meta": {"sent_id": "given", "id": "other"}}, "s1")
    assert out["meta"]["sent_id"] == "given"


def test_ourOwnIdSurvivesToo():
    """The graph must still read back through this project's own tools."""
    assert withEditorMetadata({"meta": {}}, "s1")["meta"]["id"] == "s1"


def test_metadataParsesWithTheImportersRules():
    parsed = readMetadata(metadataText("demo", "abc-123", "2026-01-01T00:00:00.000Z"))
    assert parsed == {"name": "demo", "id": "abc-123"}


def test_zipHasARecordPerGraphPlusTheSidecar(tmp_path):
    path = writeEditorZip(GRAPHS, tmp_path / "demo.zip", sampleName="demo")
    names = zipfile.ZipFile(path).namelist()
    assert f"demo/{METADATA_NAME}" in names
    assert sum(1 for n in names if n.endswith(".yarn.json")) == len(GRAPHS)


def test_recordsAreNamedByTheirSentenceId(tmp_path):
    path = writeEditorZip(GRAPHS, tmp_path / "demo.zip", sampleName="demo")
    archive = zipfile.ZipFile(path)
    graph = json.loads(archive.read("demo/fracas-001.premise_0.yarn.json"))
    assert graph["meta"]["sent_id"] == "fracas-001.premise_0"


def test_jsonlPutsEveryGraphInOneFile(tmp_path):
    path = writeEditorZip(GRAPHS, tmp_path / "demo.zip", sampleName="demo", asJsonl=True)
    archive = zipfile.ZipFile(path)
    lines = archive.read("demo/demo.jsonl").decode().strip().split("\n")
    assert len(lines) == len(GRAPHS)
    assert json.loads(lines[0])["meta"]["sent_id"] == "s1"


def test_sampleIdDiffersBetweenExports(tmp_path):
    """Two exports are two samples, so the editor must not merge them."""
    first = readMetadata(
        zipfile.ZipFile(writeEditorZip(GRAPHS, tmp_path / "a.zip", sampleName="s"))
        .read(f"s/{METADATA_NAME}").decode()
    )
    second = readMetadata(
        zipfile.ZipFile(writeEditorZip(GRAPHS, tmp_path / "b.zip", sampleName="s"))
        .read(f"s/{METADATA_NAME}").decode()
    )
    assert first["id"] != second["id"]


def test_awkwardIdsBecomeSafeFilenames():
    assert safeName("fracas-001.premise_0") == "fracas-001.premise_0"
    assert safeName("a/b c") == "a_b_c"
    assert safeName("///") == "record"


def test_directoriesAreReadByTheGraphsOwnIdNotTheFilename(tmp_path):
    """A grouped layout must keep its real ids."""
    nested = tmp_path / "fracas-001"
    nested.mkdir()
    (nested / "premise_0.json").write_text(
        json.dumps({"meta": {"id": "fracas-001.premise_0"}, "s": ["S1"]}),
        encoding="utf-8",
    )
    assert list(readYarnDirectory(tmp_path)) == ["fracas-001.premise_0"]


def test_theSidecarIsNotReadBackAsAGraph(tmp_path):
    (tmp_path / METADATA_NAME).write_text("# sampleName = x\n", encoding="utf-8")
    (tmp_path / "s1.json").write_text(
        json.dumps({"meta": {"id": "s1"}}), encoding="utf-8"
    )
    assert list(readYarnDirectory(tmp_path)) == ["s1"]

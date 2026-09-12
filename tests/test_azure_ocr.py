"""Check cloud upload boundaries, page evidence, and CLI defaults without Azure calls."""

import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pypdf import PdfReader, PdfWriter

from fda510k import azure_di, cli, extractors
from fda510k.models import OcrResult


def make_pdf() -> bytes:
    writer = PdfWriter()
    for width in [100, 200, 300]:
        writer.add_blank_page(width=width, height=400)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_azure_upload_contains_only_selected_pages_and_preserves_original_page_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_result = SimpleNamespace(
        content="Page two. Page three.",
        pages=[
            SimpleNamespace(page_number=1, words=[], spans=[SimpleNamespace(offset=0, length=9)]),
            SimpleNamespace(page_number=2, words=[], spans=[SimpleNamespace(offset=10, length=11)]),
        ],
    )
    client = Mock()
    client.begin_analyze_document.return_value.result.return_value = service_result
    monkeypatch.setattr(azure_di, "AzureClient", Mock(return_value=client))
    extractor = azure_di.AzureLayoutExtractor("https://example.cognitiveservices.azure.com/")

    result = extractor.extract_layout(make_pdf(), page_numbers=[2, 3])

    uploaded_request = client.begin_analyze_document.call_args.args[1]
    uploaded_pdf = PdfReader(BytesIO(uploaded_request.bytes_source))
    assert [int(page.mediabox.width) for page in uploaded_pdf.pages] == [200, 300]
    assert result.text_by_page == {2: "Page two.", 3: "Page three."}
    assert client.begin_analyze_document.call_args.kwargs["string_index_type"] == "unicodeCodePoint"


def test_empty_page_selection_does_not_call_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    monkeypatch.setattr(azure_di, "AzureClient", Mock(return_value=client))
    extractor = azure_di.AzureLayoutExtractor("https://example.cognitiveservices.azure.com/")

    assert extractor.extract_layout(make_pdf(), page_numbers=[]).text_by_page == {}
    client.begin_analyze_document.assert_not_called()


def test_invalid_page_selection_fails_before_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    monkeypatch.setattr(azure_di, "AzureClient", Mock(return_value=client))
    extractor = azure_di.AzureLayoutExtractor("https://example.cognitiveservices.azure.com/")

    with pytest.raises(ValueError, match="outside the PDF"):
        extractor.extract_layout(make_pdf(), page_numbers=[4])
    client.begin_analyze_document.assert_not_called()


def test_fallback_sends_only_weak_pages_and_keeps_existing_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readable_text = "An existing page with enough text to remain on the local extraction path."
    pages = [
        SimpleNamespace(extract_text=lambda: readable_text),
        SimpleNamespace(extract_text=lambda: ""),
    ]
    monkeypatch.setattr(extractors, "PdfReader", lambda _: SimpleNamespace(pages=pages))
    monkeypatch.setattr(
        extractors.PdfExtractor, "_enrich_with_pdfplumber", staticmethod(lambda _, text: text)
    )
    cloud = Mock()
    cloud.extract_layout.return_value = OcrResult(text_by_page={2: "Predicate K123456"})

    result = extractors.PdfExtractor(cloud).extract("example.pdf", "digest", b"example")

    cloud.extract_layout.assert_called_once_with(b"example", page_numbers=[2])
    assert result.text_by_page == {1: readable_text, 2: "Predicate K123456"}
    assert result.used_document_intelligence is True


def test_cli_uses_azure_by_default_from_local_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("DOCUMENT_INTELLIGENCE_KEY", raising=False)
    Path("local.settings.json").write_text(
        json.dumps(
            {
                "Values": {
                    "DOCUMENT_INTELLIGENCE_ENDPOINT": "https://example.cognitiveservices.azure.com/"
                }
            }
        )
    )
    Path("example.pdf").write_bytes(make_pdf())
    cloud = Mock()
    cloud.extract_layout.return_value = OcrResult(text_by_page={1: "Predicate K123456"})
    constructor = Mock(return_value=cloud)
    monkeypatch.setattr(cli, "AzureLayoutExtractor", constructor)
    monkeypatch.setattr("sys.argv", ["fda510k", "example.pdf", "--k-number", "K654321"])

    cli.main()

    constructor.assert_called_once_with("https://example.cognitiveservices.azure.com/", None)
    assert cloud.extract_layout.called
    saved = json.loads(Path("data/audit.jsonl").read_text())
    assert saved["extractor"] == "azure-layout"
    assert saved["relationships"][0]["predicate_k_number"] == "K123456"


def test_local_only_ignores_cloud_settings_and_force_reprocesses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("example.pdf").write_bytes(make_pdf())
    Path("local.settings.json").write_text("invalid configuration is irrelevant to local-only")
    constructor = Mock(side_effect=AssertionError("Local mode must not construct Azure"))
    monkeypatch.setattr(cli, "AzureLayoutExtractor", constructor)
    arguments = ["fda510k", "example.pdf", "--k-number", "K654321", "--local-only"]
    monkeypatch.setattr("sys.argv", arguments)
    cli.main()
    cli.main()
    assert len(Path("data/audit.jsonl").read_text().splitlines()) == 1

    monkeypatch.setattr("sys.argv", arguments + ["--force"])
    cli.main()

    assert len(Path("data/audit.jsonl").read_text().splitlines()) == 2
    constructor.assert_not_called()


def test_default_mode_requires_an_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.setattr("sys.argv", ["fda510k", "example.pdf", "--k-number", "K654321"])

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2


def test_module_command_runs_processing_and_exports_parquet(tmp_path: Path) -> None:
    pdf_path = tmp_path / "example.pdf"
    pdf_path.write_bytes(make_pdf())
    audit_path = tmp_path / "audit.jsonl"
    export_path = tmp_path / "audit.parquet"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(cli.__file__).resolve().parents[1])

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "fda510k.cli",
            str(pdf_path),
            "--k-number",
            "K654321",
            "--local-only",
            "--audit-file",
            str(audit_path),
            "--export",
            str(export_path),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(completed.stdout)["status"] == "completed"
    assert json.loads(audit_path.read_text())["relationships"][0]["status"] == "unmatched"
    assert export_path.read_bytes().startswith(b"PAR1")

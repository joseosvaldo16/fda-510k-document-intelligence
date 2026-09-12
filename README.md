# FDA 510(k) Document Intelligence

A Python project that finds predicate-device references in public FDA PDFs and saves each result with its page number and supporting text.

A **predicate** is an existing legally marketed device used for comparison in a 510(k) submission. A **K-number** identifies a submission. This project makes those references easier to find and check; it does not decide whether devices are equivalent. See the [FDA's explanation](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/premarket-notification-510k).

The project combines PDF parsing, Azure OCR, rule-based matching, and an optional LLM review. It uses pretrained models; no custom model has been trained.

## Goal and dataset

The goal is to turn references buried in PDFs into searchable relationships with evidence a reviewer can inspect.

The development sample contains **13 public FDA PDFs, totaling 88 pages**, with 3–13 pages per file. It includes device summaries, comparison tables, clearance letters, and indications-for-use forms. Files were selected because they downloaded successfully, so the sample is not representative of the full FDA archive.

[The benchmark labels](benchmarks/fda_predicates.json) record source URLs, PDF hashes, reviewed page numbers, and expected relationships: **21 predicates and four reference devices**. Primary and additional predicates are retained separately. Devices labeled “reference,” including “reference predicates,” are stored as references and excluded from predicate-only scores. Two PDFs contain no numbered predicate references; this does not establish that the devices have no predicates.

Labels were checked against rendered source pages before the LLM comparison. They are a single development review, not independently adjudicated ground truth. PDFs and full extraction outputs remain outside Git. The separate `scripts/download_reference_data.py` script downloads 100 metadata records from [openFDA](https://open.fda.gov/apis/device/510k/); that is not the benchmark corpus.

## How it works

1. **Read the PDF.** Extract page text with `pypdf`; try `pdfplumber` on pages with fewer than 40 characters.
2. **Check for extraction problems.** Send empty or short pages and pages with malformed K-number patterns to Azure Document Intelligence. A text-heavy page can still need OCR.
3. **Keep source detail.** Upload only the selected pages, preserve original page numbers, and retain Azure word-confidence scores. Table objects are not retained or scored.
4. **Find relationships.** The default rules read predicate sections and tables, preserve multiple predicates, distinguish reference devices, and exclude the source document's own number. Whitespace inside identifiers can be joined; uncertain letters are not silently replaced.
5. **Optionally use an LLM.** Azure OpenAI classifies relationships and returns page and line ranges. The program builds evidence directly from those source lines and checks the identifier and relationship label. Unsupported suggestions remain `ambiguous` for review.
6. **Save results.** Pydantic records are written to JSONL and can be exported to CSV or Parquet with DuckDB. File hashes prevent repeat processing; `--force` reruns a recorded PDF.

### Confidence-based OCR review

With `--matching llm`, K-number-like OCR words below **0.90 confidence** are checked against a rendered page image. Azure provides word confidence, not an independent score for each character. The thresholds are review settings, not calibrated accuracy guarantees.

An automatic correction requires agreement between the vision reading and another OCR occurrence at **0.95 confidence or higher**, plus a supported O/0 or I/l/1 character confusion. Otherwise the original text stays intact and affected relationships require review. Original OCR words and review notes are retained. Model confidence alone never authorizes a correction. A live controlled test corrected an injected `K13O391` to `K130391` using the original page image and a separate strong OCR occurrence; this does not measure correction accuracy on naturally occurring errors.

## What the evaluation shows

The September 12, 2026 comparison uses the same reviewed answers for every method. Predicate metrics count distinct source-to-predicate relationships; references are scored separately. Full-document correctness requires all relationship identities and types to agree, with no unresolved review items.

| Method | Correct / suggested | Found / expected | F1 | Complete documents |
| --- | --- | --- | --- | --- |
| Original matcher, local text | 13 / 20 (65%) | 13 / 21 (61.9%) | 0.634 | 4 / 13 |
| Improved rules, local text | 18 / 18 (100%) | 18 / 21 (85.7%) | 0.923 | 11 / 13 |
| **Improved rules + Azure OCR** | **21 / 21 (100%)** | **21 / 21 (100%)** | **1.000** | **13 / 13** |
| LLM + the same Azure text | 20 / 20 (100%) | 20 / 21 (95.2%) | 0.976 | 12 / 13 |

Both improved approaches also recovered all four reference relationships without false reference matches. One LLM answer failed source-evidence validation and was held for review. Rules plus OCR remain the default because they performed best on this sample; the LLM option is available for further evaluation.

These are **development results, not held-out performance**. Parsing rules were improved using this sample, and the LLM prompt was revised after an initial run. The saved comparison reports the final implementations. A larger, independently reviewed test set is needed before claiming general accuracy.

The earlier 75% figure is superseded. The old review missed three predicates in K140814 and mixed reference predicates into the predicate total. [Results by document](benchmarks/results.json) and [the evaluation script](benchmarks/evaluate.py) make the revised definitions and calculations inspectable.

### Why character counts are not a quality measure

Returned text can contain incorrect identifiers, broken tables, or missing sections. Character counts only help route weak pages. The benchmark checks relationship identities and types, not overall transcription, reading order, table-cell accuracy, or every device field.

## Challenges and current limits

- **Long lists:** section parsing now finds later entries that the original 100-character window missed.
- **Several valid predicates:** each gets its own relationship instead of treating the whole document as ambiguous.
- **Damaged embedded text:** malformed identifiers can trigger OCR even when a page has plenty of text.
- **LLM evidence errors:** asking a model to rewrite a quote introduced small transcription changes. Returning source line ranges keeps evidence unchanged and makes validation direct.
- **Remaining gaps:** new layouts, confidently wrong OCR, missing identifiers that do not trigger OCR, and unclear device roles still need broader testing. Generic keyword checks cannot prove a semantic relationship by themselves.
- **Production operation:** failed attempts are currently considered seen unless forced. Concurrent storage, scheduled ingestion, and a hosted deployment are not complete.

Embeddings were not tested. The current task needs exact identifiers and explicit relationship labels; semantic retrieval would be a separate experiment for finding relevant sections in a larger collection.

## Privacy and HIPAA

The project uses public regulatory documents, not a patient-record dataset. This work does **not** establish HIPAA compliance. HIPAA obligations depend on the data and the organization's role; see [HHS guidance](https://www.hhs.gov/hipaa/for-professionals/covered-entities/index.html).

Azure OCR uploads selected pages by default. LLM mode also sends relevant page text and, when needed, page images to the configured Azure OpenAI service. `--local-only` disables cloud processing and cannot be combined with LLM matching.

Live calls used Azure token authentication without storing service keys. Downloaded documents, local configuration, and full audit outputs are excluded from Git. Audit evidence is plain text; Git exclusions and file hashes do not encrypt or anonymize data. There is no automatic PHI redaction.

Handling protected health information would require a separately reviewed deployment with appropriate agreements, risk assessment, access controls, storage protection, retention, and incident procedures. Those controls are not established here. [HHS cloud guidance](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html)

## Run with conda

Use Python 3.12 or newer. Development and checks use the existing `mlenv` environment. Run from the repository root:

```bash
conda activate mlenv
python -m pip install -r requirements.txt
az login
mkdir -p exports
PYTHONPATH=src python -m fda510k.cli path/to/summary.pdf --k-number K123456 --export exports/results.parquet
```

Set `DOCUMENT_INTELLIGENCE_ENDPOINT` in the environment or in `Values` within `local.settings.json`, using the example file as a starting point. The signed-in identity needs access to that service. Azure OCR is enabled by default and may incur charges.

For LLM review, also configure `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT`, then add `--matching llm`. The live comparison used `gpt-5-mini`. Use `--local-only` for local rules, or `--force` when changing methods on a previously processed PDF.

### Live Azure check

Both OCR and LLM matching were exercised against the configured Azure services. The two cloud comparisons used the same saved OCR outputs to isolate matching differences. A separate image-only version of a public page also returned its three expected identifiers through OCR. This is a controlled check, not a benchmark of naturally scanned documents.

### Reproduce the comparison

```bash
PYTHONPATH=src python -m benchmarks.evaluate --method legacy --download --output data/legacy.json
PYTHONPATH=src python -m benchmarks.evaluate --method rules --output data/rules.json
PYTHONPATH=src python -m benchmarks.evaluate --method rules --ocr --output data/rules-ocr.json
PYTHONPATH=src python -m benchmarks.evaluate --method llm --ocr --extraction-cache data/benchmark/rules-ocr --output data/llm-ocr.json
```

Downloads are checked against the saved PDF hashes; changed source files stop evaluation. Cached extractions are also checked against the PDF hash. LLM outputs can vary between runs.

### Code checks

```bash
conda run -n mlenv python -m pip install pytest ruff mypy
PYTHONPATH=src conda run -n mlenv python -m pytest -q
conda run -n mlenv python -m ruff check .
conda run -n mlenv python -m mypy src/fda510k
```

## Skills demonstrated and next steps

The implementation demonstrates PDF processing, OCR routing, structured LLM output, evidence validation, error analysis, typed Python records, and reproducible evaluation. The comparison separates extraction problems from matching problems and tests whether a more complex method adds value.

Next: add independently reviewed documents with new layouts and real scans, measure OCR review precision and correction coverage, and compare methods on a held-out set. Core code is in `src/fda510k/`, tests in `tests/`, and labels and evaluation tools in `benchmarks/`.

`function_app.py` provides a function-key-protected reprocessing endpoint for server-accessible PDFs. Its timer logs a trigger; automated FDA ingestion and verified deployment remain future work.

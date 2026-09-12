# FDA 510(k) Document Intelligence

A Python project that finds predicate-device references in public FDA PDFs and saves each result with its page number and supporting text.

In a 510(k) submission, a manufacturer compares a medical device with an existing legally marketed device, called a **predicate**, to support substantial equivalence. A **K-number** identifies a submission. This project helps locate those references for review; it does not decide whether devices are equivalent. See the [FDA's explanation of the 510(k) process](https://www.fda.gov/medical-devices/premarket-submissions-selecting-and-preparing-correct-submission/premarket-notification-510k).

**Current stage:** a working document-processing baseline with a live Azure OCR integration. Predicate matching uses rules; OCR uses Microsoft's pretrained model. No custom machine-learning model has been trained.

## Goal and dataset

The goal is to turn references buried in PDFs into searchable records that a reviewer can trace back to the document. The intended output is a relationship between a submission and each of its predicates, with evidence for checking the result.

The local development sample contains **13 public FDA PDFs, totaling 88 pages**, with 3–13 pages per file. They include device summaries, comparison tables, and clearance letters. The sample was limited to files that downloaded successfully and is not a random sample of the FDA archive. Every file contains embedded text. A separate Azure check used one page converted into an image-only PDF; performance on naturally scanned documents has not been established.

The sample submission IDs are K102429, K111372, K134031, K140814, K170381, K180583, K213456, K220001, K221537, K221887, K230001, K230857, and K232692. These are submission identifiers, not patient identifiers. The PDFs and local evaluation files are not tracked in Git.

The repository also includes a script that downloads 100 metadata records from the [openFDA 510(k) API](https://open.fda.gov/apis/device/510k/). That metadata sample is separate from the 13-PDF evaluation; the script does not download the benchmark PDFs or their reviewed answers.

## How it works

1. **Identify the file.** Calculate a SHA-256 file hash and check the local audit log for a previous run. This avoids processing the same file twice in a normal local workflow.
2. **Read the PDF.** Use `pypdf` to extract embedded text by page. If a page has fewer than 40 characters, try `pdfplumber`. The threshold is a simple fallback trigger, not a quality score.
3. **Find possible predicates.** Use Python regular expressions to find K-numbers with “predicate” or “substantially equivalent” language within 100 characters before or after the number.
4. **Save a reviewable result.** Use Pydantic models to organize the source K-number, candidate numbers, status, page numbers, and evidence excerpts. The current matcher returns `matched` for one candidate, `ambiguous` for several, and `unmatched` for none. These labels describe the rule's output, not verified correctness.
5. **Store and export.** Append the result to a local JSONL audit file. Use DuckDB to export audit records to CSV or Parquet.

Azure AI Document Intelligence's `prebuilt-layout` model is enabled by default as a fallback for pages that remain weak. The adapter creates a PDF containing **only those pages**, sends it to Azure, and maps the returned text back to the original page numbers. Use `--local-only` to disable cloud processing. The adapter currently keeps page text; it does not retain the service's table or layout objects.

## What the evaluation shows

The saved August 24, 2026 review reported the following results. Counts are pooled across documents; a candidate is a distinct K-number within one source document.

| Measure | Result | Meaning |
| --- | --- | --- |
| Candidate precision | 15 / 20 = **75%** | Of the suggested references, 15 agreed with the reviewed answers and 5 did not. |
| Candidate recall | 15 / 20 = **75%** | Of the 20 reviewed references, 15 were found and 5 were missed. |
| Candidate F1 | **0.75** | The harmonic mean of precision and recall. |
| Complete document result | 4 / 13 = **30.8%** | The saved review marked four documents as fully represented by the current output. |

A local rerun on September 12, 2026 reproduced the candidate count for every document. The saved review contains per-document counts, but a separate answer file with expected K-numbers, page evidence, and labeling rules is missing. The figures above are **preliminary development results**, not an independently reproduced accuracy benchmark. Labels were originally reviewed from extracted text, which can hide errors introduced during extraction.

### Why character counts are not a quality measure

A large amount of extracted text can still contain scrambled reading order, broken tables, incorrect identifiers, or missing sections. Similar character counts from two libraries do not show that either returned the correct text.

Here, character counts only help identify pages that may need another extraction method. The rerun found three pages still below the 40-character threshold. Because OCR was disabled, they were left as local text results. Their low counts alone do not establish whether they contain missed information or are mostly blank.

The project has not measured transcription accuracy, table-cell accuracy, reading order, or completeness of other device fields. A stronger evaluation needs answers checked against rendered PDF pages, with separate scores for correct identifiers, relationship types, evidence locations, and complete documents.

## Challenges and current limits

| Challenge | Current approach and what remains |
| --- | --- |
| Different PDF layouts | Extract by page and try a second library on weak pages. Table structure is not reconstructed or scored. |
| Several valid predicates in one document | Preserve all candidates for review. The current status still calls multiple candidates `ambiguous`, even when the document clearly lists several predicates. |
| Long predicate lists | Search nearby text. In K111372, the rule finds K043272 but misses later list entries K002901 and K092205. Section-aware parsing remains to be implemented. |
| A document mentions its own K-number | Keep evidence so errors can be inspected. K140814 currently matches itself; the matcher needs an explicit self-reference exclusion. |
| Reference devices and predicates appear together | The rule uses nearby keywords. It does not yet distinguish primary predicates, additional predicates, and reference devices. |
| Repeat runs and failures | File hashes prevent repeat work, but the current store also treats a failed attempt as seen. The CLI's `--force` option and the Functions route can force a rerun. Concurrent writes and production storage still need work. |

K102429 illustrates the difference between finding text and modeling the result: both listed predicates, K082320 and K091243, are found, but the output is still `ambiguous`.

## Privacy and HIPAA

This project uses public regulatory documents. It was not built around patient records, and this evaluation does not demonstrate HIPAA compliance. HIPAA obligations depend on the data and the role of the organization handling it; see [HHS guidance on covered entities and business associates](https://www.hhs.gov/hipaa/for-professionals/covered-entities/index.html).

The implemented boundaries are:

- The default workflow uploads weak pages to the configured Azure service. `--local-only` prevents those uploads. No language-model service is used.
- Downloaded files, audit outputs, exports, `.env`, and local Azure settings are excluded from Git. This reduces accidental publication; it does not encrypt files or restrict local access.
- Azure credentials come from configuration. The adapter uses `DefaultAzureCredential` when no key is supplied. The live run used the existing Azure CLI login without retrieving or storing service keys. Managed identity is supported for an Azure-hosted application, but no application was deployed or assigned an identity in this work.
- The audit file retains evidence excerpts in plain text. File hashing detects duplicate content; it does not anonymize the document. There is no automatic PHI detection or redaction.

Using this code with protected health information would require a separate deployment and privacy review: appropriate agreements, risk assessment, access controls, storage protection, retention rules, and incident procedures. Cloud processing would also require appropriate business associate agreements and safeguards, as described in [HHS cloud guidance](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html). Those controls are not established by this repository.

## Run with conda

Requires Python 3.12 or newer. This project is checked in the existing `mlenv` conda environment (Python 3.13). Run from the repository root.

```bash
conda activate mlenv
python -m pip install -r requirements.txt
mkdir -p exports
az login
```

Set `DOCUMENT_INTELLIGENCE_ENDPOINT` in your environment, or copy `local.settings.json.example` to `local.settings.json` and fill in `Values.DOCUMENT_INTELLIGENCE_ENDPOINT` with your resource's endpoint. The endpoint is configuration, not a credential. The signed-in identity needs Document Intelligence data access on that resource. No service key is needed when token authentication is configured.

```bash
PYTHONPATH=src python -m fda510k.cli path/to/summary.pdf --k-number K123456 --export exports/results.parquet
```

Azure OCR is enabled by default and may incur charges. An unset endpoint produces a configuration error. For an entirely local run:

```bash
PYTHONPATH=src python -m fda510k.cli path/to/summary.pdf --k-number K123456 --local-only
```

Use `--force` when comparing extraction settings on a PDF already recorded in the audit file. Otherwise the existing file hash causes the CLI to skip it. To download the separate public metadata sample, run `python scripts/download_reference_data.py`.

`function_app.py` provides `POST /api/reprocess`, accepting `{"pdf_path":"/path/file.pdf","k_number":"K123456"}` for a server-accessible file. It uses function-key authorization. With the endpoint configured, it also uses Azure for weak pages. Its daily timer currently logs a trigger; automated FDA ingestion is not implemented.

### Live Azure check

On September 12, 2026, the default CLI processed K221537 through the existing Azure service and wrote JSONL and Parquet outputs. A second check rendered page 1 of K111372 into an image-only PDF with `pypdfium2` and Pillow. Local text extraction returned no text; Azure OCR recovered **all three expected K-numbers: K043272, K002901, and K092205**.

The predicate matcher still selected only K043272 because the other numbers fell outside its keyword window. This shows why OCR and relationship extraction need separate evaluation. The check verifies a working cloud connection and identifier recovery on one controlled page; it does not measure table accuracy or establish performance across scanned FDA documents. The earlier 13-document accuracy figures remain the results of the local development review.

### Code checks

```bash
conda run -n mlenv python -m pip install pytest ruff mypy
PYTHONPATH=src conda run -n mlenv python -m pytest -q
conda run -n mlenv python -m ruff check .
conda run -n mlenv python -m mypy src/fda510k
```

Tests cover page selection before upload, original page-number mapping, Azure as the CLI default, local-only processing, reruns, and the module command with Parquet export. They run without calling Azure; the live checks above are separate.

## Skills demonstrated and next steps

The implementation shows Python pipeline design, PDF parsing with `pypdf` and `pdfplumber`, rule-based text extraction, Pydantic records, JSONL persistence, DuckDB exports, and token-authenticated Azure OCR. Evaluation separates incorrect suggestions from missed references and exposes errors that a text-volume metric would overlook.

The next development steps are to save a reproducible labeled benchmark, fix self-references and multiple-predicate output with matching regression tests, and evaluate scanned and mixed-layout PDFs. A later ML experiment could compare a learned extraction method with this baseline using a held-out test set. The current cloud integration uses a pretrained model; the project does not demonstrate custom model training.

Core code lives in `src/fda510k/`; `scripts/` contains the metadata downloader. Ruff and mypy are configured for code checks. The Azure integration has regression tests and a live check. Matching-quality regression tests and a verified cloud deployment are still missing.

# sist2 Local AI — first integration slice

This folder is an **experimental, read-only RAG bridge** for the SQLite backend of
sist2. It is intentionally separate from the C scanner and does not write to
either sist2 database.

## What it does

- Queries the existing SQLite FTS5 search index.
- Resolves each hit to its original sist2 document row.
- Reads extracted text from the original `document.json_data` record.
- Sends retrieved evidence to a local OpenAI-compatible model endpoint.
- Returns the answer plus source paths and evidence classification.
- Makes no cloud calls. The default model endpoint is loopback only.

## What it does not do yet

- It is not yet wired into the native Mongoose server or Vue UI.
- It does not download or manage a model.
- It currently supports one source index per process.
- It does not yet do vector retrieval, OCR, image understanding, audio/video
  transcription, CAD/3D parsing, or archive-specific reasoning.
- The current API is a development bridge, not a production security boundary.

## Requirements

- Python 3.10+
- A sist2 source SQLite index (`*.sist2`)
- The corresponding SQLite search index created with `sist2 sqlite-index`
- A local OpenAI-compatible inference server, such as llama.cpp server

## Start

Example paths are placeholders; use the actual paths on your machine:

```powershell
python .\ai\sist2_ai_server.py `
  --source-db "D:\indexes\documents.sist2" `
  --search-db "D:\indexes\documents_fts.sqlite" `
  --model-url "http://127.0.0.1:8080" `
  --model "local-model"
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Chat:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8765/chat `
  -ContentType "application/json" `
  -Body (@{ question = "Where are the project requirements documented?"; limit = 6 } | ConvertTo-Json)
```

## Design notes

sist2's FTS5 table is contentless. Search hits are joined to
`document_index`, and the document's extracted text is fetched from the original
index database. This avoids assuming that FTS5 stores the authoritative text.

The source reference includes the full file path, the sist2 document ID, MIME
type, and whether the evidence is extracted text or metadata only. The model is
instructed to cite `[S1]`, `[S2]`, etc. and to say when the evidence is
insufficient.

## Next integration steps

1. Add managed lifecycle to `sist2 web` so the worker starts/stops with sist2.
2. Add authenticated `/ai/status` and `/ai/chat` routes to `src/web/serve.c`.
3. Add a Vue chat view and source-opening links.
4. Reuse the existing embedding tables for hybrid retrieval.
5. Add a separate, versioned AI metadata store for summaries and incremental
   enrichment.
6. Package a local model preset suitable for 8 GB VRAM and 16 GB system RAM.

## Attribution and licensing

This is an overlay/prototype intended to be developed against the upstream
sist2 source. Before publishing a combined fork, preserve upstream copyright
notices and comply with the exact license and attribution terms in the upstream
repository. Clearly document which files are upstream and which changes are
your contributions.

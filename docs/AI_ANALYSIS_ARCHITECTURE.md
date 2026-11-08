# AI Analysis Architecture

This document records the agreed product behavior for the AI layer in this fork.

## Product principle

sist2 remains the indexing, metadata extraction, persistence, and primary search engine. The AI layer is an additional understanding and question-answering layer built on top of a completed sist2 index.

The user-facing workflow should remain familiar to sist2: create an index, save it, open it later, and return to it. The AI assistant should be integrated into the existing sist2 web experience where practical. Internally, keep the AI engine modular so it can be maintained independently.

## One-time analysis workflow

For each user-selected source path:

1. The user explicitly starts a scan/index operation. There is no automatic folder watching or background re-indexing in the initial release.
2. sist2 inventories files, extracts supported metadata and text, and creates its normal persisted index/search artifacts.
3. OCR must be enabled during the scan when image text is required. sist2 already documents Tesseract OCR support for image files with `--ocr-images` and `--ocr-lang <lang>`, and for ebook/PDF-like formats with `--ocr-ebooks`.
4. After the sist2 index is complete, run the AI analysis once against the persisted sist2 outputs. Build and save reusable analysis artifacts: searchable knowledge, relationships/context, retrieval structures, and provenance linking every fact back to its indexed source and path.
5. Mark the analysis as ready. Later questions query the saved sist2 index and saved AI analysis; they must not trigger a full source scan or rebuild the analysis.

Each analyzed source path has its own independent, persistent analysis that can be reopened later. A new path creates a new analysis.

## Knowledge included in the analysis

- File and folder inventory: names, extensions, paths, sizes, timestamps, and available sist2 metadata.
- Extracted text from supported documents and text-bearing formats.
- OCR text extracted from images and supported scanned-document formats when OCR was enabled during scanning.
- Structural context: folder hierarchy, parent/child relationships where represented by sist2 (including archive entries), nearby files, and project context.
- Metadata-only records for formats whose internals are not supported or intentionally not parsed.

For unsupported specialist formats such as CAD and 3D files, do not claim to inspect or render their internals. Use available names, paths, extensions, metadata, and surrounding project/document context. Clearly label conclusions about their purpose as inference, not extracted content.

Preserve provenance and evidence type. Distinguish extracted document text, OCR text, file metadata, and contextual inference. Never fabricate file contents or citations.

## Persistence and update behavior

- Do not copy original user files into the AI data store.
- Reuse sist2's persisted index/search data rather than creating a duplicate general-purpose file index.
- Store only the additional AI analysis artifacts needed for efficient retrieval and answers, with references to the original sist2 records and paths.
- Do not rescan, re-OCR, or rebuild analysis for each chat question.
- If source data changes, the user explicitly chooses to run the relevant sist2 scan/update and AI analysis again. Automatic updates are out of scope for the initial release.
- Keep separate analyses isolated and reopenable.

## Chat behavior

After analysis is complete, provide a chat assistant in the sist2 web interface. It answers using retrieved evidence from the saved analysis and sist2 index, cites source paths, and states when evidence is insufficient. Chat requests must not initiate a full scan or one-time analysis.

## Initial implementation boundary

The current AI server is a prototype/read-only bridge, not the completed workflow. It currently retrieves a small set of FTS results at question time and calls a local OpenAI-compatible model endpoint. It does not yet implement the persistent one-time AI analysis pipeline, OCR orchestration, complete folder context, or native sist2 UI integration. These are implementation tasks, not existing capabilities.

# OCR setup on Windows

This fork relies on sist2's existing OCR extraction during the initial scan. The AI analysis stage consumes the text persisted by sist2; it must not reopen source PDFs or images for OCR on every chat question.

## Important behavior

- Searchable PDFs: sist2 extracts their text normally.
- Scanned/image-only PDFs: enable ebook OCR with `--ocr-ebooks`.
- Standalone images: enable image OCR with `--ocr-images`.
- Select Tesseract language data with `--ocr-lang`. For English and Arabic, the language code is `eng+ara`.
- OCR happens during the user-requested scan. If an existing index was created without OCR, missing OCR text will not appear automatically; the user must explicitly run a new scan/update with OCR enabled, then rebuild the AI analysis.

## Example

Adjust the executable path, source path, and output path:

```powershell
& "C:\sist2\sist2.exe.exe" scan `
  --ocr-images `
  --ocr-ebooks `
  --ocr-lang "eng+ara" `
  --name "My documents" `
  --output "C:\sist2\analyses\my-documents.sist2" `
  "E:\Documents"
```

After the scan completes, create/update the SQLite search database:

```powershell
& "C:\sist2\sist2.exe.exe" sqlite-index `
  "C:\sist2\analyses\my-documents.sist2" `
  --search-index "C:\sist2\analyses\my-documents-search.sist2"
```

Then run the one-time AI analysis stage against those persisted databases. Chat requests must never start these commands automatically.

## Verify language availability

The OCR language data must be available to the Tesseract build used by sist2. If OCR reports a missing language, use the language code(s) actually installed. Do not assume `ara` is available merely because the option accepts it.

For a first test, scan a small folder containing a normal text PDF, a scanned/image-only PDF, and a standalone image containing readable text. Inspect the sist2 index and confirm the `content` field contains the expected text before running AI analysis.

## Scope

This documents OCR scan configuration only. It does not yet implement the persistent AI analysis pipeline or native chat UI.
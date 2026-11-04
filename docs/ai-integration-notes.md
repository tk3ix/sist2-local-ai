# Engineering integration notes

## Verified source facts

- Upstream source inspected: sist2 4.2.3.
- Native server routes are dispatched in `src/web/serve.c` by `ev_router`.
- The source database has a `document` table with JSON in `json_data`.
- `database_get_content()` reads `json_data ->> 'content'`.
- The FTS database has `document_index` and a contentless FTS5 `search` table.
- FTS document IDs are encoded as `(index_id << 32) | document.id`.
- `database_fts_get_document()` already demonstrates the same resolution path
  from FTS metadata back to the source index and extracted content.

## Proposed native integration

Do not expose the Python port directly to remote clients. The native web server
should own the public API and proxy requests to a loopback-only worker, or call
a library boundary with equivalent lifecycle management. Reuse sist2's existing
authentication checks before forwarding AI requests.

Suggested endpoints:
- `GET /ai/status`
- `POST /ai/chat`

The Vue application should call same-origin endpoints. Source records should
link to the existing document-detail route and/or file route, rather than
constructing arbitrary filesystem URLs.

## Important implementation caveats

- The bridge currently assumes one source index per process. Multi-index support
  needs a mapping from each `index_id` to its source database path.
- Verify the exact SQLite search-index filename from the user's CLI settings;
  do not infer it from the source database filename.
- FTS5 query parsing differs from general web search. This prototype tokenizes
  plain words and ANDs them; later work should support phrase, OR, filters,
  and fallback retrieval.
- The bridge limits retrieved text to 18,000 characters per source to keep
  prompts bounded. This is a temporary prototype policy, not a final chunking
  strategy.
- Model output is not trusted. File paths and metadata must come from SQLite,
  never from model-generated text.
- Add request authentication, rate limits, cancellation, structured logs,
  and explicit model lifecycle management before shipping.

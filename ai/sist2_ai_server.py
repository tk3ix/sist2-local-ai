#!/usr/bin/env python3
"""Read-only local RAG bridge for a sist2 SQLite index.

This is an isolated first vertical slice. It does not modify sist2 databases.
Run it with the source index database and its SQLite search database.
The LLM endpoint must be a local OpenAI-compatible server (for example llama.cpp).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MAX_BODY = 128 * 1024
MAX_QUERY = 1200
DEFAULT_LIMIT = 6
MAX_LIMIT = 12


def open_db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def load_descriptor(source_db: sqlite3.Connection) -> dict[str, Any]:
    row = source_db.execute(
        "SELECT id, root, name FROM descriptor ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("The supplied file is not a sist2 index database (descriptor missing).")
    return dict(row)


def safe_fts_query(user_query: str) -> str:
    # Treat user text as words, not FTS5 operators or SQL syntax.
    terms = re.findall(r"[\w.-]+", user_query, flags=re.UNICODE)
    if not terms:
        return ""
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in terms[:24])


def retrieve(source_db: sqlite3.Connection, search_db: sqlite3.Connection,
             query: str, limit: int) -> list[dict[str, Any]]:
    fts_query = safe_fts_query(query)
    if not fts_query:
        return []

    # sist2 encodes the index id in the high 32 bits and the source document id
    # in the low 32 bits. The FTS5 table is contentless; authoritative content
    # is fetched from the source index's document.json_data.
    rows = search_db.execute(
        """
        SELECT s.rowid AS sid, bm25(search) AS score,
               d.index_id, d.path, d.name, d.mime, d.size, d.mtime, d.json_data
        FROM search AS s
        JOIN document_index AS d ON d.id = s.rowid
        WHERE search MATCH ?
        ORDER BY score
        LIMIT ?
        """,
        (fts_query, limit),
    ).fetchall()

    descriptor = load_descriptor(source_db)
    expected_index_id = int(descriptor["id"])
    results: list[dict[str, Any]] = []

    for row in rows:
        if int(row["index_id"]) != expected_index_id:
            # First version deliberately supports one source index per process.
            continue
        doc_id = int(row["sid"]) & 0xFFFFFFFF
        source_row = source_db.execute(
            "SELECT json_data FROM document WHERE id = ?", (doc_id,)
        ).fetchone()
        if source_row is None or not source_row["json_data"]:
            continue

        try:
            metadata = json.loads(source_row["json_data"])
        except (TypeError, json.JSONDecodeError):
            metadata = {}

        content = metadata.get("content") or ""
        rel_path = metadata.get("path") or row["path"] or ""
        root = str(descriptor["root"] or "")
        full_path = str(Path(root) / rel_path) if root else str(rel_path)

        results.append({
            "document_id": doc_id,
            "sid": int(row["sid"]),
            "name": metadata.get("name") or row["name"] or Path(rel_path).name,
            "path": full_path,
            "relative_path": rel_path,
            "mime": row["mime"],
            "size": int(row["size"] or 0),
            "mtime": int(row["mtime"] or 0),
            "content": content[:18000],
            "score": float(row["score"]),
            "evidence_type": "extracted_text" if content else "metadata_only",
        })
    return results


def make_prompt(question: str, sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    evidence = []
    for i, item in enumerate(sources, 1):
        body = item["content"] if item["content"] else (
            "No extracted text is available for this item. Use only the metadata below."
        )
        evidence.append(
            f"[S{i}] File: {item['name']}\n"
            f"Path: {item['path']}\n"
            f"MIME: {item.get('mime') or 'unknown'}\n"
            f"Evidence type: {item['evidence_type']}\n"
            f"Content:\n{body}"
        )
    context = "\n\n".join(evidence) if evidence else "No matching indexed sources were found."
    system = (
        "You are the local assistant inside sist2. Answer only from the supplied evidence. "
        "Do not invent file contents. If evidence is insufficient, say so clearly. "
        "Cite every factual statement with [S1], [S2], etc. Distinguish extracted facts "
        "from metadata-only facts and from any inference. Never claim to have read a file "
        "when only its metadata is available. Reply in the user's language."
    )
    user = f"Question: {question}\n\nIndexed evidence:\n{context}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def ask_local_llm(base_url: str, model: str, messages: list[dict[str, str]],
                  api_key: str = "", timeout: int = 180) -> str:
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = json.dumps({
        "model": model or "local-model",
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Cannot reach the local model server at {url}: {exc}. "
            "Start your local OpenAI-compatible model server first."
        ) from exc
    try:
        return result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("The local model server returned an unexpected response.") from exc


class App:
    def __init__(self, source_db_path: str, search_db_path: str,
                 model_url: str, model_name: str, api_key: str):
        self.source_db_path = source_db_path
        self.search_db_path = search_db_path
        self.model_url = model_url
        self.model_name = model_name
        self.api_key = api_key

    def status(self) -> dict[str, Any]:
        with open_db(self.source_db_path) as source:
            descriptor = load_descriptor(source)
        with open_db(self.search_db_path) as search:
            fts = search.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='search'"
            ).fetchone()[0] == 1
        return {
            "ok": True,
            "mode": "read_only_local_rag",
            "source_index": descriptor["name"],
            "source_root": descriptor["root"],
            "search_database_ready": fts,
            "model_endpoint": self.model_url,
            "model_name": self.model_name,
        }

    def chat(self, question: str, limit: int) -> dict[str, Any]:
        if not question.strip():
            raise ValueError("question must not be empty")
        if len(question) > MAX_QUERY:
            raise ValueError(f"question is too long (max {MAX_QUERY} characters)")
        with open_db(self.source_db_path) as source, open_db(self.search_db_path) as search:
            sources = retrieve(source, search, question, limit)
        if not sources:
            return {
                "answer": "لم أعثر على نتائج مطابقة في فهرس sist2 الحالي. جرّب صياغة أخرى أو تأكد من تحديث فهرس SQLite.",
                "sources": [],
                "retrieval_count": 0,
            }
        answer = ask_local_llm(
            self.model_url, self.model_name, make_prompt(question, sources), self.api_key
        )
        public_sources = [
            {k: v for k, v in item.items() if k not in ("content", "score")}
            for item in sources
        ]
        return {"answer": answer, "sources": public_sources, "retrieval_count": len(sources)}


def create_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "sist2-local-ai/0.1"

        def _reply(self, status: int, body: dict[str, Any]):
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path != "/health":
                return self._reply(404, {"error": "not_found"})
            try:
                self._reply(200, app.status())
            except Exception as exc:
                self._reply(503, {"ok": False, "error": str(exc)})

        def do_POST(self):
            if self.path != "/chat":
                return self._reply(404, {"error": "not_found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > MAX_BODY:
                    return self._reply(413, {"error": "invalid_request_size"})
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                question = str(payload.get("question", ""))
                limit = max(1, min(int(payload.get("limit", DEFAULT_LIMIT)), MAX_LIMIT))
                self._reply(200, app.chat(question, limit))
            except ValueError as exc:
                self._reply(400, {"error": str(exc)})
            except Exception as exc:
                self._reply(502, {"error": str(exc)})

        def log_message(self, fmt, *args):
            print("[sist2-ai] " + (fmt % args))

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Local, read-only AI bridge for sist2 SQLite indexes")
    parser.add_argument("--source-db", required=True, help="Path to the original *.sist2 SQLite index")
    parser.add_argument("--search-db", required=True, help="Path to the SQLite search index")
    parser.add_argument("--model-url", default="http://127.0.0.1:8080",
                        help="Local OpenAI-compatible model server base URL")
    parser.add_argument("--model", default="local-model")
    parser.add_argument("--api-key", default=os.environ.get("SIST2_AI_API_KEY", ""))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    app = App(args.source_db, args.search_db, args.model_url, args.model, args.api_key)
    print(json.dumps(app.status(), ensure_ascii=False, indent=2))
    server = ThreadingHTTPServer((args.host, args.port), create_handler(app))
    print(f"[sist2-ai] listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

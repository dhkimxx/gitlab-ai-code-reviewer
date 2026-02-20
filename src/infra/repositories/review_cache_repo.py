from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from typing import List

from src.shared.types import GitDiffChange, LLMReviewResult


logger = logging.getLogger(__name__)


class ReviewCacheRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        directory = os.path.dirname(self._db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_cache (
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                diff_hash TEXT NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (provider, model, diff_hash)
            )
            """
        )
        return conn

    @staticmethod
    def _build_diff_hash(changes: List[GitDiffChange]) -> str:
        hasher = hashlib.sha256()

        for change in changes:
            old_path = change.get("old_path") or ""
            new_path = change.get("new_path") or ""
            flags = "".join(
                [
                    "N" if change.get("new_file") else "-",
                    "D" if change.get("deleted_file") else "-",
                    "R" if change.get("renamed_file") else "-",
                ]
            )
            diff_text = change.get("diff", "") or ""

            segment = "\n".join(
                [
                    f"old_path:{old_path}",
                    f"new_path:{new_path}",
                    f"flags:{flags}",
                    "diff:",
                    diff_text,
                    "---",
                ]
            )
            hasher.update(segment.encode("utf-8"))

        return hasher.hexdigest()

    def get(
        self,
        *,
        provider: str,
        model: str,
        changes: List[GitDiffChange],
    ) -> LLMReviewResult | None:
        diff_hash = self._build_diff_hash(changes)
        conn: sqlite3.Connection | None = None
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT result_json FROM review_cache WHERE provider = ? AND model = ? AND diff_hash = ?",
                (provider, model, diff_hash),
            )
            row = cursor.fetchone()
            if not row:
                return None
            payload = row[0]
            data = json.loads(payload)
            return data  # type: ignore[return-value]
        except Exception:
            logger.exception("Failed to read review cache; skipping cache usage")
            return None
        finally:
            if conn is not None:
                conn.close()

    def put(
        self,
        *,
        provider: str,
        model: str,
        changes: List[GitDiffChange],
        result: LLMReviewResult,
    ) -> None:
        diff_hash = self._build_diff_hash(changes)
        conn: sqlite3.Connection | None = None
        try:
            conn = self._get_connection()
            payload = json.dumps(result)
            conn.execute(
                """
                INSERT INTO review_cache (provider, model, diff_hash, result_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, model, diff_hash) DO UPDATE SET
                    result_json = excluded.result_json
                """,
                (provider, model, diff_hash, payload),
            )
            conn.commit()
        except Exception:
            logger.exception("Failed to write review cache; ignoring cache persistence error")
        finally:
            if conn is not None:
                conn.close()

from __future__ import annotations

import logging
import os
import sqlite3


logger = logging.getLogger(__name__)


class RefactorSuggestionStateRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        directory = os.path.dirname(self._db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS refactor_suggestion_review_state (
                project_id INTEGER NOT NULL,
                merge_request_iid INTEGER NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (project_id, merge_request_iid)
            )
            """
        )
        return conn

    def try_claim(self, project_id: int, merge_request_iid: int) -> bool:
        conn: sqlite3.Connection | None = None
        try:
            conn = self._get_connection()
            conn.execute(
                """
                INSERT INTO refactor_suggestion_review_state (project_id, merge_request_iid, status, updated_at)
                VALUES (?, ?, 'queued', datetime('now'))
                """,
                (project_id, merge_request_iid),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception:
            logger.exception("Failed to claim refactor suggestion review slot")
            return False
        finally:
            if conn is not None:
                conn.close()

    def mark_completed(self, project_id: int, merge_request_iid: int) -> None:
        conn: sqlite3.Connection | None = None
        try:
            conn = self._get_connection()
            conn.execute(
                """
                UPDATE refactor_suggestion_review_state
                SET status = 'completed', updated_at = datetime('now')
                WHERE project_id = ? AND merge_request_iid = ?
                """,
                (project_id, merge_request_iid),
            )
            conn.commit()
        except Exception:
            logger.exception("Failed to mark refactor suggestion review as completed")
        finally:
            if conn is not None:
                conn.close()

    def release_claim(self, project_id: int, merge_request_iid: int) -> None:
        conn: sqlite3.Connection | None = None
        try:
            conn = self._get_connection()
            conn.execute(
                """
                DELETE FROM refactor_suggestion_review_state
                WHERE project_id = ? AND merge_request_iid = ? AND status = 'queued'
                """,
                (project_id, merge_request_iid),
            )
            conn.commit()
        except Exception:
            logger.exception("Failed to release refactor suggestion review claim")
        finally:
            if conn is not None:
                conn.close()

    def get_status(self, project_id: int, merge_request_iid: int) -> str | None:
        conn: sqlite3.Connection | None = None
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                SELECT status
                FROM refactor_suggestion_review_state
                WHERE project_id = ? AND merge_request_iid = ?
                """,
                (project_id, merge_request_iid),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return str(row[0])
        except Exception:
            logger.exception("Failed to read refactor suggestion review status")
            return None
        finally:
            if conn is not None:
                conn.close()

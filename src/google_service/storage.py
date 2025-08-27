import sqlite3
import json
import os
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()


logger = get_logger("google_service.storage")

DB_PATH = os.getenv("DB_PATH", "./storage.db")


class KeyValueStore:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)"
        )
        self.conn.commit()
        logger.info("Database initialized.")

    def set(self, key: str, value: dict):
        """Set a key-value pair in the database."""
        json_value = json.dumps(value, default=str)
        self.conn.execute(
            "REPLACE INTO kv (key, value) VALUES (?, ?)", (key, json_value)
        )
        self.conn.commit()
        logger.info("Key-value pair saved successfully.", extra={"key": key})

    def get(self, key: str) -> dict | None:
        """Get a value from the database by key."""
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM kv WHERE key=?", (key,))
        row = cur.fetchone()
        if row:
            logger.info("Key-value pair found.", extra={"key": key})
            return json.loads(row[0])
        logger.info("Key-value pair not found.", extra={"key": key})
        return None

    def delete(self, key: str):
        """Delete a key-value pair from the database by key."""
        self.conn.execute("DELETE FROM kv WHERE key=?", (key,))
        self.conn.commit()
        logger.info("Key-value pair deleted successfully.", extra={"key": key})

    def list_keys(self, prefix: str = "") -> list:
        """List all keys in the database that start with the given prefix."""
        cur = self.conn.cursor()
        cur.execute("SELECT key FROM kv WHERE key LIKE ?", (f"{prefix}%",))
        keys = [row[0] for row in cur.fetchall()]
        logger.info("Keys listed successfully.", extra={"keys": keys})
        return keys

import sqlite3
from datetime import datetime, timedelta

import pytest


def _setup_db(db_path: str):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS thunderstorm_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_timestamp TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _set_logged_in_session(client):
    with client.session_transaction() as sess:
        sess["logged_in"] = True


def test_next_storm_prediction_endpoint_filters_stale_predictions(tmp_path, monkeypatch):
    # Import inside test to ensure app/db are initialized
    import web_app

    # Point DB to a temp sqlite file and monkeypatch the connection used by the endpoint
    test_db_path = str(tmp_path / "test_weather.db")
    conn = _setup_db(test_db_path)

    def get_conn_patch(*args, **kwargs):
        # Return a context manager compatible connection
        class Ctx:
            def __enter__(self):
                return conn
            def __exit__(self, exc_type, exc, tb):
                pass
        return Ctx()

    monkeypatch.setattr(web_app.db, "get_connection", get_conn_patch)

    client = web_app.app.test_client()

    # Case 0: Empty table -> 404
    _set_logged_in_session(client)
    resp = client.get("/api/next_storm_prediction")
    assert resp.status_code == 404

    c = conn.cursor()

    # Case 1: Past prediction -> 404
    c.execute("DELETE FROM thunderstorm_predictions")
    conn.commit()
    past_pred = (datetime.now() - timedelta(minutes=10)).isoformat()
    c.execute(
        "INSERT INTO thunderstorm_predictions (prediction_timestamp, confidence, created_at) VALUES (?, ?, ?)",
        (past_pred, 0.6, datetime.now().isoformat()),
    )
    conn.commit()
    _set_logged_in_session(client)
    resp = client.get("/api/next_storm_prediction")
    assert resp.status_code == 404

    # Case 2: Future prediction but created 13h ago -> 404
    c.execute("DELETE FROM thunderstorm_predictions")
    conn.commit()
    future_pred = (datetime.now() + timedelta(minutes=30)).isoformat()
    old_created = (datetime.now() - timedelta(hours=13)).isoformat()
    c.execute(
        "INSERT INTO thunderstorm_predictions (prediction_timestamp, confidence, created_at) VALUES (?, ?, ?)",
        (future_pred, 0.7, old_created),
    )
    conn.commit()
    _set_logged_in_session(client)
    resp = client.get("/api/next_storm_prediction")
    assert resp.status_code == 404

    # Case 3: Valid future prediction created now -> 200
    c.execute("DELETE FROM thunderstorm_predictions")
    conn.commit()
    valid_future = (datetime.now() + timedelta(minutes=45)).isoformat()
    c.execute(
        "INSERT INTO thunderstorm_predictions (prediction_timestamp, confidence, created_at) VALUES (?, ?, ?)",
        (valid_future, 0.8, datetime.now().isoformat()),
    )
    conn.commit()
    _set_logged_in_session(client)
    resp = client.get("/api/next_storm_prediction")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["prediction_timestamp"] == valid_future
    assert data["confidence"] == 0.8



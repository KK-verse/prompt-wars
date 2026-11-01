"""Local SQLite persistence for Planora AI."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = Path("/tmp/planora.db") if os.getenv("VERCEL") else PROJECT_ROOT / "data" / "planora.db"
DB_PATH = Path(os.getenv("PLANORA_DB_PATH", DEFAULT_DB_PATH))


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                event_type TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                event_date TEXT,
                duration_days INTEGER NOT NULL DEFAULT 1,
                guest_count INTEGER NOT NULL DEFAULT 0,
                total_budget REAL NOT NULL DEFAULT 0,
                theme TEXT NOT NULL DEFAULT '',
                food_preferences TEXT NOT NULL DEFAULT '',
                accommodation_required INTEGER NOT NULL DEFAULT 0,
                accommodation_count INTEGER NOT NULL DEFAULT 0,
                decoration_preferences TEXT NOT NULL DEFAULT '',
                entertainment_requirements TEXT NOT NULL DEFAULT '',
                special_instructions TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planning',
                ideas_json TEXT NOT NULL DEFAULT '[]',
                is_demo INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                estimated_cost REAL NOT NULL DEFAULT 0,
                actual_cost REAL NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT 'not_started',
                notes TEXT NOT NULL DEFAULT '',
                UNIQUE(event_id, category)
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                deadline TEXT,
                priority TEXT NOT NULL DEFAULT 'medium',
                status TEXT NOT NULL DEFAULT 'pending',
                dependencies TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS vendors (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                contact TEXT NOT NULL DEFAULT '',
                price_min REAL NOT NULL DEFAULT 0,
                price_max REAL NOT NULL DEFAULT 0,
                rating REAL,
                source TEXT NOT NULL DEFAULT 'user-entered',
                verification_status TEXT NOT NULL DEFAULT 'user-entered',
                services TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                booking_status TEXT NOT NULL DEFAULT 'not_contacted',
                agreed_price REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS guests (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                contact TEXT NOT NULL DEFAULT '',
                group_category TEXT NOT NULL DEFAULT 'Friends',
                rsvp_status TEXT NOT NULL DEFAULT 'pending',
                meal_preference TEXT NOT NULL DEFAULT '',
                dietary_restrictions TEXT NOT NULL DEFAULT '',
                accommodation_required INTEGER NOT NULL DEFAULT 0,
                table_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_data TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS event_schedules (
                event_id TEXT PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_event_deadline ON tasks(event_id, deadline);
            CREATE INDEX IF NOT EXISTS idx_guests_event_rsvp ON guests(event_id, rsvp_status);
            CREATE INDEX IF NOT EXISTS idx_vendors_event_category ON vendors(event_id, category);
            CREATE INDEX IF NOT EXISTS idx_messages_event_created ON messages(event_id, created_at);
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if count == 0:
            _seed_demo_workspace(conn)


def _seed_demo_workspace(conn: sqlite3.Connection) -> None:
    event_id = make_id("evt")
    now = utc_now()
    event_date = date.today() + timedelta(days=125)
    conn.execute(
        """INSERT INTO events (
            id, title, event_type, location, event_date, duration_days,
            guest_count, total_budget, theme, food_preferences,
            accommodation_required, accommodation_count, decoration_preferences,
            entertainment_requirements, special_instructions, status, is_demo,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id,
            "Aarav & Mira’s Wedding",
            "Wedding",
            "Jaipur, Rajasthan",
            event_date.isoformat(),
            2,
            300,
            1_500_000,
            "Royal Rajasthani",
            "Vegetarian",
            1,
            100,
            "Marigold, brass, and warm candlelight",
            "Live folk music and a quiet acoustic set",
            "Demo workspace with planning estimates, not vendor quotations.",
            "planning",
            1,
            now,
            now,
        ),
    )

    allocations = [
        ("Venue", 0.18),
        ("Catering", 0.27),
        ("Decoration", 0.13),
        ("Photography", 0.09),
        ("Videography", 0.04),
        ("Entertainment", 0.05),
        ("Transportation", 0.04),
        ("Accommodation", 0.08),
        ("Invitations", 0.02),
        ("Contingency", 0.10),
    ]
    for category, share in allocations:
        actual = 0
        status = "not_started"
        if category == "Venue":
            actual, status = 85_000, "deposit_paid"
        elif category == "Catering":
            actual, status = 25_000, "deposit_paid"
        conn.execute(
            """INSERT INTO expenses
            (id, event_id, category, estimated_cost, actual_cost, payment_status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                make_id("exp"),
                event_id,
                category,
                round(1_500_000 * share),
                actual,
                status,
                "Planning estimate; confirm with a vendor before booking.",
            ),
        )

    task_seed = [
        ("Confirm venue shortlist", "Compare capacity, access, and weather backup.", 105, "high", "completed"),
        ("Approve catering direction", "Confirm vegetarian menu and tasting dates.", 82, "high", "pending"),
        ("Book photography team", "Shortlist photo and video coverage for both days.", 70, "high", "pending"),
        ("Send save-the-dates", "Prepare guest communication and accommodation details.", 55, "medium", "pending"),
        ("Collect final RSVPs", "Follow up with guests who have not replied.", 25, "medium", "pending"),
        ("Run vendor coordination call", "Confirm arrival windows and day-of contacts.", 7, "high", "pending"),
        ("Review the final run sheet", "Share the event-day schedule with the team.", 2, "high", "pending"),
    ]
    for title, description, days_before, priority, status in task_seed:
        conn.execute(
            """INSERT INTO tasks
            (id, event_id, title, description, deadline, priority, status, dependencies, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?)""",
            (
                make_id("task"),
                event_id,
                title,
                description,
                (event_date - timedelta(days=days_before)).isoformat(),
                priority,
                status,
                now,
            ),
        )


def _decode_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def get_event(event_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if not row:
            return None
        event = dict(row)
        event["is_demo"] = bool(event["is_demo"])
        event["accommodation_required"] = bool(event["accommodation_required"])
        event["ideas"] = _decode_json(event.pop("ideas_json"), [])
        event["expenses"] = [
            dict(item)
            for item in conn.execute(
                "SELECT * FROM expenses WHERE event_id = ? ORDER BY rowid", (event_id,)
            ).fetchall()
        ]
        event["tasks"] = [
            _task_dict(item)
            for item in conn.execute(
                "SELECT * FROM tasks WHERE event_id = ? ORDER BY deadline, rowid", (event_id,)
            ).fetchall()
        ]
        event["guests"] = [
            _guest_dict(item)
            for item in conn.execute(
                "SELECT * FROM guests WHERE event_id = ? ORDER BY name COLLATE NOCASE", (event_id,)
            ).fetchall()
        ]
        event["vendors"] = [
            dict(item)
            for item in conn.execute(
                "SELECT * FROM vendors WHERE event_id = ? ORDER BY name COLLATE NOCASE", (event_id,)
            ).fetchall()
        ]
        schedule = conn.execute(
            "SELECT data_json FROM event_schedules WHERE event_id = ?", (event_id,)
        ).fetchone()
        event["schedule"] = _decode_json(schedule[0], []) if schedule else []
        event["messages"] = [
            _message_dict(item)
            for item in conn.execute(
                "SELECT * FROM messages WHERE event_id = ? ORDER BY created_at DESC LIMIT 30",
                (event_id,),
            ).fetchall()[::-1]
        ]
        return event


def _task_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["dependencies"] = _decode_json(item["dependencies"], [])
    return item


def _guest_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["accommodation_required"] = bool(item["accommodation_required"])
    return item


def _message_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["tool_data"] = _decode_json(item["tool_data"], {})
    return item


def list_events() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT e.*,
                (SELECT COUNT(*) FROM tasks t WHERE t.event_id=e.id) AS task_count,
                (SELECT COUNT(*) FROM tasks t WHERE t.event_id=e.id AND t.status='completed') AS done_count,
                (SELECT COALESCE(SUM(actual_cost),0) FROM expenses x WHERE x.event_id=e.id) AS actual_spend
            FROM events e ORDER BY e.is_demo DESC, e.event_date IS NULL, e.event_date"""
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["is_demo"] = bool(item["is_demo"])
            item["progress_pct"] = round(item["done_count"] * 100 / item["task_count"]) if item["task_count"] else 0
            result.append(item)
        return result


def add_message(event_id: str, role: str, content: str, tool_data: dict[str, Any] | None = None) -> dict[str, Any]:
    item = {
        "id": make_id("msg"),
        "event_id": event_id,
        "role": role,
        "content": content,
        "tool_data": tool_data or {},
        "created_at": utc_now(),
    }
    with connection() as conn:
        conn.execute(
            "INSERT INTO messages (id,event_id,role,content,tool_data,created_at) VALUES (?,?,?,?,?,?)",
            (item["id"], event_id, role, content, json.dumps(item["tool_data"]), item["created_at"]),
        )
    return item


def get_messages(event_id: str, limit: int = 30) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE event_id = ? ORDER BY created_at DESC LIMIT ?",
            (event_id, limit),
        ).fetchall()
        return [_message_dict(row) for row in rows[::-1]]


def dashboard_payload(event_id: str | None = None) -> dict[str, Any]:
    events = list_events()
    selected_id = event_id or (events[0]["id"] if events else None)
    event = get_event(selected_id) if selected_id else None
    if not event:
        return {"events": events, "event": None, "metrics": {"event_count": len(events)}}
    planned = sum(float(item["estimated_cost"]) for item in event["expenses"])
    actual = sum(float(item["actual_cost"]) for item in event["expenses"])
    pending = [task for task in event["tasks"] if task["status"] != "completed"]
    today = date.today().isoformat()
    overdue = sum(1 for task in pending if task.get("deadline") and task["deadline"] < today)
    event["progress_pct"] = round((len(event["tasks"]) - len(pending)) * 100 / len(event["tasks"])) if event["tasks"] else 0
    return {
        "events": events,
        "event": event,
        "metrics": {
            "event_count": len(events),
            "planned_budget": float(event["total_budget"]),
            "allocated": planned,
            "actual_spend": actual,
            "remaining_budget": float(event["total_budget"]) - actual,
            "pending_tasks": len(pending),
            "overdue_tasks": overdue,
            "guest_count": int(event["guest_count"]),
            "progress_pct": event["progress_pct"],
        },
    }

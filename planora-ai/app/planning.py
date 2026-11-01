"""Deterministic planning helpers shared by REST endpoints and ADK tools."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.database import connection, make_id, utc_now

BUDGET_SHARES = {
    "Venue": 0.18,
    "Catering": 0.27,
    "Decoration": 0.13,
    "Photography": 0.09,
    "Videography": 0.04,
    "Entertainment": 0.05,
    "Transportation": 0.04,
    "Accommodation": 0.08,
    "Invitations": 0.02,
    "Contingency": 0.10,
}

EVENT_TYPES = (
    "Wedding",
    "Engagement",
    "Birthday",
    "Anniversary",
    "College festival",
    "Hackathon",
    "Corporate event",
    "Community gathering",
    "Cultural celebration",
    "Religious celebration",
    "Custom event",
)


def money_from_text(text: str) -> float | None:
    match = re.search(
        r"(?:₹|rs\.?\s*|inr\s*)\s*([\d,]+(?:\.\d+)?)\s*(crore|cr|lakh|lac|lakhs|l|thousand|k)?\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"(?:budget|spend|cost|worth)\s*(?:of|is|around|about|at|to|:)?\s*([\d,]+(?:\.\d+)?)\s*(crore|cr|lakh|lac|lakhs|l|thousand|k)?\b",
            text,
            re.IGNORECASE,
        )
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "").lower()
    if unit in {"crore", "cr"}:
        amount *= 10_000_000
    elif unit in {"lakh", "lakhs", "lac", "l"}:
        amount *= 100_000
    elif unit in {"thousand", "k"}:
        amount *= 1_000
    return amount


def parse_date(text: str) -> str | None:
    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(1)).isoformat()
        except ValueError:
            return None
    patterns = (
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %Y",
        "%b %Y",
    )
    candidates = re.findall(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,)?\s+20\d{2}|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+20\d{2}|\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+20\d{2}",
        text,
        re.IGNORECASE,
    )
    for candidate in candidates:
        cleaned = re.sub(r"\s+", " ", candidate.strip())
        for pattern in patterns:
            try:
                parsed = datetime.strptime(cleaned, pattern)
                if pattern in {"%B %Y", "%b %Y"}:
                    parsed = parsed.replace(day=1)
                return parsed.date().isoformat()
            except ValueError:
                pass
    return None


def extract_event_details(prompt: str) -> dict[str, Any]:
    text = prompt.strip()
    lower = text.lower()
    event_type = "Custom event"
    for candidate in EVENT_TYPES[:-1]:
        if candidate.lower() in lower or (candidate == "Birthday" and "birthday" in lower):
            event_type = candidate
            break
    if "corporate" in lower or "company event" in lower:
        event_type = "Corporate event"
    if "festival" in lower and "college" in lower:
        event_type = "College festival"
    if "cultural" in lower or "rajasthani" in lower:
        event_type = "Cultural celebration" if "wedding" not in lower else "Wedding"

    location = ""
    location_match = re.search(
        r"\bin\s+([A-Za-z][A-Za-z .'-]*?)(?=\s+(?:for|with|on|over|under|and|budget|theme|using)\b|[,.;]|$)",
        text,
        re.IGNORECASE,
    )
    if location_match:
        location = location_match.group(1).strip()

    guest_match = re.search(
        r"(?:for|with|around|about|approximately)?\s*([\d,]+)\s*(?:guests?|people|attendees|persons?)\b",
        text,
        re.IGNORECASE,
    )
    guests = int(guest_match.group(1).replace(",", "")) if guest_match else 0

    budget = money_from_text(text)
    duration_match = re.search(r"\b(\d+)\s*[- ]?day(?:s)?\b", text, re.IGNORECASE)
    duration = int(duration_match.group(1)) if duration_match else 1

    accommodation_match = re.search(
        r"accommodation\s+for\s+([\d,]+)\s*(?:guests?|people)?",
        text,
        re.IGNORECASE,
    )
    accommodation_count = int(accommodation_match.group(1).replace(",", "")) if accommodation_match else 0

    theme = ""
    theme_match = re.search(r"\btheme\s*(?:is|:|of)?\s*([^,.;]+)", text, re.IGNORECASE)
    if theme_match:
        theme = theme_match.group(1).strip()
    elif "royal rajasthani" in lower:
        theme = "Royal Rajasthani"

    food = ""
    for preference in ("vegetarian", "vegan", "halal", "kosher", "gluten-free", "non-vegetarian"):
        if preference in lower:
            food = preference.title()
            break

    date_value = parse_date(text)
    title = f"{event_type} in {location}" if location else event_type
    if event_type == "Wedding" and theme:
        title = f"{theme} Wedding" + (f" in {location}" if location else "")
    return {
        "title": title,
        "event_type": event_type,
        "location": location,
        "event_date": date_value,
        "duration_days": max(1, min(duration, 30)),
        "guest_count": guests,
        "total_budget": budget or 0,
        "theme": theme,
        "food_preferences": food,
        "accommodation_required": accommodation_count > 0,
        "accommodation_count": accommodation_count,
        "decoration_preferences": "",
        "entertainment_requirements": "",
        "special_instructions": text,
    }


def extract_updates(message: str, event: dict[str, Any]) -> dict[str, Any]:
    text = message.strip()
    lower = text.lower()
    updates: dict[str, Any] = {}

    guest_target = re.search(
        r"(?:guest count|guests?|attendees)\D{0,28}(?:from\s+[\d,]+\s+to\s+|to\s+)?([\d,]+)\s*(?:guests?|people|attendees)?",
        text,
        re.IGNORECASE,
    )
    if guest_target and any(word in lower for word in ("guest", "attendee", "people")):
        updates["guest_count"] = int(guest_target.group(1).replace(",", ""))
    elif re.search(r"\b(?:increase|reduce|change|make|set)\b.*\b(?:to|at)\s+[\d,]+\s+guests?", text, re.IGNORECASE):
        generic_guest = re.search(r"\b(?:to|at)\s+([\d,]+)\s+guests?", text, re.IGNORECASE)
        if generic_guest:
            updates["guest_count"] = int(generic_guest.group(1).replace(",", ""))

    change_by = re.search(
        r"\b(reduce|cut|lower|decrease|increase|raise|add)\b.{0,24}\bbudget\b.{0,18}\bby\b\s*(?:₹|rs\.?\s*)?([\d,]+(?:\.\d+)?)\s*(crore|cr|lakh|lac|k)?",
        text,
        re.IGNORECASE,
    )
    if change_by:
        amount = float(change_by.group(2).replace(",", ""))
        unit = (change_by.group(3) or "").lower()
        amount *= 10_000_000 if unit in {"crore", "cr"} else 100_000 if unit in {"lakh", "lac"} else 1_000 if unit == "k" else 1
        is_increase = change_by.group(1).lower() in {"increase", "raise", "add"}
        updates["total_budget"] = max(0, float(event.get("total_budget", 0)) + (amount if is_increase else -amount))
    elif "budget" in lower:
        amount = money_from_text(text)
        if amount is not None:
            updates["total_budget"] = amount

    location_match = re.search(
        r"(?:change|move|switch|update|set|relocate)\s+(?:the\s+)?(?:event\s+)?(?:location|venue|city)\s+(?:to|in)\s+([A-Za-z][A-Za-z .'-]*?)(?=\s+(?:for|with|on|and|budget|theme)\b|[,.;]|$)",
        text,
        re.IGNORECASE,
    )
    if location_match:
        updates["location"] = location_match.group(1).strip()
    elif re.search(r"\b(?:move|relocate)\b", lower):
        location_in = re.search(r"\bto\s+([A-Za-z][A-Za-z .'-]*?)(?=\s+(?:for|with|on)\b|[,.;]|$)", text, re.IGNORECASE)
        if location_in:
            updates["location"] = location_in.group(1).strip()

    date_value = parse_date(text)
    if date_value and any(word in lower for word in ("date", "move", "reschedule", "change", "schedule")):
        updates["event_date"] = date_value

    if "vegetarian" in lower and any(word in lower for word in ("upgrade", "change", "menu", "catering", "switch")):
        updates["food_preferences"] = "Vegetarian"
    elif "vegan" in lower and any(word in lower for word in ("change", "menu", "catering", "switch")):
        updates["food_preferences"] = "Vegan"
    if re.search(r"\bremove\s+(?:the\s+)?dj\b", lower):
        updates["entertainment_requirements"] = "DJ removed; no DJ booking needed."
    elif re.search(r"\badd\s+(?:another\s+)?ceremony\b", lower):
        updates["special_instructions"] = (event.get("special_instructions", "") + " Additional ceremony requested.").strip()
    return updates


def allocate_budget(total_budget: float) -> list[dict[str, Any]]:
    amount = max(0, float(total_budget))
    return [
        {
            "category": category,
            "estimated_cost": round(amount * share),
            "share": round(share * 100, 1),
        }
        for category, share in BUDGET_SHARES.items()
    ]


def save_allocations(event_id: str, preserve_actual: bool = True) -> list[dict[str, Any]]:
    with connection() as conn:
        event = conn.execute("SELECT total_budget FROM events WHERE id = ?", (event_id,)).fetchone()
        if not event:
            return []
        allocations = allocate_budget(float(event["total_budget"]))
        for item in allocations:
            existing = conn.execute(
                "SELECT id, actual_cost, payment_status, notes FROM expenses WHERE event_id=? AND category=?",
                (event_id, item["category"]),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE expenses SET estimated_cost=? WHERE id=?",
                    (item["estimated_cost"], existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO expenses
                    (id,event_id,category,estimated_cost,actual_cost,payment_status,notes)
                    VALUES (?,?,?, ?,0,'not_started','Planning estimate; not a vendor quotation.')""",
                    (make_id("exp"), event_id, item["category"], item["estimated_cost"]),
                )
        rows = conn.execute("SELECT * FROM expenses WHERE event_id=? ORDER BY rowid", (event_id,)).fetchall()
        return [dict(row) for row in rows]


def task_templates(event: dict[str, Any]) -> list[dict[str, str]]:
    event_date = event.get("event_date")
    if event_date:
        try:
            base = date.fromisoformat(event_date)
        except ValueError:
            base = date.today() + __import__("datetime").timedelta(days=90)
    else:
        base = date.today() + __import__("datetime").timedelta(days=90)
    items = [
        ("Confirm venue shortlist", "Compare capacity, accessibility, and weather backup.", 90, "high"),
        ("Confirm catering and menu", "Review menus against dietary and cultural requirements.", 60, "high"),
        ("Book photo and video coverage", "Confirm coverage hours, deliverables, and team size.", 45, "high"),
        ("Finalize theme and decor", "Approve palette, key installations, and setup timing.", 35, "medium"),
        ("Send invitations", "Share invitations and collect RSVP and accommodation details.", 30, "medium"),
        ("Confirm guest count", "Follow up on pending RSVPs and meal requirements.", 14, "medium"),
        ("Coordinate all vendors", "Confirm contacts, arrival windows, and contingency plans.", 7, "high"),
        ("Share the final run sheet", "Review responsibilities and the event-day schedule.", 2, "high"),
    ]
    return [
        {
            "title": title,
            "description": description,
            "deadline": (base - __import__("datetime").timedelta(days=offset)).isoformat(),
            "priority": priority,
        }
        for title, description, offset, priority in items
    ]


def create_tasks(event_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        event_row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if not event_row:
            return []
        existing = conn.execute("SELECT COUNT(*) FROM tasks WHERE event_id=?", (event_id,)).fetchone()[0]
        if existing:
            return [dict(row) for row in conn.execute("SELECT * FROM tasks WHERE event_id=? ORDER BY deadline", (event_id,)).fetchall()]
        event = dict(event_row)
        now = utc_now()
        for item in task_templates(event):
            conn.execute(
                """INSERT INTO tasks (id,event_id,title,description,deadline,priority,status,dependencies,created_at)
                VALUES (?,?,?,?,?,?,'pending','[]',?)""",
                (make_id("task"), event_id, item["title"], item["description"], item["deadline"], item["priority"], now),
            )
        return [dict(row) for row in conn.execute("SELECT * FROM tasks WHERE event_id=? ORDER BY deadline", (event_id,)).fetchall()]

"""Callable planning tools used by both the assistant and the web API."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from app.database import (
    add_message,
    connection,
    get_event,
    make_id,
    utc_now,
)
from app.planning import (
    BUDGET_SHARES,
    allocate_budget,
    create_tasks,
    extract_event_details,
    save_allocations,
    task_templates,
)


def _json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "error": message}


def _event(event_id: str) -> dict[str, Any] | None:
    return get_event(event_id)


def create_event(event_details_json: str) -> dict[str, Any]:
    """Create and persist an event from a JSON object of event requirements.

    Args:
        event_details_json: JSON with event_type, title, location, event_date,
            guest_count, total_budget, theme, and planning preferences.
    """
    details = _json(event_details_json, None)
    if not isinstance(details, dict):
        return _error("event_details_json must be a JSON object")
    parsed = extract_event_details(str(details.get("description", ""))) if details.get("description") else {}
    data = {**parsed, **details}
    try:
        guest_count = max(0, int(data.get("guest_count") or 0))
        total_budget = max(0.0, float(data.get("total_budget") or 0))
        duration_days = max(1, min(30, int(data.get("duration_days") or 1)))
    except (ValueError, TypeError):
        return _error("guest_count, total_budget, and duration_days must be valid numbers")
    event_type = str(data.get("event_type") or "Custom event").strip()[:80]
    location = str(data.get("location") or "").strip()[:160]
    theme = str(data.get("theme") or "").strip()[:160]
    title = str(data.get("title") or (f"{event_type} in {location}" if location else event_type)).strip()[:160]
    event_date = data.get("event_date") or None
    if event_date:
        try:
            event_date = date.fromisoformat(str(event_date)).isoformat()
        except ValueError:
            return _error("event_date must use YYYY-MM-DD")
    event_id = make_id("evt")
    now = utc_now()
    with connection() as conn:
        conn.execute(
            """INSERT INTO events (
                id,title,event_type,location,event_date,duration_days,guest_count,total_budget,
                theme,food_preferences,accommodation_required,accommodation_count,
                decoration_preferences,entertainment_requirements,special_instructions,
                status,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event_id,
                title,
                event_type,
                location,
                event_date,
                duration_days,
                guest_count,
                total_budget,
                theme,
                str(data.get("food_preferences") or "")[:160],
                int(bool(data.get("accommodation_required") or data.get("accommodation_count"))),
                max(0, int(data.get("accommodation_count") or 0)),
                str(data.get("decoration_preferences") or "")[:300],
                str(data.get("entertainment_requirements") or "")[:300],
                str(data.get("special_instructions") or "")[:800],
                "planning",
                now,
                now,
            ),
        )
    generate_event_plan(event_id)
    event = get_event(event_id)
    return {"status": "success", "event": event, "message": "Event created with a starter budget and timeline."}


def update_event(event_id: str, updates_json: str) -> dict[str, Any]:
    """Update event details and recalculate only dependent budget or dates.

    Args:
        event_id: The event record to update.
        updates_json: JSON object containing only changed event fields.
    """
    old_event = get_event(event_id)
    if not old_event:
        return _error("Event not found")
    updates = _json(updates_json, None)
    if not isinstance(updates, dict):
        return _error("updates_json must be a JSON object")
    allowed = {
        "title",
        "event_type",
        "location",
        "event_date",
        "duration_days",
        "guest_count",
        "total_budget",
        "theme",
        "food_preferences",
        "accommodation_required",
        "accommodation_count",
        "decoration_preferences",
        "entertainment_requirements",
        "special_instructions",
        "status",
    }
    changes = {key: value for key, value in updates.items() if key in allowed}
    if not changes:
        return _error("No supported event fields were supplied")
    if "guest_count" in changes:
        try:
            changes["guest_count"] = max(0, int(changes["guest_count"]))
        except (TypeError, ValueError):
            return _error("guest_count must be a non-negative integer")
    if "total_budget" in changes:
        try:
            changes["total_budget"] = max(0.0, float(changes["total_budget"]))
        except (TypeError, ValueError):
            return _error("total_budget must be a non-negative number")
    if "duration_days" in changes:
        try:
            changes["duration_days"] = max(1, min(30, int(changes["duration_days"])))
        except (TypeError, ValueError):
            return _error("duration_days must be between 1 and 30")
    if "event_date" in changes and changes["event_date"]:
        try:
            changes["event_date"] = date.fromisoformat(str(changes["event_date"])).isoformat()
        except ValueError:
            return _error("event_date must use YYYY-MM-DD")
    for field in ("title", "event_type", "location", "theme", "food_preferences", "decoration_preferences", "entertainment_requirements", "special_instructions", "status"):
        if field in changes:
            changes[field] = str(changes[field]).strip()
    if "accommodation_required" in changes:
        changes["accommodation_required"] = int(bool(changes["accommodation_required"]))
    if "accommodation_count" in changes:
        try:
            changes["accommodation_count"] = max(0, int(changes["accommodation_count"]))
        except (TypeError, ValueError):
            return _error("accommodation_count must be a non-negative integer")
    changes["updated_at"] = utc_now()
    assignments = ", ".join(f"{key}=?" for key in changes)
    with connection() as conn:
        conn.execute(
            f"UPDATE events SET {assignments} WHERE id=?",
            (*changes.values(), event_id),
        )
        if "event_date" in changes and old_event.get("event_date") and changes["event_date"]:
            old_date = date.fromisoformat(old_event["event_date"])
            new_date = date.fromisoformat(changes["event_date"])
            delta = (new_date - old_date).days
            rows = conn.execute("SELECT id, deadline FROM tasks WHERE event_id=?", (event_id,)).fetchall()
            for row in rows:
                if row["deadline"]:
                    shifted = date.fromisoformat(row["deadline"]) + timedelta(days=delta)
                    conn.execute("UPDATE tasks SET deadline=? WHERE id=?", (shifted.isoformat(), row["id"]))
            conn.execute("UPDATE event_schedules SET updated_at=? WHERE event_id=?", (changes["updated_at"], event_id))
    if "total_budget" in changes or "guest_count" in changes:
        save_allocations(event_id)
    event = get_event(event_id)
    affected = []
    if "total_budget" in changes or "guest_count" in changes:
        affected.append("budget allocation")
    if "event_date" in changes:
        affected.append("task deadlines")
    if "location" in changes:
        affected.append("vendor search filters")
    return {
        "status": "success",
        "event": event,
        "updated_fields": list(changes.keys()),
        "recalculated": affected,
        "message": "Event updated; dependent planning data was refreshed." if affected else "Event details updated.",
    }


def generate_event_plan(event_id: str) -> dict[str, Any]:
    """Create a personalized starter plan, budget allocations, and task timeline.

    Args:
        event_id: The event to plan.
    """
    event = _event(event_id)
    if not event:
        return _error("Event not found")
    expenses = save_allocations(event_id)
    tasks = create_tasks(event_id)
    ideas = _build_ideas(event, event.get("theme", ""), float(event.get("total_budget", 0)))
    with connection() as conn:
        existing = conn.execute("SELECT ideas_json FROM events WHERE id=?", (event_id,)).fetchone()
        stored = _json(existing["ideas_json"], []) if existing else []
        if not stored:
            conn.execute("UPDATE events SET ideas_json=?, updated_at=? WHERE id=?", (json.dumps(ideas), utc_now(), event_id))
        else:
            ideas = stored
    return {
        "status": "success",
        "event_id": event_id,
        "plan": {
            "summary": _plan_summary(event),
            "budget": _budget_summary(event, expenses),
            "tasks": tasks,
            "ideas": ideas,
            "assumptions": ["Costs are planning estimates, not verified vendor quotations."],
        },
    }


def calculate_budget(event_id: str, expenses_json: str) -> dict[str, Any]:
    """Calculate allocations, actual spend, remaining budget, and warnings.

    Args:
        event_id: The event budget to calculate.
        expenses_json: Optional JSON list of category actual-cost updates.
    """
    event = _event(event_id)
    if not event:
        return _error("Event not found")
    updates = _json(expenses_json, [])
    if updates and not isinstance(updates, list):
        return _error("expenses_json must be a JSON list")
    with connection() as conn:
        for item in updates:
            if not isinstance(item, dict) or not item.get("category"):
                continue
            try:
                actual_cost = max(0, float(item.get("actual_cost", item.get("actualCost", 0))))
            except (TypeError, ValueError):
                return _error("actual_cost must be a non-negative number")
            conn.execute(
                """UPDATE expenses SET actual_cost=?, payment_status=?
                WHERE event_id=? AND category=?""",
                (actual_cost, item.get("payment_status", "in_progress"), event_id, str(item["category"])),
            )
    current = get_event(event_id)
    summary = _budget_summary(current, current["expenses"])
    return {"status": "success", "budget": summary}


def optimize_budget(event_id: str, target_budget: float) -> dict[str, Any]:
    """Recalculate category estimates for a target budget while preserving actuals.

    Args:
        event_id: The event to optimize.
        target_budget: The user's new total planning budget in rupees.
    """
    if not _event(event_id):
        return _error("Event not found")
    try:
        target = max(0, float(target_budget))
    except (TypeError, ValueError):
        return _error("target_budget must be a non-negative number")
    update_event(event_id, json.dumps({"total_budget": target}))
    result = calculate_budget(event_id, "[]")
    result["optimization"] = {
        "target_budget": target,
        "recommendation": "Category estimates were proportionally rebalanced; review actual costs before committing.",
        "contingency": round(target * BUDGET_SHARES["Contingency"]),
    }
    return result


def generate_timeline(event_id: str) -> dict[str, Any]:
    """Generate event milestones, deadlines, priorities, and dependencies.

    Args:
        event_id: The event to schedule.
    """
    event = _event(event_id)
    if not event:
        return _error("Event not found")
    tasks = create_tasks(event_id)
    return {"status": "success", "event_id": event_id, "tasks": tasks}


def update_timeline(event_id: str, changes_json: str) -> dict[str, Any]:
    """Reschedule tasks and identify timeline conflicts after a change.

    Args:
        event_id: The event whose timeline is being changed.
        changes_json: JSON with new_event_date, task_id, deadline, or status.
    """
    if not _event(event_id):
        return _error("Event not found")
    changes = _json(changes_json, {})
    if not isinstance(changes, dict):
        return _error("changes_json must be a JSON object")
    if changes.get("new_event_date"):
        result = update_event(event_id, json.dumps({"event_date": changes["new_event_date"]}))
        if result.get("status") == "error":
            return result
    if changes.get("task_id"):
        fields = {key: changes[key] for key in ("deadline", "status", "priority") if key in changes}
        if fields:
            with connection() as conn:
                fields["event_id"] = event_id
                query_fields = {key: value for key, value in fields.items() if key != "event_id"}
                conn.execute(
                    "UPDATE tasks SET " + ",".join(f"{key}=?" for key in query_fields) + " WHERE id=? AND event_id=?",
                    (*query_fields.values(), changes["task_id"], event_id),
                )
    event = get_event(event_id)
    tasks = event["tasks"]
    date_conflicts = []
    for task in tasks:
        if task.get("deadline") and task["deadline"] < date.today().isoformat() and task["status"] != "completed":
            date_conflicts.append({"task_id": task["id"], "title": task["title"], "deadline": task["deadline"]})
    return {"status": "success", "tasks": tasks, "conflicts": date_conflicts, "message": "Timeline updated; overdue items are flagged for review."}


def search_vendors(event_id: str, category: str, location: str, budget: float, preferences: str) -> dict[str, Any]:
    """Search only vendors entered into this event workspace.

    Args:
        event_id: The event whose vendor list should be searched.
        category: Vendor category such as venue, catering, or photography.
        location: Preferred city or service area.
        budget: Maximum target budget in rupees.
        preferences: Other service requirements or preferences.
    """
    if not _event(event_id):
        return _error("Event not found")
    filters = ["event_id=?"]
    params: list[Any] = [event_id]
    if category.strip() and category.lower() != "any":
        filters.append("LOWER(category) LIKE ?")
        params.append(f"%{category.strip().lower()}%")
    if location.strip():
        filters.append("(location='' OR LOWER(location) LIKE ?)")
        params.append(f"%{location.strip().lower()}%")
    if preferences.strip():
        filters.append("(LOWER(services) LIKE ? OR LOWER(notes) LIKE ? OR LOWER(name) LIKE ?)")
        query = f"%{preferences.strip().lower()}%"
        params.extend([query, query, query])
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vendors WHERE " + " AND ".join(filters) + " ORDER BY name COLLATE NOCASE",
            params,
        ).fetchall()
    vendors = [dict(row) for row in rows]
    if budget > 0:
        vendors.sort(key=lambda item: (item["price_min"] > budget, abs(float(item["price_max"] or item["price_min"]) - budget)))
    return {
        "status": "success",
        "vendors": vendors,
        "source": "user-entered workspace records only",
        "message": "No user-entered vendors match yet." if not vendors else "Results are user-entered and have not been independently verified.",
    }


def compare_vendors(vendor_ids_json: str) -> dict[str, Any]:
    """Compare selected user-entered vendor records side by side.

    Args:
        vendor_ids_json: JSON array of vendor record IDs.
    """
    ids = _json(vendor_ids_json, None)
    if not isinstance(ids, list) or not ids:
        return _error("vendor_ids_json must be a non-empty JSON list")
    placeholders = ",".join("?" for _ in ids)
    with connection() as conn:
        rows = conn.execute(f"SELECT * FROM vendors WHERE id IN ({placeholders})", ids).fetchall()
    vendors = [dict(row) for row in rows]
    return {
        "status": "success",
        "vendors": vendors,
        "comparison": [
            {"name": item["name"], "category": item["category"], "price_range": [item["price_min"], item["price_max"]], "rating": item["rating"], "services": item["services"], "verification_status": item["verification_status"]}
            for item in vendors
        ],
        "note": "Only user-entered information is shown; no ratings or availability are inferred.",
    }


def _build_ideas(event: dict[str, Any], theme: str, budget: float) -> list[dict[str, Any]]:
    event_type = event.get("event_type", "event").lower()
    preferred = theme or event.get("theme") or "personalized celebration"
    names = [preferred.title() if preferred else "Signature celebration", "Modern garden gathering", "Intimate cultural experience"]
    subtitles = [
        "Build the day around your preferred theme and a few memorable moments.",
        "Keep the visual plan light, flexible, and guest-friendly.",
        "Bring local details into the food, music, and guest experience.",
    ]
    palettes = [["#7d4e57", "#e4b168", "#f4e7d5"], ["#85987e", "#e8ddc8", "#f9f6ef"], ["#bf7a55", "#d7b06d", "#f2e2cf"]]
    ideas = []
    for index, fraction in enumerate((0.68, 0.84, 0.98)):
        ideas.append(
            {
                "id": f"concept-{index + 1}",
                "title": names[index],
                "summary": f"A {event_type} concept that suits {event.get('guest_count', 0) or 'your'} guests. {subtitles[index]}",
                "estimated_cost": round(max(0, budget) * fraction),
                "budget_fit": "Within budget" if budget > 0 else "Add a budget to estimate",
                "palette": palettes[index],
                "decoration": ["Layered lighting", "Focal table details", "Reusable florals" if index == 0 else "Local seasonal greens"],
                "food": event.get("food_preferences") or "Build the menu around guest preferences",
                "experience": ["Welcome moment", "One shared activity", "Quiet seating area"],
            }
        )
    return ideas


def generate_event_ideas(event_id: str, theme: str, budget: float) -> dict[str, Any]:
    """Generate three budget-aware event concepts and creative direction.

    Args:
        event_id: The event to personalize ideas for.
        theme: Preferred theme or mood.
        budget: Maximum concept budget in rupees.
    """
    event = _event(event_id)
    if not event:
        return _error("Event not found")
    try:
        amount = max(0, float(budget)) if budget else float(event["total_budget"])
    except (ValueError, TypeError):
        return _error("budget must be a non-negative number")
    ideas = _build_ideas(event, theme, amount)
    with connection() as conn:
        conn.execute("UPDATE events SET ideas_json=?,updated_at=? WHERE id=?", (json.dumps(ideas), utc_now(), event_id))
    return {"status": "success", "ideas": ideas, "note": "Concept costs are estimates for planning, not vendor quotes."}


def manage_guests(event_id: str, action: str, guest_data_json: str) -> dict[str, Any]:
    """Add, update, delete, or list guest records for an event.

    Args:
        event_id: The event whose guest list is being managed.
        action: One of add, update, delete, or list.
        guest_data_json: JSON guest object, guest list, or object with guest_id.
    """
    if not _event(event_id):
        return _error("Event not found")
    data = _json(guest_data_json, {})
    if action == "list":
        event = get_event(event_id)
        return {"status": "success", "guests": event["guests"], "analytics": _guest_analytics(event["guests"])}
    if action == "add":
        guests = data if isinstance(data, list) else [data]
        if not guests or any(not isinstance(item, dict) or not str(item.get("name", "")).strip() for item in guests):
            return _error("Each guest needs a name")
        now = utc_now()
        inserted = []
        with connection() as conn:
            for item in guests:
                guest_id = make_id("gst")
                conn.execute(
                    """INSERT INTO guests
                    (id,event_id,name,contact,group_category,rsvp_status,meal_preference,dietary_restrictions,accommodation_required,table_name,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        guest_id,
                        event_id,
                        str(item["name"]).strip()[:120],
                        str(item.get("contact") or "")[:160],
                        str(item.get("group_category") or item.get("group") or "Friends")[:80],
                        str(item.get("rsvp_status") or item.get("rsvp") or "pending")[:32],
                        str(item.get("meal_preference") or item.get("meal") or "")[:80],
                        str(item.get("dietary_restrictions") or "")[:200],
                        int(bool(item.get("accommodation_required"))),
                        str(item.get("table_name") or "")[:80],
                        now,
                    ),
                )
                inserted.append(guest_id)
        return {"status": "success", "guest_ids": inserted, "message": f"Added {len(inserted)} guest record(s)."}
    guest_id = str(data.get("guest_id") or data.get("id") or "") if isinstance(data, dict) else ""
    if action == "delete":
        with connection() as conn:
            cursor = conn.execute("DELETE FROM guests WHERE id=? AND event_id=?", (guest_id, event_id))
        return {"status": "success", "deleted": cursor.rowcount > 0}
    if action == "update" and guest_id:
        fields = {
            "name": data.get("name"),
            "contact": data.get("contact"),
            "group_category": data.get("group_category", data.get("group")),
            "rsvp_status": data.get("rsvp_status", data.get("rsvp")),
            "meal_preference": data.get("meal_preference", data.get("meal")),
            "dietary_restrictions": data.get("dietary_restrictions"),
            "accommodation_required": int(bool(data["accommodation_required"])) if "accommodation_required" in data else None,
            "table_name": data.get("table_name"),
        }
        fields = {key: value for key, value in fields.items() if value is not None}
        if fields:
            with connection() as conn:
                conn.execute("UPDATE guests SET " + ",".join(f"{key}=?" for key in fields) + " WHERE id=? AND event_id=?", (*fields.values(), guest_id, event_id))
        return {"status": "success", "updated": bool(fields), "guest_id": guest_id}
    return _error("Action must be add, update, delete, or list")


def _guest_analytics(guests: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tracked": len(guests),
        "confirmed": sum(1 for guest in guests if guest["rsvp_status"] == "confirmed"),
        "pending": sum(1 for guest in guests if guest["rsvp_status"] == "pending"),
        "declined": sum(1 for guest in guests if guest["rsvp_status"] == "declined"),
        "accommodation": sum(1 for guest in guests if guest["accommodation_required"]),
    }


def generate_invitation(event_details_json: str, tone: str, language: str) -> dict[str, Any]:
    """Draft an invitation message; this tool never sends it.

    Args:
        event_details_json: JSON event details or an event record.
        tone: Desired style such as warm, formal, joyful, or minimal.
        language: Requested language, for example English or Hindi.
    """
    details = _json(event_details_json, None)
    if not isinstance(details, dict):
        return _error("event_details_json must be a JSON object")
    event_type = str(details.get("event_type") or "celebration")
    title = str(details.get("title") or event_type)
    location = str(details.get("location") or "")
    date_text = str(details.get("event_date") or "date to be confirmed")
    guest_names = details.get("guest_names") or "you"
    tone_text = tone.strip().lower()
    language_name = language.strip().lower()
    if language_name in {"hindi", "हिन्दी", "हिंदी"}:
        invitation = f"सप्रेम आमंत्रण\n\nहमारी खुशी के अवसर {title} पर {guest_names} की उपस्थिति हमारे लिए बहुत मायने रखेगी।\n\nदिनांक: {date_text}\nस्थान: {location or 'स्थान की जानकारी शीघ्र साझा करेंगे'}\n\nकृपया अपनी उपस्थिति की पुष्टि करें।\nस्नेह सहित,\nपरिवार"
        used_language = "Hindi"
    else:
        greeting = "You’re warmly invited" if tone_text in {"warm", "friendly", "joyful"} else "Please join us" if tone_text == "formal" else "Save the date"
        invitation = f"{greeting}\n\nWe would love for {guest_names} to join us for {title}.\n\nDate: {date_text}\nLocation: {location or 'Details to follow'}\n\nPlease let us know if you can make it.\n\nWith love,\nThe hosts"
        used_language = "English"
    return {"status": "success", "draft": invitation, "language": used_language, "sent": False, "note": "Draft only. Planora does not send invitations or contact guests."}


def check_task_status(event_id: str) -> dict[str, Any]:
    """Retrieve completed, pending, overdue, and upcoming tasks.

    Args:
        event_id: The event whose tasks should be summarized.
    """
    event = _event(event_id)
    if not event:
        return _error("Event not found")
    today = date.today().isoformat()
    completed = [task for task in event["tasks"] if task["status"] == "completed"]
    overdue = [task for task in event["tasks"] if task["status"] != "completed" and task.get("deadline") and task["deadline"] < today]
    upcoming = [task for task in event["tasks"] if task["status"] != "completed" and task.get("deadline") and task["deadline"] >= today]
    return {"status": "success", "completed": completed, "pending": [task for task in event["tasks"] if task["status"] != "completed"], "overdue": overdue, "upcoming": upcoming, "counts": {"completed": len(completed), "overdue": len(overdue), "upcoming": len(upcoming)}}


def generate_event_day_schedule(event_id: str) -> dict[str, Any]:
    """Create and persist an operational run sheet for each event day.

    Args:
        event_id: The event to coordinate.
    """
    event = _event(event_id)
    if not event:
        return _error("Event not found")
    duration = int(event.get("duration_days") or 1)
    event_type = event.get("event_type", "Event")
    day_templates = [
        [("08:00", "Venue access and setup", "Event lead"), ("10:00", "Vendor arrivals and sound check", "Operations lead"), ("12:00", "Guest welcome and refreshments", "Guest team"), ("14:00", "Main ceremony or opening", "Event lead"), ("16:00", "Meal service", "Catering lead"), ("18:00", "Entertainment and guest activities", "Program lead"), ("20:30", "Closing and transport coordination", "Operations lead")],
        [("09:00", "Team briefing and venue check", "Event lead"), ("11:00", "Guest arrival and welcome", "Guest team"), ("13:00", "Main celebration", "Program lead"), ("15:00", "Meal and speeches", "Catering lead"), ("17:30", "Closing moment and departures", "Operations lead")],
    ]
    schedule = []
    for day_number in range(1, duration + 1):
        template = day_templates[min(day_number - 1, len(day_templates) - 1)]
        schedule.append({
            "day": day_number,
            "label": f"Day {day_number} · {event_type}",
            "items": [
                {"time": time, "activity": activity, "owner": owner, "status": "planned"}
                for time, activity, owner in template
            ],
        })
    with connection() as conn:
        conn.execute(
            "INSERT INTO event_schedules(event_id,data_json,updated_at) VALUES(?,?,?) ON CONFLICT(event_id) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at",
            (event_id, json.dumps(schedule), utc_now()),
        )
    return {"status": "success", "schedule": schedule, "note": "Assign real team members before sharing the run sheet."}


def suggest_alternatives(event_id: str, problem: str) -> dict[str, Any]:
    """Suggest practical alternatives for a delay, cancellation, or budget issue.

    Args:
        event_id: The event context for the recommendation.
        problem: A plain-language planning issue.
    """
    event = _event(event_id)
    if not event:
        return _error("Event not found")
    lower = problem.lower()
    if any(word in lower for word in ("delay", "late", "behind")):
        options = [
            "Move guest arrival or a flexible photo block by the delay, then protect the ceremony start.",
            "Use a short welcome activity to absorb the gap while the delayed vendor arrives.",
            "Ask the event lead to confirm the new arrival time and send one update to affected owners.",
        ]
    elif any(word in lower for word in ("rain", "weather", "outdoor")):
        options = [
            "Switch the ceremony to the pre-identified indoor backup and keep the guest route covered.",
            "Move only the weather-sensitive activity indoors; retain the rest of the plan.",
            "Set a decision time with the venue and assign one person to update vendors and guests.",
        ]
    elif any(word in lower for word in ("budget", "cost", "expensive", "over budget")):
        options = [
            "Protect accessibility, dietary needs, and core guest experience; trim optional decor first.",
            "Compare a smaller menu or shorter service window before reducing contingency.",
            "Request revised written estimates from user-selected vendors before changing commitments.",
        ]
    else:
        options = [
            "Identify the deadline and people affected, then change only the dependent tasks.",
            "Choose a low-impact substitute and keep a named owner for the decision.",
            "Record the change in the event workspace so the team is working from one plan.",
        ]
    return {"status": "success", "problem": problem, "alternatives": options, "event_id": event_id, "note": "These are planning suggestions; no vendor or guest has been contacted."}


def generate_event_report(event_id: str) -> dict[str, Any]:
    """Create a structured summary of event details, budget, tasks, guests, and vendors.

    Args:
        event_id: The event to summarize.
    """
    event = _event(event_id)
    if not event:
        return _error("Event not found")
    budget = _budget_summary(event, event["expenses"])
    status = check_task_status(event_id)
    return {
        "status": "success",
        "report": {
            "event": {key: event[key] for key in ("id", "title", "event_type", "location", "event_date", "duration_days", "guest_count", "total_budget", "theme", "status", "is_demo")},
            "budget": budget,
            "tasks": status["counts"],
            "guest_count_tracked": len(event["guests"]),
            "vendors_entered": len(event["vendors"]),
            "generated_at": utc_now(),
        },
    }


def _budget_summary(event: dict[str, Any], expenses: list[dict[str, Any]]) -> dict[str, Any]:
    allocated = sum(float(item.get("estimated_cost", 0)) for item in expenses)
    actual = sum(float(item.get("actual_cost", 0)) for item in expenses)
    total = float(event.get("total_budget") or 0)
    categories = []
    for item in expenses:
        estimate = float(item.get("estimated_cost", 0))
        spent = float(item.get("actual_cost", 0))
        categories.append({**item, "remaining": estimate - spent, "consumed_pct": round(spent * 100 / estimate, 1) if estimate else 0})
    return {
        "total_budget": total,
        "allocated": allocated,
        "actual_spend": actual,
        "remaining": total - actual,
        "budget_consumed_pct": round(actual * 100 / total, 1) if total else 0,
        "over_budget": actual > total,
        "warning": "Actual spend is above the total budget." if actual > total else None,
        "categories": categories,
    }


def _plan_summary(event: dict[str, Any]) -> str:
    date_phrase = f"on {event['event_date']}" if event.get("event_date") else "on a date to be confirmed"
    budget_phrase = f"₹{float(event.get('total_budget') or 0):,.0f}" if event.get("total_budget") else "a budget to be confirmed"
    parts = [f"{event.get('event_type', 'Event')} in {event.get('location') or 'a location to be confirmed'} {date_phrase}", f"for {int(event.get('guest_count') or 0)} guests", f"planned around {budget_phrase}"]
    if event.get("theme"):
        parts.append(f"with a {event['theme']} direction")
    if event.get("food_preferences"):
        parts.append(f"and {event['food_preferences']} food preferences")
    return ", ".join(parts) + "."


def _event_context_summary(event: dict[str, Any]) -> str:
    return _plan_summary(event)


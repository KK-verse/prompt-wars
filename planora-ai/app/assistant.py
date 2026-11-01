"""Natural-language routing and optional Gemini-backed ADK conversation."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.database import add_message, get_event, get_messages
from app.planning import extract_event_details, extract_updates
from app.tools import (
    calculate_budget,
    check_task_status,
    create_event,
    generate_event_day_schedule,
    generate_event_ideas,
    generate_event_report,
    generate_invitation,
    manage_guests,
    search_vendors,
    suggest_alternatives,
    update_event,
)


def model_is_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def _rupees(value: float | int) -> str:
    number = int(round(float(value or 0)))
    if number < 1000:
        return f"₹{number:,}"
    last3 = f"{number % 1000:03d}"
    rest = str(number // 1000)
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return f"₹{','.join(groups)},{last3}"


def _new_event_from_message(message: str) -> dict[str, Any]:
    details = extract_event_details(message)
    has_event_signal = (
        details["event_type"] != "Custom event"
        or details["location"]
        or details["guest_count"]
        or details["total_budget"]
        or details["event_date"]
    )
    if not has_event_signal:
        return {
            "message": "Tell me the event type and, if you know it, the city. I’ll build the first draft from there.",
            "event_id": None,
            "tool_name": None,
            "tool_result": None,
        }
    result = create_event(json.dumps(details))
    if result.get("status") != "success":
        return {"message": result.get("error", "I could not create the event."), "event_id": None, "tool_name": "create_event", "tool_result": result}
    event = result["event"]
    message_text = (
        f"I set up {event['title']} for {int(event['guest_count'])} guests. "
        f"The workspace now has a starter budget and {len(event['tasks'])} planning milestones. "
    )
    if event["total_budget"]:
        message_text += f"The current budget is {_rupees(event['total_budget'])}, with all category costs marked as estimates. "
    if not event["event_date"]:
        message_text += "What date should I plan around?"
    elif not event["total_budget"]:
        message_text += "What total budget should I use for the category plan?"
    elif not event["guest_count"]:
        message_text += "How many guests should I plan for?"
    else:
        message_text += "Would you like to work on the budget, timeline, or event ideas first?"
    return {"message": message_text, "event_id": event["id"], "tool_name": "create_event", "tool_result": result}


def local_tool_response(message: str, event_id: str | None) -> dict[str, Any]:
    """Run the appropriate local tool for simple requests without model credentials."""
    if not event_id:
        return _new_event_from_message(message)
    event = get_event(event_id)
    if not event:
        return {"message": "I can’t find that event. Choose an event from the workspace or create a new one.", "event_id": None, "tool_name": None, "tool_result": None}
    text = message.strip()
    lower = text.lower()
    updates = extract_updates(text, event)
    if updates:
        result = update_event(event_id, json.dumps(updates))
        updated = result.get("event") or event
        changed = []
        if "guest_count" in updates:
            changed.append(f"guest count to {int(updated['guest_count'])}")
        if "total_budget" in updates:
            changed.append(f"total budget to {_rupees(updated['total_budget'])}")
        if "location" in updates:
            changed.append(f"location to {updated['location']}")
        if "event_date" in updates:
            changed.append(f"date to {updated['event_date']}")
        if "food_preferences" in updates:
            changed.append(f"food preference to {updated['food_preferences']}")
        if "entertainment_requirements" in updates:
            changed.append("the entertainment plan")
        return {
            "message": "Updated " + ", ".join(changed) + ". I refreshed the affected estimates or deadlines while keeping unrelated plan items.",
            "event_id": event_id,
            "tool_name": "update_event",
            "tool_result": result,
        }

    if any(word in lower for word in ("vendor", "venue", "caterer", "photographer", "decorator", "dj")):
        category = "any"
        for choice in ("venue", "caterer", "catering", "decorator", "photographer", "videographer", "dj", "makeup", "transport", "accommodation"):
            if choice in lower:
                category = "catering" if choice == "caterer" else "decoration" if choice == "decorator" else "photography" if choice == "photographer" else choice
                break
        result = search_vendors(event_id, category, event.get("location", ""), float(event.get("total_budget") or 0), "")
        if result.get("vendors"):
            names = ", ".join(item["name"] for item in result["vendors"])
            response = f"I found these user-entered {category} records: {names}. Their details have not been independently verified."
        else:
            response = "There are no user-entered vendor records for this event yet. Add a vendor in the Vendors section and I can filter or compare those details. I won’t invent businesses, prices, ratings, or availability."
        return {"message": response, "event_id": event_id, "tool_name": "search_vendors", "tool_result": result}

    if any(word in lower for word in ("idea", "theme", "decor", "colour", "color", "inspiration", "concept")):
        theme = event.get("theme", "")
        result = generate_event_ideas(event_id, theme, float(event.get("total_budget") or 0))
        ideas = result.get("ideas", [])
        descriptions = " ".join(f"{index + 1}. {idea['title']} — about {_rupees(idea['estimated_cost'])}." for index, idea in enumerate(ideas))
        return {"message": f"Here are three directions for {event['title']}: {descriptions} These concept costs are estimates, not quotations.", "event_id": event_id, "tool_name": "generate_event_ideas", "tool_result": result}

    if any(word in lower for word in ("budget", "spend", "expense", "cost", "remaining")):
        result = calculate_budget(event_id, "[]")
        budget = result.get("budget", {})
        response = (
            f"The current total budget is {_rupees(budget.get('total_budget', 0))}. "
            f"Actual spend is {_rupees(budget.get('actual_spend', 0))}, leaving {_rupees(budget.get('remaining', 0))}. "
            f"{budget.get('budget_consumed_pct', 0)}% of the total budget has been spent. Category allocations are planning estimates."
        )
        return {"message": response, "event_id": event_id, "tool_name": "calculate_budget", "tool_result": result}

    if any(word in lower for word in ("event day", "run sheet", "hour-by-hour", "schedule for the day")):
        result = generate_event_day_schedule(event_id)
        first_day = result.get("schedule", [{}])[0]
        items = first_day.get("items", [])[:4]
        peek = "; ".join(f"{item['time']} {item['activity']}" for item in items)
        return {"message": f"I drafted a {len(result.get('schedule', []))}-day run sheet. Day one begins: {peek}. Add named owners in your team before sharing it.", "event_id": event_id, "tool_name": "generate_event_day_schedule", "tool_result": result}

    if any(word in lower for word in ("timeline", "task", "deadline", "what's next", "what is next", "progress")):
        result = check_task_status(event_id)
        next_task = next(iter(result.get("upcoming", [])), None)
        response = f"{result['counts']['completed']} planning tasks are complete and {result['counts']['overdue']} are overdue. "
        if next_task:
            response += f"The next open milestone is {next_task['title']} by {next_task['deadline']}."
        else:
            response += "Your open milestones are listed in the Timeline section."
        return {"message": response, "event_id": event_id, "tool_name": "check_task_status", "tool_result": result}

    if "guest" in lower or "rsvp" in lower or "invite list" in lower:
        result = manage_guests(event_id, "list", "{}")
        analytics = result.get("analytics", {})
        response = f"There are {analytics.get('tracked', 0)} guest records tracked, with {analytics.get('confirmed', 0)} confirmed and {analytics.get('pending', 0)} pending. Add or edit guests in the Guests section."
        return {"message": response, "event_id": event_id, "tool_name": "manage_guests", "tool_result": result}

    if "invitation" in lower or "invite message" in lower:
        result = generate_invitation(json.dumps(event), "warm", "English")
        return {"message": "I drafted an invitation below. It has not been sent.\n\n" + result["draft"], "event_id": event_id, "tool_name": "generate_invitation", "tool_result": result}

    if any(word in lower for word in ("delay", "late", "rain", "weather", "cancel", "over budget", "alternative", "emergency")):
        result = suggest_alternatives(event_id, text)
        options = " ".join(f"{index + 1}. {item}" for index, item in enumerate(result.get("alternatives", [])))
        return {"message": f"Here are practical options for this event: {options}", "event_id": event_id, "tool_name": "suggest_alternatives", "tool_result": result}

    if "report" in lower or "summary" in lower:
        result = generate_event_report(event_id)
        report = result.get("report", {})
        return {"message": f"{event['title']} is planned for {event.get('event_date') or 'a date to be confirmed'} in {event.get('location') or 'a location to be confirmed'}, with {event.get('guest_count', 0)} guests and a {_rupees(event.get('total_budget', 0))} budget. {report.get('tasks', {}).get('completed', 0)} tasks are complete.", "event_id": event_id, "tool_name": "generate_event_report", "tool_result": result}

    task_result = check_task_status(event_id)
    next_task = next(iter(task_result.get("upcoming", [])), None)
    context = f"{event['event_type']} in {event.get('location') or 'location TBD'} for {event.get('guest_count', 0)} guests"
    if next_task:
        context += f". The next open milestone is {next_task['title']} by {next_task['deadline']}"
    return {
        "message": f"I’m planning {context}. I can update requirements, recalculate the budget, review the timeline, generate ideas, or work with your guest and vendor records. What would you like to adjust?",
        "event_id": event_id,
        "tool_name": "check_task_status",
        "tool_result": task_result,
    }


_session_service = None
_runner = None
_active_sessions: set[str] = set()


async def gemini_response(event_id: str, message: str) -> dict[str, Any]:
    """Run one ADK turn with persistent in-process event sessions."""
    global _session_service, _runner
    if _runner is None:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        from app.agent import app as adk_app

        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
        _session_service = InMemorySessionService()
        _runner = Runner(app=adk_app, session_service=_session_service)

    event = get_event(event_id)
    if not event:
        return {"message": "I can’t find the selected event.", "event_id": event_id, "tool_name": None, "tool_result": None, "mode": "gemini"}

    from google.genai import types

    user_id = "local-user"
    if event_id not in _active_sessions:
        await _session_service.create_session(app_name="app", user_id=user_id, session_id=event_id)
        _active_sessions.add(event_id)
    history = get_messages(event_id, 12)
    recent_context = ""
    if len(history) > 1 and event_id in _active_sessions:
        recent_context = "\nRecent saved conversation:\n" + "\n".join(
            f"{item['role']}: {item['content']}" for item in history[-8:]
        )
    event_context = {
        "id": event["id"],
        "title": event["title"],
        "event_type": event["event_type"],
        "location": event["location"],
        "event_date": event["event_date"],
        "duration_days": event["duration_days"],
        "guest_count": event["guest_count"],
        "total_budget": event["total_budget"],
        "theme": event["theme"],
        "food_preferences": event["food_preferences"],
        "accommodation_count": event["accommodation_count"],
    }
    prompt = (
        f"Current event context (authoritative persisted values): {json.dumps(event_context)}\n"
        f"Event ID for tool calls: {event_id}.{recent_context}\n\nLatest user request: {message}"
    )
    content = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    response_text = ""
    tool_calls = []
    async for event_result in _runner.run_async(user_id=user_id, session_id=event_id, new_message=content):
        parts = event_result.content.parts if event_result.content and event_result.content.parts else []
        for part in parts:
            if part.function_call:
                tool_calls.append({"name": part.function_call.name, "args": dict(part.function_call.args or {})})
        if event_result.is_final_response():
            response_text = "\n".join(part.text for part in parts if part.text)
    if not response_text:
        response_text = "I updated the event workspace. You can review the changed details in the relevant section."
    return {
        "message": response_text,
        "event_id": event_id,
        "tool_name": ", ".join(item["name"] for item in tool_calls) or None,
        "tool_result": {"calls": tool_calls} if tool_calls else None,
        "mode": "gemini",
    }


"""FastAPI backend for the local Planora workspace."""

from __future__ import annotations

import csv
import io
import json
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app import assistant
from app.database import (
    add_message,
    connection,
    dashboard_payload,
    get_event,
    get_messages,
    init_db,
    make_id,
    utc_now,
)
from app.tools import (
    calculate_budget,
    create_event,
    generate_event_day_schedule,
    generate_event_ideas,
    generate_event_plan,
    generate_event_report,
    generate_invitation,
    manage_guests,
    search_vendors,
    compare_vendors,
    update_event,
    update_timeline,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Planora AI",
    description="Local-first event planning workspace with a tool-using assistant.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "assistant_mode": "gemini" if assistant.model_is_configured() else "local"}


@app.get("/api/dashboard")
def get_dashboard(event_id: str | None = None) -> dict[str, Any]:
    return dashboard_payload(event_id)


@app.get("/api/events")
def get_events() -> list[dict[str, Any]]:
    return dashboard_payload()["events"]


@app.post("/api/events")
def post_event(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    result = create_event(json.dumps(body))
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result.get("error", "Invalid event details"))
    return result["event"]


@app.get("/api/events/{event_id}")
def get_event_detail(event_id: str) -> dict[str, Any]:
    event = get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.patch("/api/events/{event_id}")
def patch_event(event_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    result = update_event(event_id, json.dumps(body))
    if result.get("status") != "success":
        raise HTTPException(status_code=400 if result.get("error") != "Event not found" else 404, detail=result.get("error"))
    return result["event"]


@app.post("/api/events/{event_id}/plan")
def post_plan(event_id: str) -> dict[str, Any]:
    result = generate_event_plan(event_id)
    if result.get("status") != "success":
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@app.get("/api/events/{event_id}/messages")
def event_messages(event_id: str) -> list[dict[str, Any]]:
    if not get_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    return get_messages(event_id)


@app.post("/api/assistant/chat")
async def assistant_chat(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    message = str(body.get("message") or "").strip()
    event_id = body.get("event_id") or None
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    if event_id and assistant.model_is_configured():
        try:
            result = await assistant.gemini_response(str(event_id), message)
        except Exception:
            result = {
                "message": "Gemini could not complete this turn. Refresh the workspace to review any saved tool updates, then try again or continue in local mode by removing the API key.",
                "event_id": str(event_id),
                "tool_name": None,
                "tool_result": None,
                "mode": "gemini-unavailable",
            }
    else:
        result = assistant.local_tool_response(message, str(event_id) if event_id else None)
        result["mode"] = "local"
    response_event_id = result.get("event_id") or event_id
    if response_event_id and get_event(str(response_event_id)):
        add_message(str(response_event_id), "user", message)
        add_message(
            str(response_event_id),
            "assistant",
            str(result.get("message") or ""),
            {"tool_name": result.get("tool_name"), "tool_result": result.get("tool_result"), "mode": result.get("mode")},
        )
    return result


@app.post("/api/events/{event_id}/expenses")
def post_expense(event_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not get_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    category = str(body.get("category") or "").strip()
    if not category:
        raise HTTPException(status_code=400, detail="category is required")
    try:
        actual_cost = max(0, float(body.get("actual_cost", 0)))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="actual_cost must be a number") from None
    with connection() as conn:
        row = conn.execute("SELECT id FROM expenses WHERE event_id=? AND category=?", (event_id, category)).fetchone()
        if row:
            conn.execute(
                "UPDATE expenses SET actual_cost=?,payment_status=?,notes=? WHERE id=?",
                (actual_cost, str(body.get("payment_status") or "in_progress"), str(body.get("notes") or ""), row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO expenses(id,event_id,category,estimated_cost,actual_cost,payment_status,notes) VALUES(?,?,?,0,?,?,?)",
                (make_id("exp"), event_id, category, actual_cost, str(body.get("payment_status") or "in_progress"), str(body.get("notes") or "")),
            )
    return calculate_budget(event_id, "[]")["budget"]


@app.patch("/api/events/{event_id}/tasks/{task_id}")
def patch_task(event_id: str, task_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not get_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    result = update_timeline(event_id, json.dumps({"task_id": task_id, **body}))
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/api/events/{event_id}/guests")
def post_guest(event_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    result = manage_guests(event_id, "add", json.dumps(body))
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result.get("error"))
    return {**result, "event": get_event(event_id)}


@app.post("/api/events/{event_id}/guests/import")
def import_guests(event_id: str, body: list[dict[str, Any]] = Body(...)) -> dict[str, Any]:
    result = manage_guests(event_id, "add", json.dumps(body))
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result.get("error"))
    return {**result, "event": get_event(event_id)}


@app.patch("/api/events/{event_id}/guests/{guest_id}")
def patch_guest(event_id: str, guest_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    result = manage_guests(event_id, "update", json.dumps({**body, "guest_id": guest_id}))
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result.get("error"))
    return {**result, "event": get_event(event_id)}


@app.delete("/api/events/{event_id}/guests/{guest_id}")
def delete_guest(event_id: str, guest_id: str) -> dict[str, Any]:
    result = manage_guests(event_id, "delete", json.dumps({"guest_id": guest_id}))
    return {**result, "event": get_event(event_id)}


@app.get("/api/events/{event_id}/guests.csv")
def export_guests_csv(event_id: str) -> StreamingResponse:
    event = get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Contact", "Group", "RSVP", "Meal preference", "Dietary restrictions", "Accommodation", "Table"])
    for guest in event["guests"]:
        writer.writerow([guest["name"], guest["contact"], guest["group_category"], guest["rsvp_status"], guest["meal_preference"], guest["dietary_restrictions"], "Yes" if guest["accommodation_required"] else "No", guest["table_name"]])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=planora-guests-{event_id}.csv"})


@app.post("/api/events/{event_id}/vendors")
def post_vendor(event_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not get_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    name = str(body.get("name") or "").strip()
    category = str(body.get("category") or "").strip()
    if not name or not category:
        raise HTTPException(status_code=400, detail="name and category are required")
    try:
        price_min = max(0, float(body.get("price_min", 0)))
        price_max = max(price_min, float(body.get("price_max", price_min)))
        rating = float(body["rating"]) if body.get("rating") not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Price and rating fields must be numeric") from None
    vendor_id = make_id("vnd")
    with connection() as conn:
        conn.execute(
            """INSERT INTO vendors(id,event_id,name,category,location,contact,price_min,price_max,rating,source,verification_status,services,notes,booking_status,agreed_price)
            VALUES(?,?,?,?,?,?,?,?,?,'user-entered','user-entered',?,?, 'not_contacted',0)""",
            (vendor_id, event_id, name[:120], category[:80], str(body.get("location") or "")[:120], str(body.get("contact") or "")[:160], price_min, price_max, rating, str(body.get("services") or "")[:300], str(body.get("notes") or "")[:500]),
        )
    return {"id": vendor_id, "event": get_event(event_id), "source": "user-entered", "verification_status": "user-entered"}


@app.post("/api/events/{event_id}/vendors/search")
def post_vendor_search(event_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    result = search_vendors(event_id, str(body.get("category") or "any"), str(body.get("location") or ""), float(body.get("budget") or 0), str(body.get("preferences") or ""))
    if result.get("status") != "success":
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@app.post("/api/events/{event_id}/vendors/compare")
def post_vendor_compare(event_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    vendor_ids = body.get("vendor_ids", [])
    result = compare_vendors(json.dumps(vendor_ids))
    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail=result.get("error"))
    event = get_event(event_id)
    valid_ids = {vendor["id"] for vendor in event["vendors"]} if event else set()
    result["vendors"] = [vendor for vendor in result["vendors"] if vendor["id"] in valid_ids]
    result["comparison"] = [item for item in result["comparison"] if any(vendor["name"] == item["name"] for vendor in result["vendors"])]
    return result


@app.post("/api/events/{event_id}/ideas")
def post_ideas(event_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    result = generate_event_ideas(event_id, str(body.get("theme") or ""), float(body.get("budget") or 0))
    if result.get("status") != "success":
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@app.post("/api/events/{event_id}/schedule")
def post_schedule(event_id: str) -> dict[str, Any]:
    result = generate_event_day_schedule(event_id)
    if result.get("status") != "success":
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@app.post("/api/events/{event_id}/invitation")
def post_invitation(event_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    event = get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return generate_invitation(json.dumps(event), str(body.get("tone") or "warm"), str(body.get("language") or "English"))


@app.get("/api/events/{event_id}/report")
def get_report(event_id: str) -> dict[str, Any]:
    result = generate_event_report(event_id)
    if result.get("status") != "success":
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result["report"]


frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="planora-ui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

"""Planora's tool-using event planning agent."""

from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools import (
    calculate_budget,
    check_task_status,
    compare_vendors,
    create_event,
    generate_event_day_schedule,
    generate_event_ideas,
    generate_event_plan,
    generate_event_report,
    generate_invitation,
    generate_timeline,
    manage_guests,
    optimize_budget,
    search_vendors,
    suggest_alternatives,
    update_event,
    update_timeline,
)

INSTRUCTION = """You are Planora, a practical event planning assistant.

Use the event details and current event ID in the user's message as your working context. Select only the tools needed for the request. When details are missing, ask one concise, high-value follow-up question rather than asking a long checklist.

Planning rules:
- Use tools to create, update, calculate, and retrieve event data. Explain the result in plain language.
- Never claim an update happened unless the tool result confirms it.
- Never invent vendors, availability, ratings, contact details, reviews, or quotations. Vendor search returns user-entered records only.
- Describe category costs and concept costs as estimates, never as verified quotations.
- Keep recommendations within the stated budget and explain any trade-off.
- Preserve dietary, cultural, accessibility, and personal preferences.
- Do not send invitations, contact guests or vendors, book vendors, or make payments. Invitation tools only create a draft.
- For a requirement change, call update_event with only the changed fields. Avoid regenerating unrelated parts of the plan.
- When event_id is required by a tool, use the current event ID from the context. For JSON-string parameters, provide valid JSON text.

Available capabilities include event creation and updates, personalized plans, budget calculations and optimization, timeline generation and rescheduling, user-entered vendor search and comparison, theme ideas, guest management, invitation drafts, task status, event-day schedules, alternatives, and event reports."""


root_agent = Agent(
    name="planora_planning_agent",
    model=Gemini(
        model=os.getenv("MODEL_NAME", "gemini-flash-latest"),
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description="Tool-using event planner for budgets, timelines, ideas, guests, and event-day coordination.",
    instruction=INSTRUCTION,
    tools=[
        create_event,
        update_event,
        generate_event_plan,
        calculate_budget,
        optimize_budget,
        generate_timeline,
        update_timeline,
        search_vendors,
        compare_vendors,
        generate_event_ideas,
        manage_guests,
        generate_invitation,
        check_task_status,
        generate_event_day_schedule,
        suggest_alternatives,
        generate_event_report,
    ],
)

app = App(name="app", root_agent=root_agent)

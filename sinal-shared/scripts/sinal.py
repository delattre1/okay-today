#!/usr/bin/env python3
"""The agent's one way to touch the check-in state.

Every skill goes through these subcommands instead of writing JSON by hand, so
validation lives in one place: a handle that is not E.164, an hour that is not
HH:MM or a chat id that is not a cht_ never reach the file the unattended
watchman trusts.

  setup-family   who is checked on, and in which group
  setup-solo     the owner is the one checked on
  link-chat      record the chat id a just-created thread returned
  consent        yes or no, from the person themselves
  oncall-add     the person called when the morning answer does not come
  oncall-remove
  pause / resume a trip, a hospital stay, a week at a daughter's house
  schedule       the daily hour, or a one-off hour for tomorrow
  windows        how long each escalation step waits
  checkin        record an answer that arrived somewhere else
  resolve        someone reached them; stop the escalation
  status         what is configured and what happened today
  summary        the weekly line
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sinal_state as st  # noqa: E402


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def _require_handle(value: str) -> str:
    value = (value or "").strip()
    if not st.valid_handle(value):
        fail(f"{value!r} is not a phone number in +1... form; ask for it again rather than guessing")
    return value


def _require_time(value: str) -> str:
    value = (value or "").strip()
    if not st.valid_time(value):
        fail(f"{value!r} is not an hour in HH:MM (24h) form")
    return value


def _require_chat(value: str) -> str:
    value = (value or "").strip()
    if not st.valid_chat(value):
        fail(f"{value!r} is not a cht_ id; use the chat_id the group tool returned")
    return value


def cmd_setup_family(args, state):
    state["mode"] = "family"
    state["language"] = args.language
    state["owner"] = {"name": st.clean_name(args.owner_name), "handle": "",
                      "chat_uid": _require_chat(args.owner_chat)}
    state["watch"].update({
        "name": st.clean_name(args.name),
        "handle": _require_handle(args.handle),
        "timezone": args.timezone,
        "morning_at": _require_time(args.morning_at),
        "consent": "pending",
        "chat_uid": "",
    })
    return state, (f"Set up for {state['watch']['name']} at {state['watch']['morning_at']} "
                   f"({state['watch']['timezone']}). Next: start the group and link the chat id.")


def cmd_setup_solo(args, state):
    state["mode"] = "solo"
    state["language"] = args.language
    state["owner"] = {"name": st.clean_name(args.name), "handle": "",
                      "chat_uid": _require_chat(args.chat)}
    state["watch"].update({
        "name": st.clean_name(args.name),
        "handle": "",
        "timezone": args.timezone,
        "morning_at": _require_time(args.morning_at),
        "consent": "yes",          # the owner is the one being checked on
        "chat_uid": _require_chat(args.chat),
    })
    return state, (f"Checking in with you at {state['watch']['morning_at']} "
                   f"({state['watch']['timezone']}). Next: add the person I should tell "
                   "if a morning goes unanswered.")


def cmd_link_chat(args, state):
    state["watch"]["chat_uid"] = _require_chat(args.watch_chat)
    return state, f"Linked the check-in chat ({state['watch']['chat_uid']})."


def cmd_consent(args, state):
    value = args.value
    if args.oncall:
        handle = _require_handle(args.oncall)
        for contact in state.get("oncall") or []:
            if contact.get("handle") == handle:
                contact["consent"] = value
                return state, f"{contact.get('name') or handle} said {value}."
        fail(f"{handle} is not on the on-call list")
    state["watch"]["consent"] = value
    if value == "yes":
        return state, f"{state['watch']['name']} said yes. The morning message starts tomorrow."
    return state, (f"{state['watch']['name']} said no. Nothing will be sent. "
                   "Tell the owner, and do not ask her again.")


def cmd_oncall_add(args, state):
    handle = _require_handle(args.handle)
    entry = {"name": st.clean_name(args.name), "handle": handle,
             "chat_uid": _require_chat(args.chat_uid), "consent": "pending"}
    contacts = [c for c in (state.get("oncall") or []) if c.get("handle") != handle]
    contacts.append(entry)
    state["oncall"] = contacts[:4]
    return state, f"{entry['name']} is on the list, pending their yes."


def cmd_oncall_remove(args, state):
    handle = _require_handle(args.handle)
    before = len(state.get("oncall") or [])
    state["oncall"] = [c for c in (state.get("oncall") or []) if c.get("handle") != handle]
    if len(state["oncall"]) == before:
        fail(f"{handle} was not on the list")
    return state, "Removed."


def cmd_pause(args, state):
    now = st.utcnow()
    if args.until:
        until = st.parse_dt(args.until)
        if not until:
            fail("--until needs an ISO 8601 timestamp")
    elif args.days:
        until = now + timedelta(days=args.days)
    else:
        until = now + timedelta(hours=args.hours or 24)
    state["pause_until"] = st.fmt_dt(until)
    state["pause_reason"] = st.clean_name(args.reason, 80)
    tz = st.tzinfo_for(state)
    return state, (f"Paused until {until.astimezone(tz).strftime('%b %-d, %-I:%M %p')}"
                   f"{' (' + state['pause_reason'] + ')' if state['pause_reason'] else ''}.")


def cmd_resume(args, state):
    state["pause_until"] = None
    state["pause_reason"] = None
    return state, "Back on. The next morning message goes out at the usual time."


def cmd_schedule(args, state):
    if args.tomorrow:
        hour = _require_time(args.tomorrow)
        tz = st.tzinfo_for(state)
        day = (st.utcnow().astimezone(tz) + timedelta(days=1)).date().isoformat()
        state["override"] = {"date": day, "morning_at": hour}
        return state, f"Tomorrow only, I'll write at {hour}."
    hour = _require_time(args.morning_at)
    state["watch"]["morning_at"] = hour
    return state, f"From now on I'll write at {hour}."


def cmd_windows(args, state):
    windows = dict(state.get("windows") or st.DEFAULT_STATE["windows"])
    for key, value in (("nudge_after_min", args.nudge), ("oncall_after_min", args.oncall),
                       ("owner_after_min", args.owner)):
        if value is not None:
            if not 5 <= value <= 1440:
                fail(f"{key} has to be between 5 and 1440 minutes")
            windows[key] = value
    if not windows["nudge_after_min"] <= windows["oncall_after_min"] <= windows["owner_after_min"]:
        fail("the steps have to grow: nudge, then on-call, then owner")
    state["windows"] = windows
    return state, (f"Steps: nudge at {windows['nudge_after_min']} min, "
                   f"on-call at {windows['oncall_after_min']}, owner at {windows['owner_after_min']}.")


def cmd_checkin(args, state):
    record = state.get("today")
    if not record:
        fail("no morning message has gone out today, so there is nothing to mark")
    when = st.parse_dt(args.at) if args.at else st.utcnow()
    greeted = st.parse_dt(record.get("greeted_at"))
    record["replied_at"] = st.fmt_dt(when)
    record["minutes_to_reply"] = max(0, int((when - greeted).total_seconds() // 60))
    record["stage"] = "done"
    state["today"] = record
    return state, f"Marked as answered after {record['minutes_to_reply']} minutes."


def cmd_resolve(args, state):
    record = state.get("today")
    if not record:
        fail("nothing is open today")
    record["resolved_by"] = st.clean_name(args.by)
    record["resolved_at"] = st.fmt_dt(st.utcnow())
    record["stage"] = "done"
    state["today"] = record
    greeted = st.parse_dt(record.get("greeted_at"))
    minutes = max(0, int((st.utcnow() - greeted).total_seconds() // 60))
    return state, f"Closed by {record['resolved_by']} {minutes} minutes after the morning message."


def cmd_language(args, state):
    state["language"] = args.value
    spoken = {"en": "English", "pt": "portugues"}[args.value]
    return state, f"From now on the morning message goes out in {spoken}."


def cmd_status(args, state):
    ready, reason = st.is_configured(state)
    tz = st.tzinfo_for(state)
    record = state.get("today") or {}
    payload = {
        "ready": ready,
        "reason": reason,
        "mode": state.get("mode"),
        "language": state.get("language"),
        "watch": {k: state["watch"].get(k) for k in
                  ("name", "morning_at", "timezone", "consent", "chat_uid")},
        "oncall": [{"name": c.get("name"), "consent": c.get("consent")}
                   for c in state.get("oncall") or []],
        "paused_until": state.get("pause_until"),
        "today": record,
        "local_now": st.utcnow().astimezone(tz).isoformat(timespec="minutes"),
    }
    if args.json:
        return state, json.dumps(payload, ensure_ascii=False)
    lines = [f"{'Ready' if ready else 'Not ready'}: {reason}",
             f"Mode: {state.get('mode') or 'not set'}",
             f"Morning message language: {state.get('language')}",
             f"Checking on {state['watch'].get('name') or '(nobody yet)'} at "
             f"{state['watch'].get('morning_at')} {state['watch'].get('timezone')} "
             f"(consent: {state['watch'].get('consent')})"]
    if state.get("oncall"):
        lines.append("On call: " + ", ".join(f"{c.get('name')} ({c.get('consent')})"
                                             for c in state["oncall"]))
    if state.get("pause_until"):
        lines.append(f"Paused until {state['pause_until']}")
    if record:
        lines.append(f"Today ({record.get('date')}): greeted {record.get('greeted_at')}, "
                     f"answered {record.get('replied_at') or 'not yet'}, stage {record.get('stage')}")
    else:
        lines.append("Nothing sent yet today.")
    return state, "\n".join(lines)


def cmd_summary(args, state):
    data = st.summary(state, args.days)
    if args.json:
        return state, json.dumps(data, ensure_ascii=False)
    line = f"{data['answered']} of {data['days']} mornings answered"
    if data["median_minutes_to_reply"] is not None:
        line += f", usually within {data['median_minutes_to_reply']} minutes"
    line += f". Escalations: {data['escalations']}."
    if data["resolved_by"]:
        line += " Closed by " + ", ".join(sorted(set(data["resolved_by"]))) + "."
    return state, line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("setup-family", help="check in on someone else, in a group with the owner")
    p.add_argument("--name", required=True)
    p.add_argument("--handle", required=True, help="their phone in +1... form")
    p.add_argument("--owner-name", default="")
    p.add_argument("--owner-chat", required=True, help="the owner's own cht_ id")
    p.add_argument("--timezone", default="America/New_York")
    p.add_argument("--morning-at", default="08:30")
    p.add_argument("--language", default="en", choices=["en", "pt"])
    p.set_defaults(func=cmd_setup_family)

    p = sub.add_parser("setup-solo", help="check in on the owner themselves")
    p.add_argument("--name", required=True)
    p.add_argument("--chat", required=True, help="the owner's own cht_ id")
    p.add_argument("--timezone", default="America/New_York")
    p.add_argument("--morning-at", default="08:30")
    p.add_argument("--language", default="en", choices=["en", "pt"])
    p.set_defaults(func=cmd_setup_solo)

    p = sub.add_parser("link-chat", help="record the group's chat id after starting it")
    p.add_argument("--watch-chat", required=True)
    p.set_defaults(func=cmd_link_chat)

    p = sub.add_parser("consent", help="record a yes or a no, said by that person")
    p.add_argument("--value", required=True, choices=["yes", "no"])
    p.add_argument("--oncall", help="the on-call contact's handle, when the yes is theirs")
    p.set_defaults(func=cmd_consent)

    p = sub.add_parser("oncall-add")
    p.add_argument("--name", required=True)
    p.add_argument("--handle", required=True)
    p.add_argument("--chat-uid", required=True)
    p.set_defaults(func=cmd_oncall_add)

    p = sub.add_parser("oncall-remove")
    p.add_argument("--handle", required=True)
    p.set_defaults(func=cmd_oncall_remove)

    p = sub.add_parser("pause")
    p.add_argument("--hours", type=int)
    p.add_argument("--days", type=int)
    p.add_argument("--until")
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_pause)

    p = sub.add_parser("resume")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("schedule")
    p.add_argument("--morning-at")
    p.add_argument("--tomorrow", help="a one-off hour for tomorrow only")
    p.set_defaults(func=cmd_schedule)

    p = sub.add_parser("windows")
    p.add_argument("--nudge", type=int)
    p.add_argument("--oncall", type=int)
    p.add_argument("--owner", type=int)
    p.set_defaults(func=cmd_windows)

    p = sub.add_parser("checkin", help="record an answer that arrived somewhere else")
    p.add_argument("--at", help="ISO 8601; defaults to now")
    p.set_defaults(func=cmd_checkin)

    p = sub.add_parser("resolve", help="someone reached them; close today")
    p.add_argument("--by", required=True)
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("language", help="the language the morning message goes out in")
    p.add_argument("--value", required=True, choices=["en", "pt"])
    p.set_defaults(func=cmd_language)

    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("summary")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_summary)
    return parser


READ_ONLY = {"status", "summary"}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    state = st.load()
    state, message = args.func(args, state)
    if args.command not in READ_ONLY:
        st.save(state)
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

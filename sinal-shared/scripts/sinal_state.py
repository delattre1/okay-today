#!/usr/bin/env python3
"""The check-in state machine: one file of state, one pure decision function.

Everything the agent knows about who it checks on lives in one JSON file under
$SINAL_DIR (the image puts it at /var/lib/hermes/sinal). Two processes read it:

  * the skills, on a model turn, through sinal.py -- they write configuration,
    consent, pauses and resolutions;
  * the watchman, every 60 seconds with no model at all -- it sends the morning
    message, records the answer and walks the escalation.

`decide()` is pure: state in, (state, actions) out. No clock of its own, no
network, no file access. That is what makes the whole escalation testable
without a running agent, and it is why the watchman can crash between two ticks
without inventing an alarm: the only durable memory is the file.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

try:                                             # pragma: no cover - 3.9+
    from zoneinfo import ZoneInfo
except ImportError:                              # pragma: no cover
    ZoneInfo = None

SINAL_DIR = os.environ.get("SINAL_DIR") or "/var/lib/hermes/sinal"
STATE_PATH = os.path.join(SINAL_DIR, "state.json")

STAGES = ("greeted", "nudged", "oncall", "owner", "done")
HANDLE_RE = re.compile(r"^\+[1-9]\d{6,15}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
CHAT_RE = re.compile(r"^cht_[A-Za-z0-9_-]{1,64}$")

DEFAULT_STATE = {
    "version": 1,
    "mode": None,                  # "family" (someone else is checked on) or "solo"
    "language": "en",
    "owner": {"name": "", "handle": "", "chat_uid": ""},
    "watch": {
        "name": "",
        "handle": "",
        "chat_uid": "",            # family: the {owner, watched, agent} group; solo: the owner's own chat
        "timezone": "America/New_York",
        "morning_at": "08:30",
        "consent": "pending",      # pending | yes | no
    },
    "oncall": [],                  # [{"name", "handle", "chat_uid", "consent"}]
    "windows": {"nudge_after_min": 120, "oncall_after_min": 150, "owner_after_min": 180},
    "pause_until": None,           # UTC ISO 8601, or null
    "pause_reason": None,
    "override": None,              # one-off: {"date": "YYYY-MM-DD", "morning_at": "HH:MM"}
    "today": None,
    "history": [],                 # newest last, capped
}

HISTORY_CAP = 120


# --------------------------------------------------------------------------- io
def _atomic_write(path: str, payload: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".state-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load(path: str = None) -> dict:
    """The state as it is on disk, merged over the defaults.

    A missing file is a fresh install, not an error: the agent has to be able
    to answer "are you set up?" before anything has ever been written.
    """
    path = path or STATE_PATH
    state = json.loads(json.dumps(DEFAULT_STATE))
    try:
        with open(path, encoding="utf-8") as handle:
            stored = json.load(handle)
    except FileNotFoundError:
        return state
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"{path} is unreadable ({exc}); fix or remove it before continuing") from exc
    for key, value in stored.items():
        if isinstance(value, dict) and isinstance(state.get(key), dict):
            state[key].update(value)
        else:
            state[key] = value
    return state


def save(state: dict, path: str = None) -> None:
    _atomic_write(path or STATE_PATH, json.dumps(state, indent=1, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------- helpers
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value):
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def fmt_dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def tzinfo_for(state: dict):
    """The watched person's timezone, with a loud fallback.

    A container without tzdata would otherwise raise inside the tick loop and
    the morning message would simply never go out. UTC is wrong by hours, but
    it is wrong visibly: the owner sees the greeting land at the wrong time and
    fixes the timezone, instead of seeing nothing at all.
    """
    name = (state.get("watch") or {}).get("timezone") or "UTC"
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def clean_name(value: str, limit: int = 40) -> str:
    """A person's name, safe to paste into an outbound template.

    Names reach here from a model turn, so they are untrusted text: newlines
    and control characters are stripped rather than escaped, because the only
    thing downstream is a chat message body.
    """
    text = " ".join(str(value or "").split())
    return text[:limit]


def valid_handle(value: str) -> bool:
    return bool(HANDLE_RE.match(str(value or "").strip()))


def valid_time(value: str) -> bool:
    return bool(TIME_RE.match(str(value or "").strip()))


def valid_chat(value: str) -> bool:
    return bool(CHAT_RE.match(str(value or "").strip()))


def consented_oncall(state: dict) -> list:
    return [c for c in state.get("oncall") or []
            if c.get("consent") == "yes" and valid_chat(c.get("chat_uid") or "")]


def is_configured(state: dict) -> tuple:
    """(ready, reason). Ready means the watchman may send this person a message."""
    watch = state.get("watch") or {}
    if state.get("mode") not in ("family", "solo"):
        return False, "no mode yet: run setup in the owner's own chat"
    if not valid_chat(watch.get("chat_uid") or ""):
        return False, "no chat to write in yet"
    if watch.get("consent") != "yes":
        return False, f"consent is {watch.get('consent') or 'pending'}"
    if not valid_time(watch.get("morning_at") or ""):
        return False, "morning_at is not HH:MM"
    return True, "ready"


def morning_at_for(state: dict, day: str) -> str:
    override = state.get("override") or {}
    if override.get("date") == day and valid_time(override.get("morning_at") or ""):
        return override["morning_at"]
    return (state.get("watch") or {}).get("morning_at") or "08:30"


# ----------------------------------------------------------------------- texts
def _t(state: dict, key: str, **kw) -> str:
    language = (state.get("language") or "en").lower()
    table = TEXTS.get(language) or TEXTS["en"]
    return table[key].format(**kw)


TEXTS = {
    "en": {
        "greet": "Good morning, {name}. All good there?",
        "nudge": "{name}, just checking in. One word back and I'll leave you alone.",
        "oncall": ("{name} hasn't answered this morning's message ({greeted}). "
                   "Last heard from her {last}. Could you give her a call?"),
        "oncall_m": ("{name} hasn't answered this morning's message ({greeted}). "
                     "Last heard from him {last}. Could you give him a call?"),
        "owner": ("Still nothing from {name} since {greeted}, and no one has confirmed yet. "
                  "Worth calling now."),
        "solo_oncall": ("{owner} set me to check in every morning and asked me to tell you "
                        "if there was no answer. There's been none since {greeted}. "
                        "Could you try reaching them?"),
    },
    "pt": {
        "greet": "Bom dia, {name}. Tudo bem por aí?",
        "nudge": "{name}, só confirmando que está tudo bem. Uma palavrinha e eu paro de incomodar.",
        "oncall": ("{name} não respondeu a mensagem da manhã ({greeted}). "
                   "A última notícia dela foi {last}. Você consegue ligar para ela?"),
        "oncall_m": ("{name} não respondeu a mensagem da manhã ({greeted}). "
                     "A última notícia dele foi {last}. Você consegue ligar para ele?"),
        "owner": ("Continua sem resposta de {name} desde {greeted}, e ninguém confirmou ainda. "
                  "Vale ligar agora."),
        "solo_oncall": ("{owner} pediu para eu mandar um bom-dia todo dia e avisar você se não "
                        "houvesse resposta. Não tem resposta desde {greeted}. "
                        "Você consegue falar com {owner}?"),
    },
}


def _clock(value: datetime, tz) -> str:
    return value.astimezone(tz).strftime("%-I:%M %p") if os.name != "nt" else value.astimezone(tz).strftime("%I:%M %p")


def _last_seen_phrase(state: dict, now: datetime, tz) -> str:
    history = state.get("history") or []
    last = None
    for entry in reversed(history):
        if entry.get("replied_at"):
            last = parse_dt(entry["replied_at"])
            break
    if not last:
        return "when you set this up"
    local = last.astimezone(tz)
    days = (now.astimezone(tz).date() - local.date()).days
    when = "yesterday" if days == 1 else (local.strftime("%b %-d") if days > 1 else "today")
    return f"{when} at {_clock(last, tz)}"


# ---------------------------------------------------------------------- decide
def decide(state: dict, now: datetime, observed_reply_at: datetime = None) -> tuple:
    """One tick. Returns (state, actions); actions are {kind, chat_uid, text}.

    The caller sends the actions and only then persists the state, so a crash
    between the two costs a repeated message and never a missed alarm.
    """
    state = json.loads(json.dumps(state))
    actions = []
    tz = tzinfo_for(state)
    local = now.astimezone(tz)
    today = local.date().isoformat()

    # A finished pause is cleared here, not by whoever set it: nobody is
    # running a timer, and the first tick after the window is the event.
    pause_until = parse_dt(state.get("pause_until"))
    if pause_until and now >= pause_until:
        state["pause_until"] = None
        state["pause_reason"] = None
        pause_until = None

    ready, _reason = is_configured(state)
    if not ready:
        return state, actions

    record = state.get("today")
    if record and record.get("date") != today:
        state = _roll_day(state)
        record = None

    if pause_until:
        return state, actions

    if record is None:
        due = _greet_due_at(state, local, tz, today)
        if now < due:
            return state, actions
        # Late is not the same as due. Setting this up at noon with a 9am hour
        # used to fire "good morning" on the spot, three hours after the hour it
        # names -- and then walk an escalation over a morning that was never a
        # morning. Past the grace window the day is closed without a message;
        # the first real one goes out tomorrow, at the hour the owner chose.
        windows = state.get("windows") or DEFAULT_STATE["windows"]
        if (now - due) > timedelta(minutes=windows["nudge_after_min"]):
            state["today"] = {
                "date": today,
                "greeted_at": None,
                "replied_at": None,
                "stage": "done",
                "skipped": "set up after the hour",
                "resolved_by": None,
                "resolved_at": None,
            }
            return state, actions
        name = clean_name(state["watch"]["name"]) or "there"
        actions.append({"kind": "greet", "chat_uid": state["watch"]["chat_uid"],
                        "text": _t(state, "greet", name=name)})
        state["today"] = {
            "date": today,
            "greeted_at": fmt_dt(now),
            "replied_at": None,
            "stage": "greeted",
            "resolved_by": None,
            "resolved_at": None,
        }
        return state, actions

    if record.get("stage") == "done":
        return state, actions

    if observed_reply_at and not record.get("replied_at"):
        greeted = parse_dt(record["greeted_at"])
        record["replied_at"] = fmt_dt(observed_reply_at)
        record["minutes_to_reply"] = max(0, int((observed_reply_at - greeted).total_seconds() // 60))
        record["stage"] = "done"
        state["today"] = record
        return state, actions

    if record.get("resolved_by"):
        record["stage"] = "done"
        state["today"] = record
        return state, actions

    greeted = parse_dt(record["greeted_at"])
    elapsed = int((now - greeted).total_seconds() // 60)
    windows = state.get("windows") or DEFAULT_STATE["windows"]
    stage = record.get("stage") or "greeted"
    name = clean_name(state["watch"]["name"]) or "there"
    greeted_clock = _clock(greeted, tz)

    if stage == "greeted" and elapsed >= windows["nudge_after_min"]:
        actions.append({"kind": "nudge", "chat_uid": state["watch"]["chat_uid"],
                        "text": _t(state, "nudge", name=name)})
        stage = "nudged"

    if stage == "nudged" and elapsed >= windows["oncall_after_min"]:
        contacts = consented_oncall(state)
        if contacts:
            last = _last_seen_phrase(state, now, tz)
            for contact in contacts:
                if state.get("mode") == "solo":
                    text = _t(state, "solo_oncall",
                              owner=clean_name(state["owner"].get("name")) or name,
                              greeted=greeted_clock)
                else:
                    text = _t(state, "oncall", name=name, greeted=greeted_clock, last=last)
                actions.append({"kind": "oncall", "chat_uid": contact["chat_uid"], "text": text})
            stage = "oncall"
        else:
            # Nobody agreed to be called, so the on-call step has nothing to
            # do and the owner step is the whole escalation. Skipping the
            # stage rather than stalling in it is what keeps a solo install
            # with no contact from sitting in "nudged" forever.
            stage = "oncall"

    if stage == "oncall" and elapsed >= windows["owner_after_min"] and state.get("mode") == "family":
        owner_chat = (state.get("owner") or {}).get("chat_uid") or ""
        if valid_chat(owner_chat):
            actions.append({"kind": "owner", "chat_uid": owner_chat,
                            "text": _t(state, "owner", name=name, greeted=greeted_clock)})
        stage = "owner"

    record["stage"] = stage
    state["today"] = record
    return state, actions


def _greet_due_at(state: dict, local: datetime, tz, today: str) -> datetime:
    hour, minute = morning_at_for(state, today).split(":")
    due_local = local.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    return due_local.astimezone(timezone.utc)


def _roll_day(state: dict) -> dict:
    record = state.get("today") or {}
    if record:
        state.setdefault("history", []).append({
            "date": record.get("date"),
            "greeted_at": record.get("greeted_at"),
            "replied_at": record.get("replied_at"),
            "minutes_to_reply": record.get("minutes_to_reply"),
            "stage": record.get("stage"),
            "resolved_by": record.get("resolved_by"),
            "skipped": record.get("skipped"),
        })
        del state["history"][:-HISTORY_CAP]
    state["today"] = None
    override = state.get("override") or {}
    if override and override.get("date") and override["date"] <= (record.get("date") or ""):
        state["override"] = None
    return state


def summary(state: dict, days: int = 7) -> dict:
    """What the weekly turn reports: answered mornings, how fast, what escalated."""
    entries = list(state.get("history") or [])
    if state.get("today"):
        entries.append(state["today"])
    entries = entries[-days:]
    entries = [e for e in entries if not e.get("skipped")]
    answered = [e for e in entries if e.get("replied_at")]
    minutes = sorted(e["minutes_to_reply"] for e in answered if e.get("minutes_to_reply") is not None)
    escalated = [e for e in entries if (e.get("stage") in ("oncall", "owner"))
                 or e.get("resolved_by")]
    median = minutes[len(minutes) // 2] if minutes else None
    return {
        "days": len(entries),
        "answered": len(answered),
        "median_minutes_to_reply": median,
        "escalations": len(escalated),
        "resolved_by": [e.get("resolved_by") for e in escalated if e.get("resolved_by")],
        "paused": bool(state.get("pause_until")),
    }

#!/usr/bin/env python3
"""The unattended half of the agent: one tick every 60 seconds, no model.

What it does is deliberately small. It sends the morning message, it reads the
chat to see whether an answer came back, and it walks the escalation. It does
not interpret anything: any inbound message from the watched person counts as
an answer, so the day is safe even when the model misreads the words. The model
adds the nuance (a pause, a different hour, "she called me") by writing the
same state file through sinal.py.

Why a supervised loop and not cron: the escalation has minute-level steps, a
missed tick must cost nothing, and the whole thing has to survive a restart
with no memory of its own beyond the state file.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import timezone

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import plow_api                      # noqa: E402
import sinal_state as st             # noqa: E402

TICK_SECONDS = int(os.environ.get("SINAL_TICK_SECONDS") or 60)


def log(message: str) -> None:
    print(f"[sinal-watchman] {message}", file=sys.stderr, flush=True)


def watched_reply_at(state: dict, messages: list, since):
    """The first message from the watched person after the greeting.

    Identity comes from the role Plow puts on the sender, not from anything the
    model wrote: in a family group the watched person is the member who is not
    the owner; in a solo install the owner is the one being checked on.
    """
    mode = state.get("mode")
    earliest = None
    for message in messages:
        if message.get("direction") != "inbound":
            continue
        sender = message.get("sender") or {}
        if sender.get("type") != "member":
            continue
        role = sender.get("role")
        if mode == "solo" and role != "owner":
            continue
        if mode == "family" and role == "owner":
            continue
        if not (message.get("body") or "").strip() and not message.get("attachments"):
            continue
        created = st.parse_dt(message.get("created_at"))
        if not created or created <= since:
            continue
        if earliest is None or created < earliest:
            earliest = created
    return earliest


def tick(now=None) -> None:
    state = st.load()
    now = now or st.utcnow()

    observed = None
    record = state.get("today") or {}
    ready, _reason = st.is_configured(state)
    if ready and record and record.get("stage") not in (None, "done") and not record.get("replied_at"):
        since = st.parse_dt(record.get("greeted_at"))
        try:
            messages = plow_api.recent_messages(state["watch"]["chat_uid"])
        except plow_api.ApiError as exc:
            log(f"could not read the chat this tick ({exc.status}); trying again next tick")
            messages = []
        if since:
            observed = watched_reply_at(state, messages, since)

    state, actions = st.decide(state, now, observed)

    # Send first, persist after. A crash in between repeats a message; the
    # other order would mark a morning greeted that nobody ever received and
    # start an escalation over a message that was never sent.
    for action in actions:
        try:
            plow_api.send_message(action["chat_uid"], action["text"])
            log(f"sent {action['kind']} to {action['chat_uid']}")
        except plow_api.ApiError as exc:
            log(f"{action['kind']} to {action['chat_uid']} failed ({exc.status}); "
                "state not advanced, the next tick retries")
            return
    st.save(state)


def main() -> int:
    log(f"up, tick every {TICK_SECONDS}s, state at {st.STATE_PATH}")
    while True:
        try:
            tick()
        except Exception:                    # noqa: BLE001 - a crash here must not end the loop
            log("tick failed:\n" + traceback.format_exc())
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())

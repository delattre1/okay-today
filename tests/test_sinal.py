"""What the escalation must do, without a running agent.

The clock is an argument everywhere, so a whole day of check-ins runs in
milliseconds and the tests say the hours out loud.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sinal-shared", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "image", "sinal"))

import sinal_state as st  # noqa: E402
import watchman  # noqa: E402

NY = "America/New_York"
CLI = os.path.join(ROOT, "sinal-shared", "scripts", "sinal.py")


def at(hour, minute=0, day=12):
    """A local New York wall clock time, as UTC. September 12 is EDT, UTC-4."""
    return datetime(2026, 9, day, hour + 4, minute, tzinfo=timezone.utc)


def family_state(**over):
    state = json.loads(json.dumps(st.DEFAULT_STATE))
    state.update({"mode": "family", "language": "en",
                  "owner": {"name": "Junior", "handle": "", "chat_uid": "cht_owner"}})
    state["watch"].update({"name": "Celia", "handle": "+15551234567", "chat_uid": "cht_group",
                           "timezone": NY, "morning_at": "08:30", "consent": "yes"})
    state.update(over)
    return state


def solo_state(**over):
    state = json.loads(json.dumps(st.DEFAULT_STATE))
    state.update({"mode": "solo", "language": "en",
                  "owner": {"name": "Marcos", "handle": "", "chat_uid": "cht_me"}})
    state["watch"].update({"name": "Marcos", "handle": "", "chat_uid": "cht_me",
                           "timezone": NY, "morning_at": "09:00", "consent": "yes"})
    state.update(over)
    return state


def oncall(consent="yes"):
    return [{"name": "Ana", "handle": "+15559990000", "chat_uid": "cht_ana", "consent": consent}]


def test_nothing_happens_before_consent():
    state = family_state()
    state["watch"]["consent"] = "pending"
    _, actions = st.decide(state, at(9))
    assert actions == []


def test_nothing_happens_before_the_hour():
    _, actions = st.decide(family_state(), at(8, 29))
    assert actions == []


def test_greets_at_the_hour_once():
    state, actions = st.decide(family_state(), at(8, 30))
    assert [a["kind"] for a in actions] == ["greet"]
    assert actions[0]["chat_uid"] == "cht_group"
    assert "Celia" in actions[0]["text"]
    state, again = st.decide(state, at(8, 31))
    assert again == []
    assert state["today"]["stage"] == "greeted"


def test_an_answer_ends_the_day_in_silence():
    state, _ = st.decide(family_state(), at(8, 30))
    state, actions = st.decide(state, at(8, 41), observed_reply_at=at(8, 40))
    assert actions == []
    assert state["today"]["stage"] == "done"
    assert state["today"]["minutes_to_reply"] == 10


def test_no_answer_walks_the_three_steps():
    state = family_state(oncall=oncall())
    state, _ = st.decide(state, at(8, 30))
    state, quiet = st.decide(state, at(10, 29))
    assert quiet == []
    state, nudge = st.decide(state, at(10, 30))          # 120 min
    assert [a["kind"] for a in nudge] == ["nudge"]
    assert nudge[0]["chat_uid"] == "cht_group"
    state, call = st.decide(state, at(11, 0))            # 150 min
    assert [a["kind"] for a in call] == ["oncall"]
    assert call[0]["chat_uid"] == "cht_ana"
    assert "8:30" in call[0]["text"]
    state, owner = st.decide(state, at(11, 30))          # 180 min
    assert [a["kind"] for a in owner] == ["owner"]
    assert owner[0]["chat_uid"] == "cht_owner"
    assert state["today"]["stage"] == "owner"


def test_an_answer_after_the_alarm_still_closes_it():
    state = family_state(oncall=oncall())
    state, _ = st.decide(state, at(8, 30))
    state, _ = st.decide(state, at(11, 0))
    state, actions = st.decide(state, at(11, 10), observed_reply_at=at(11, 9))
    assert actions == []
    assert state["today"]["stage"] == "done"
    state, more = st.decide(state, at(11, 30))
    assert more == []


def test_resolved_by_a_person_stops_the_escalation():
    state = family_state(oncall=oncall())
    state, _ = st.decide(state, at(8, 30))
    state, _ = st.decide(state, at(11, 0))
    state["today"]["resolved_by"] = "Ana"
    state, actions = st.decide(state, at(11, 30))
    assert actions == []
    assert state["today"]["stage"] == "done"


def test_without_a_consented_contact_it_goes_to_the_owner():
    state = family_state(oncall=oncall(consent="pending"))
    state, _ = st.decide(state, at(8, 30))
    state, _ = st.decide(state, at(10, 30))
    state, call = st.decide(state, at(11, 0))
    assert call == []
    state, owner = st.decide(state, at(11, 30))
    assert [a["kind"] for a in owner] == ["owner"]


def test_solo_tells_the_emergency_contact_and_stops_there():
    state = solo_state(oncall=oncall())
    state, greet = st.decide(state, at(9, 0))
    assert greet[0]["chat_uid"] == "cht_me"
    state, _ = st.decide(state, at(11, 0))
    state, call = st.decide(state, at(11, 30))
    assert [a["kind"] for a in call] == ["oncall"]
    assert "Marcos" in call[0]["text"]
    state, nothing = st.decide(state, at(12, 0))
    assert nothing == []


def test_a_pause_keeps_the_morning_quiet_and_then_comes_back():
    state = family_state()
    state["pause_until"] = st.fmt_dt(at(8, 0, day=14))
    state, quiet = st.decide(state, at(8, 30, day=12))
    assert quiet == []
    state, quiet = st.decide(state, at(8, 30, day=13))
    assert quiet == []
    state, back = st.decide(state, at(8, 30, day=14))
    assert [a["kind"] for a in back] == ["greet"]
    assert state["pause_until"] is None


def test_a_new_day_files_the_old_one_and_starts_clean():
    state = family_state()
    state, _ = st.decide(state, at(8, 30))
    state, _ = st.decide(state, at(8, 45), observed_reply_at=at(8, 44))
    state, actions = st.decide(state, at(8, 30, day=13))
    assert [a["kind"] for a in actions] == ["greet"]
    assert len(state["history"]) == 1
    assert state["history"][0]["minutes_to_reply"] == 14
    assert state["today"]["date"] == "2026-09-13"


def test_a_one_off_hour_applies_to_that_day_only():
    state = family_state(override={"date": "2026-09-12", "morning_at": "11:00"})
    state, early = st.decide(state, at(8, 30))
    assert early == []
    state, late = st.decide(state, at(11, 0))
    assert [a["kind"] for a in late] == ["greet"]


def test_the_weekly_line_counts_what_happened():
    state = family_state()
    for day in (10, 11, 12):
        state, _ = st.decide(state, at(8, 30, day=day))
        state, _ = st.decide(state, at(8, 40, day=day), observed_reply_at=at(8, 39, day=day))
    data = st.summary(state, days=7)
    assert data["answered"] == 3
    assert data["median_minutes_to_reply"] == 9


# ------------------------------------------------------------------ watchman
def message(role, body="ok", minutes=5, direction="inbound", kind="member"):
    return {"uid": f"msg_{role}_{minutes}", "direction": direction, "body": body,
            "attachments": [], "created_at": st.fmt_dt(at(8, 30) + timedelta(minutes=minutes)),
            "sender": {"type": kind, "uid": f"mem_{role}", "role": role, "display_name": role}}


def test_watchman_reads_the_watched_person_and_ignores_the_rest():
    state = family_state()
    since = at(8, 30)
    messages = [message("owner", "did she answer?", 3),
                message("member", "bom dia filho", 7),
                message("member", "", 8),
                message("member", "echo", 9, direction="outbound")]
    assert watchman.watched_reply_at(state, messages, since) == at(8, 37)


def test_watchman_in_solo_mode_listens_to_the_owner():
    state = solo_state()
    messages = [message("member", "hi", 4), message("owner", "up and about", 6)]
    assert watchman.watched_reply_at(state, messages, at(8, 30)) == at(8, 36)


def test_watchman_ignores_anything_before_the_greeting():
    state = family_state()
    messages = [message("member", "from yesterday", -60)]
    assert watchman.watched_reply_at(state, messages, at(8, 30)) is None


# ----------------------------------------------------------------------- cli
def run_cli(tmp_path, *args):
    env = dict(os.environ, SINAL_DIR=str(tmp_path))
    return subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True, env=env)


def test_cli_sets_up_a_family_and_reports_ready(tmp_path):
    assert run_cli(tmp_path, "setup-family", "--name", "Celia", "--handle", "+15551234567",
                   "--owner-name", "Junior", "--owner-chat", "cht_owner",
                   "--timezone", NY, "--morning-at", "08:30").returncode == 0
    assert run_cli(tmp_path, "link-chat", "--watch-chat", "cht_group").returncode == 0
    assert run_cli(tmp_path, "consent", "--value", "yes").returncode == 0
    status = run_cli(tmp_path, "status", "--json")
    payload = json.loads(status.stdout)
    assert payload["ready"] is True
    assert payload["watch"]["consent"] == "yes"


def test_cli_refuses_a_handle_that_is_not_a_phone_number(tmp_path):
    result = run_cli(tmp_path, "setup-family", "--name", "Celia", "--handle", "mom",
                     "--owner-chat", "cht_owner")
    assert result.returncode == 2
    assert "not a phone number" in result.stderr


def test_cli_refuses_out_of_order_escalation_windows(tmp_path):
    run_cli(tmp_path, "setup-solo", "--name", "Marcos", "--chat", "cht_me")
    result = run_cli(tmp_path, "windows", "--nudge", "200", "--oncall", "100")
    assert result.returncode == 2


def test_cli_pause_and_resume_round_trip(tmp_path):
    run_cli(tmp_path, "setup-solo", "--name", "Marcos", "--chat", "cht_me")
    assert run_cli(tmp_path, "pause", "--days", "3", "--reason", "trip").returncode == 0
    state = st.load(os.path.join(tmp_path, "state.json"))
    assert state["pause_until"] and state["pause_reason"] == "trip"
    assert run_cli(tmp_path, "resume").returncode == 0
    state = st.load(os.path.join(tmp_path, "state.json"))
    assert state["pause_until"] is None


def test_state_file_is_owner_only(tmp_path):
    run_cli(tmp_path, "setup-solo", "--name", "Marcos", "--chat", "cht_me")
    path = os.path.join(tmp_path, "state.json")
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


# --------------------------------------------------- the runtime's own scanner
# Hermes scans SOUL.md and the other context files for prompt-injection and C2
# patterns and REPLACES the whole file when one matches (agent/prompt_builder.py
# through tools/threat_patterns.py). It is not a warning: the agent loses its
# entire persona and falls back to the base image's, which is how this project
# spent an hour on 12/09 watching a check-in agent introduce itself as a general
# Mac assistant. These are the patterns from that file that ordinary English can
# trip over, and "check in with" is the one that bit us.
BLOCKING_PATTERNS = [
    (r"(heartbeat|beacon|check[\s\-]?in)\s+(to|with)\s+", "c2_heartbeat"),
    (r"register\s+(as\s+)?a?\s*node", "c2_node_registration"),
    (r"pull\s+(down\s+)?(?:new\s+)?task(?:ing|s)?\b", "c2_task_pull"),
    (r"connect\s+to\s+the\s+network\b", "c2_network_connect"),
    (r"you\s+are\s+(?:\w+\s+){0,8}now\s+(?:a|an|the)\s+", "role_hijack"),
    (r"\bname\s+yourself\s+\w+", "identity_override"),
    (r"only\s+use\s+one[\s\-]?liners?\b", "anti_forensic_oneliner"),
    (r"\bcommand\s+and\s+control\b", "c2_explicit_long"),
]

CONTEXT_FILES = [
    "runtime/persona.md",
    "sinal-setup/SKILL.md",
    "sinal-replies/SKILL.md",
    "sinal-weekly/SKILL.md",
    "sinal-shared/SKILL.md",
]


def test_nothing_we_ship_trips_the_runtime_threat_scanner():
    for relative in CONTEXT_FILES:
        text = open(os.path.join(ROOT, relative), encoding="utf-8").read().lower()
        for pattern, name in BLOCKING_PATTERNS:
            assert not re.search(pattern, text), (
                f"{relative} matches {name}: Hermes would drop the whole file and the agent "
                "would answer with the base image's persona instead of ours"
            )


def test_setting_it_up_after_the_hour_does_not_fake_a_morning():
    """Configured at noon, with the hour set to 8:30: no message, no alarm."""
    state = family_state()
    state, actions = st.decide(state, at(12, 0))
    assert actions == []
    assert state["today"]["stage"] == "done"
    assert state["today"]["skipped"]
    state, later = st.decide(state, at(14, 0))
    assert later == []


def test_a_skipped_day_greets_normally_the_next_morning():
    state = family_state()
    state, _ = st.decide(state, at(12, 0))
    state, actions = st.decide(state, at(8, 30, day=13))
    assert [a["kind"] for a in actions] == ["greet"]


def test_a_greeting_a_little_late_still_goes_out():
    """A tick that fires 40 minutes late (a restart, a slow boot) is still today."""
    state = family_state()
    state, actions = st.decide(state, at(9, 10))
    assert [a["kind"] for a in actions] == ["greet"]


def test_a_skipped_day_is_not_counted_as_answered():
    state = family_state()
    state, _ = st.decide(state, at(12, 0))
    state, _ = st.decide(state, at(8, 30, day=13))
    state, _ = st.decide(state, at(8, 40, day=13), observed_reply_at=at(8, 39, day=13))
    data = st.summary(state, days=7)
    assert data["days"] == 1 and data["answered"] == 1


def test_the_command_the_skills_call_is_installed_by_the_image():
    """Skills and persona say `sinal`, and the image has to put that command
    somewhere the agent can run. The wrapper runs the image's own copy, not the
    one under the agent's home: the home copy loses its executable bit on the way
    in, and it belongs to the agent's uid, so it is a file one injected turn
    could rewrite into anything and have every later turn run it."""
    wrapper = os.path.join(ROOT, "image", "bin", "sinal")
    assert os.path.exists(wrapper), "image/bin/sinal is the command every skill calls"
    with open(wrapper, encoding="utf-8") as handle:
        body = handle.read()
    assert body.startswith("#!"), "the wrapper needs a shebang"
    assert os.access(wrapper, os.X_OK), "the wrapper has to be executable in the repo"
    assert "/opt/hermes/skills/sinal-shared/scripts/sinal.py" in body, (
        "the wrapper must run the image's root-owned copy of the tool"
    )
    dockerfile = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    assert "/usr/local/bin/sinal" in dockerfile, "the image has to install the command"


def test_no_skill_calls_the_tool_by_a_path_under_the_agents_home():
    """The bit that makes a .py runnable does not survive the copy into the
    agent's home, and nothing about that failure is visible: the service keeps
    sending the morning message while every command a person triggers answers
    Permission denied. A path here is that bug coming back."""
    home_path = "/var/lib/hermes/skills/sinal-shared/scripts/sinal.py"
    for relative in ("runtime/persona.md", "sinal-setup/SKILL.md",
                     "sinal-replies/SKILL.md", "sinal-weekly/SKILL.md",
                     "sinal-shared/SKILL.md"):
        text = open(os.path.join(ROOT, relative), encoding="utf-8").read()
        assert home_path not in text, (
            f"{relative} calls the tool by its path under the agent's home; "
            "say `sinal` instead, which the image installs on the PATH"
        )

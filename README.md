# Sinal de Vida

A daily check-in you can text. It says good morning to one person who lives
alone, and it stays quiet when they answer. When a morning goes unanswered, it
nudges once, then tells the person who agreed to be called, then the owner.

Nobody installs an app. The person being checked on answers in the thread they
already use, in their own words, and can pause it or stop it at any time.

**What it is not.** Not an emergency service. It cannot detect a fall, call an
ambulance, or tell anyone that someone is safe. The promise is narrower and it
is the whole point: nobody goes a day without being noticed.

## Two shapes

**Family.** An adult child installs it, and the agent lives in a group with them
and their parent. A sibling, or the owner, is on call when a morning goes
unanswered.

**Solo.** The person who lives alone installs it for themselves and names one
emergency contact.

## Consent and privacy

- The owner tells the person first. The agent then asks, in that person's own
  chat, and sends nothing until they answer yes. A no ends it, permanently.
- The group is created with **discretion**, never full trust, so no one in it
  can reach the owner's connected accounts or recall his other chats.
- The on-call contact agrees separately, in their own thread, and hears from the
  agent only when a morning goes unanswered.
- What is stored: names, the phone numbers of people who agreed, the hour, the
  timezone, and for each morning whether it was answered and how long it took.
  No health data, no location, no copies of what anyone said.
- The person being checked on is in charge of their own check-in. Pause, change
  the hour or stop, and the agent does it immediately without asking the owner.

## How it works

A supervised service ticks once a minute with no model in the loop: it sends the
morning message, reads the chat to see whether an answer came back, and walks
the escalation. Any inbound message from the watched person counts as an answer,
so a misread word never turns into a false alarm. The model adds the nuance
(a trip, a different hour, "I talked to her") by writing the same state file
through one validated tool.

| File | What it is |
| --- | --- |
| `runtime/persona.md` | who the agent is, and what it never promises |
| `sinal-setup/` | setup, in the owner's own chat only |
| `sinal-replies/` | every message in the check-in group or an on-call chat |
| `sinal-weekly/` | the Sunday line to the owner |
| `sinal-shared/scripts/sinal_state.py` | the state machine, pure and tested |
| `sinal-shared/scripts/sinal.py` | the only sanctioned way to change the state |
| `image/sinal/watchman.py` | the unattended tick, root-owned in the image |

Install it: [docs/INSTALL.md](docs/INSTALL.md). Tests: `just test`, or
`python3 tests/run_tests.py` with no network.

Apache-2.0. Built on the Plow cloud agent base image and Plow Chat.

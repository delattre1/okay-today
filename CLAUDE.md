# Okay Today, for whoever picks this up next

A daily check-in agent for the AI Worth Using x Hermes hackathon (submission
16/09/2026, leaderboard snapshot 22/09). Built on the Plow cloud agent base
image, Plow Chat and the Agent Index client.

## The one rule

The state file is the memory. The morning message is sent by a service, not by a
model turn, so a conversation never remembers sending it. Every skill reads
`sinal status --json` before answering, and changes
state only through that tool.

## Shape of the thing

- `sinal_state.py` holds `decide(state, now, observed_reply_at)`, pure: state in,
  (state, actions) out. All escalation logic lives there and is covered by
  `tests/test_sinal.py` (21 tests, no network needed: `python3 tests/run_tests.py`).
- `watchman.py` is the only caller of `decide` in production. It ticks every 60s
  under s6, sends actions **before** persisting state (a crash repeats a message
  rather than inventing an alarm), and identifies the watched person by the role
  Plow puts on the sender, never by anything the model wrote.
- `plow_api.py` makes the two calls the watchman needs, refusing redirects so the
  bearer cannot be walked to another host.
- Skills are prose, not code: `sinal-setup` (owner's chat only), `sinal-replies`,
  `sinal-weekly`.

## Things that will bite you

- A group started by the owner defaults to **full trust** in newer plugin
  versions. Always pass `trusted=false`; the README of the plugin explains what
  full trust hands to members.
- A chat's session is born on its first inbound message. The consent ask has to
  invite a reply, or the thread has no memory at all.
- Member turns cannot send to another chat. Anything that has to reach a second
  person goes through the watchman, not through a turn.
- An install that never spends a model token reports as "pending" to the Agent
  Index and does not count as a user. The daily answer is what keeps a real
  install visible; do not "optimise" the reply turn away.
- `plow-agents mint` writes `./plow-credentials`, a live bearer. It is in
  `.gitignore` and `.dockerignore`; keep it that way.

## Next steps, in order

1. Build and run locally, set up with two phones (one plays the parent).
2. Register the id once: `agent_index_client.py --register --agent <id> --name
   "<name>" --blurb "<one line>"`, then set `AGENT_ID` in compose.
3. Ask for verification on the Index page (opens 14/09), then publish the page
   with a video, images and a first-person story with a number in it.
4. Recruit real installs for 16 to 22/09.

---
name: sinal-shared
description: The check-in state tool and the Plow API helpers every other check-in skill calls. Not a skill to run on its own.
---

# The state tool

`scripts/sinal.py` is the only sanctioned way to read or change the check-in
state. `scripts/sinal_state.py` holds the state machine (it is the same file the
unattended watchman runs from its own root-owned copy) and `scripts/plow_api.py`
holds the two Plow Chat calls the watchman makes without a model turn.

Read: `sinal.py status --json`, `sinal.py summary --days 7 --json`.

Write: `setup-family`, `setup-solo`, `link-chat`, `consent`, `oncall-add`,
`oncall-remove`, `pause`, `resume`, `schedule`, `windows`, `checkin`, `resolve`.
Each one validates before it writes: a phone that is not +1 form, an hour that is
not HH:MM and a chat id that is not `cht_` are refused rather than stored.

Never write the state file directly. The watchman trusts it to decide whether a
family gets woken up.

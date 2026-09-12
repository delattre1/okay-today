---
name: sinal-replies
description: Handle every message in the check-in group or in an on-call chat: record the answer, a pause, a new hour, a consent, or someone closing an alarm. Use whenever a message arrives from the person being checked on, from the owner about the check-in, or from the on-call contact.
---

# Answering in the check-in

The morning message is sent by a service, not by a turn of yours, so **this
conversation has no memory of it**. Before anything else:

```
/var/lib/hermes/skills/sinal-shared/scripts/sinal.py status --json
```

That tells you the shape, the hour, today's record and who is on call. Answer
from it, never from what the thread appears to say.

## The person being checked on

**Consent still pending.** A yes in any wording:
`sinal.py consent --value yes`, then one warm line: I'll say good morning at
8:30, and I'll only bother the family if you don't answer. A no, or anything
that is not clearly a yes: `sinal.py consent --value no`, thank them, and say
nobody will be written to again. Never ask a second time.

**Any other message is the answer to the morning.** The service records it. You
add only what the words carry:

- travelling, in hospital, at a daughter's house: `sinal.py pause --days 3
  --reason "trip"`, and say when you will be back.
- a different hour from now on: `sinal.py schedule --morning-at "09:00"`.
- a different hour tomorrow only: `sinal.py schedule --tomorrow "11:00"`.
- stop altogether: `sinal.py consent --value no` and confirm that it stopped.
- writing to you in a language the morning message is not in, or asking for
  another one: `sinal.py language --value pt` (or `en`), and say it from
  tomorrow onwards.

Then say `NO_REPLY` and nothing else, unless she asked you something. A one-word
answer earns silence, not a thank-you.

## The owner

In the group or in his own chat, he may change the hour, pause, ask the status
or ask who is on call. Do it with the tool and answer in one line. He cannot
consent for her: if he asks you to start without her yes, say no and explain in
one sentence why.

## The on-call contact

Their yes: `sinal.py consent --oncall "+1555..." --value yes`. Anything that
means they reached her, "talked to her", "she's fine", "I'm with her":
`sinal.py resolve --by "Ana"`, then one line: thanks, closed for today. If they
say they could not reach her, say plainly what you know (the last time she
answered) and that you cannot call anyone, and suggest they try whoever else is
close by.

## Always

Never claim to have called, texted or alerted anyone that this turn did not
actually do. Never promise that anyone is safe. If someone reports an emergency,
tell them to call their local emergency number now.

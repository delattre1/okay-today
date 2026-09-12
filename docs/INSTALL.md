# Install

You need a Mac or Linux machine that stays awake, Docker, Git and Python 3, and
a Plow account on the phone you text from.

## 1. The Plow CLI and a line

```sh
git clone https://github.com/plow-pbc/plow-agents.git
export PATH="$PWD/plow-agents/bin:$PATH"
plow-agents login          # text the printed phrase from your phone
plow-agents lines          # pick a free line, or: plow-agents login --new-line
```

## 2. This agent

```sh
git clone https://github.com/<you>/sinal-de-vida.git
cd sinal-de-vida
plow-agents mint ln_xxx    # writes ./plow-credentials, never commit it
docker compose up --build -d
docker compose logs -f agent   # wait for: plow-init: configured ... as cht_
```

The first build takes a few minutes. If the base image pull returns 403, run
`docker logout public.ecr.aws` and build again. On Apple Silicon, turn on
Settings, General, "Use Rosetta for x86_64/amd64 emulation".

## 3. Set it up by text

Text your line. Say who lives alone: your mother, your father, or you. The agent
asks for a name, a phone number in +1 form, the city and the hour, and who
should be called if a morning goes unanswered.

It will ask you to tell that person first, in your own words. Then it starts a
group with the two of you and asks for her yes. Nothing is sent to her before
that, and nothing at all is sent to the on-call contact until they agree too.

## 4. Day to day

- She answers the morning message and the agent says nothing. That is the normal
  day.
- "I'm travelling until Sunday" pauses it. "Send at 9" changes the hour.
- "Status" tells you what is configured and what happened today.
- Sunday evening you get one line about the week.

## Running it for a family that has no Mac

The cloud deploy button on the agent's Index page does this without Docker: the
installer texts the number on the page and Plow runs their own copy. Use that
for anyone who is not going to keep a computer awake.

## Stopping

```sh
plow-agents revoke
docker compose down -v
```

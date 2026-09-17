# Sinal de Vida, built for the Plow cloud image.
#
# The base tag is an immutable `base-<sha>` naming one commit of
# plow-pbc/plow-hermes-agent, pinned by digest as well: every install of this
# agent runs while holding that owner's Plow credential, so a moving tag would
# substitute code underneath them.
FROM public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-51f83158a70a383f03a4d03dbd8b6ea102cf0361@sha256:253d7ed3409effa7fa59113d93b4b79bb731d8264cdaf4cd60294924d0110a2e

# Identity. plow-init composes SOUL.md at boot as the base persona followed by
# this file; nothing here restates what the base already carries.
COPY --chmod=0644 runtime/persona.md /opt/hermes/plow-seed/persona.md
COPY LICENSE NOTICE /usr/share/doc/sinal-de-vida/

# The skills, outside every home, so a bind-mounted home still gets them and an
# image update still reaches a skill the agent has not customised.
COPY sinal-setup/    /opt/hermes/skills/sinal-setup/
COPY sinal-replies/  /opt/hermes/skills/sinal-replies/
COPY sinal-weekly/   /opt/hermes/skills/sinal-weekly/
COPY sinal-shared/   /opt/hermes/skills/sinal-shared/

RUN find /opt/hermes/skills -mindepth 1 -type d -exec chmod 0755 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f ! -perm -u+x -exec chmod 0644 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f -perm -u+x -exec chmod 0755 {} +

# The unattended half, root-owned and out of the agent's reach. What the
# supervisor runs every 60 seconds must not be a file a model turn can rewrite:
# everything under $HERMES_HOME/skills belongs to the agent's uid, so scheduling
# that copy would turn one prompt injection into code that runs forever holding
# this household's credential. The home copy stays exactly as it is; only the
# SERVICE points here.
COPY sinal-shared/scripts/sinal_state.py sinal-shared/scripts/plow_api.py /opt/plow/sinal/
COPY image/sinal/watchman.py /opt/plow/sinal/
RUN chown -R root:root /opt/plow \
 && find /opt/plow -type d -exec chmod 0755 {} + \
 && find /opt/plow -type f -exec chmod 0644 {} +

# The usage reporter, fetched at build from the commit vendor/client.pin names
# and checked against the hash beside it. A sha in a URL is only as good as the
# host serving it, and this file runs inside an agent holding a live credential.
COPY vendor/client.pin /opt/plow/agent-index-client.pin
RUN set -eu; \
    sha="$(sed -n 's/^sha=//p' /opt/plow/agent-index-client.pin)"; \
    want="$(sed -n 's/^sha256=//p' /opt/plow/agent-index-client.pin)"; \
    path="$(sed -n 's/^path=//p' /opt/plow/agent-index-client.pin)"; \
    curl -fsS --max-time 60 -o /opt/plow/agent-index-client.py \
      "https://raw.githubusercontent.com/plow-pbc/agent-index-client/${sha}/${path}"; \
    got="$(sha256sum /opt/plow/agent-index-client.py | cut -d' ' -f1)"; \
    [ "$got" = "$want" ] || { echo "agent-index client is $got, pin says $want" >&2; exit 1; }; \
    chmod 0644 /opt/plow/agent-index-client.py

# The command the skills and the persona call. Installed by the image, on the
# PATH in two standard places, running the image's own copy of the tool: the
# runtime strips the executable bit off skill files on their way into the
# agent's home, and a .py under that home is a file a turn could rewrite.
COPY --chmod=0755 image/bin/sinal /usr/local/bin/sinal
RUN ln -sf /usr/local/bin/sinal /usr/bin/sinal

COPY image/s6-overlay/ /etc/s6-overlay/

# The state directory: agent-owned, 0700, empty until setup runs. An unset-up
# agent is routed to sinal-setup by the persona.
RUN install -d -o 10000 -g 10000 -m 0700 /var/lib/hermes/sinal

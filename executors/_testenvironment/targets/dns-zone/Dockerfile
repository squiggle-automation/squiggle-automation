# Deterministic, authoritative-only DNS target.
# Serves the static "test.local" zone below - no recursion, no internet access needed.

FROM debian:trixie

RUN apt-get update && apt-get install -y bind9 && apt-get clean

COPY named.conf /etc/bind/named.conf
COPY zones/ /etc/bind/zones/

EXPOSE 53/udp 53/tcp

CMD ["named", "-g", "-c", "/etc/bind/named.conf"]

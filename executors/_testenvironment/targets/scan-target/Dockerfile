# Deterministic scan target: TCP 80 and 8443 open, everything else closed.

FROM debian:trixie

RUN apt-get update && apt-get install -y socat && apt-get clean

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80/tcp 8443/tcp

CMD ["/start.sh"]

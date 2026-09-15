# Deterministic TLS target: presents a self-signed cert with a known CN and SAN list, so
# tools that read certificate data (tlsx, nmap's ssl tunnel detection) have something fixed
# to extract.

FROM debian:trixie

RUN apt-get update && apt-get install -y socat openssl && apt-get clean

RUN openssl req -x509 -newkey rsa:2048 -keyout /etc/tls-target.key -out /etc/tls-target.crt \
        -days 3650 -nodes -subj "/CN=tls-target.test.local" \
        -addext "subjectAltName=DNS:tls-target.test.local,DNS:alt1.test.local,DNS:alt2.test.local" && \
    cat /etc/tls-target.key /etc/tls-target.crt > /etc/tls-target.pem

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8443/tcp

CMD ["/start.sh"]

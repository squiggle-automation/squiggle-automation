FROM quay.io/squiggle-automation/executor-base

ARG TARGETARCH

COPY entrypoint.py /root/entrypoint.py

RUN mkdir /tmp/dnsx && \
    cd /tmp/dnsx && \
    curl --location -o dnsx.zip $(curl -s https://api.github.com/repos/projectdiscovery/dnsx/releases/latest | jq -r '.assets[].browser_download_url' | grep "linux_$TARGETARCH\.zip\$") && \
    unzip dnsx.zip && \
    cp dnsx /root/dnsx && \
    chmod +x /root/dnsx && \
    rm -rf /tmp/dnsx

CMD ["/root/entrypoint.py"]

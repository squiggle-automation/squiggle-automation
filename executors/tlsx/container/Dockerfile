FROM quay.io/squiggle-automation/executor-base

ARG TARGETARCH

COPY entrypoint.py /root/entrypoint.py

RUN mkdir /tmp/tlsx && \
    cd /tmp/tlsx && \
    curl --location -o tlsx.zip $(curl -s https://api.github.com/repos/projectdiscovery/tlsx/releases/latest | jq -r '.assets[].browser_download_url' | grep linux_$TARGETARCH) && \
    unzip tlsx.zip && \
    cp tlsx /root/tlsx && \
    chmod +x /root/tlsx && \
    rm -rf /tmp/tlsx

CMD ["/root/entrypoint.py"]

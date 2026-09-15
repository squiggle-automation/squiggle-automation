FROM quay.io/squiggle-automation/executor-base

ARG TARGETARCH

COPY entrypoint.py /root/entrypoint.py

RUN mkdir /tmp/subfinder && \
    cd /tmp/subfinder && \
    curl --location -o subfinder.zip $(curl -s https://api.github.com/repos/projectdiscovery/subfinder/releases/latest | jq -r '.assets[].browser_download_url' | grep linux_$TARGETARCH) && \
    unzip subfinder.zip && \
    cp subfinder /root/subfinder && \
    chmod +x /root/subfinder && \
    rm -rf /tmp/subfinder

CMD ["/root/entrypoint.py"]

FROM debian:trixie

RUN apt update && apt install -y jq python3 python3-pip wget curl unzip && apt clean

COPY executor_helper /root/executor_helper
RUN cd /root/executor_helper && pip install --break-system-packages --root-user-action ignore . && rm -rf /root/executor_helper

COPY entrypoint.py /root/entrypoint.py

CMD ["/root/entrypoint.py"]

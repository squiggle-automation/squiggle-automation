FROM quay.io/squiggle-automation/executor-base

RUN apt update && apt install -y nmap && apt clean

COPY entrypoint.py /root/entrypoint.py

CMD ["/root/entrypoint.py"]

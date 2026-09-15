FROM python:3.13-slim

# build-essential is needed to compile uwsgi (no prebuilt wheel on pypi)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY . /app/src
COPY .env.container /app/src/.env
WORKDIR /app/src

RUN pip install --no-cache-dir -r requirements.txt -r requirements-prod.txt

RUN chmod +x docker-entrypoint.sh

RUN mkdir -p /data/artifacts /data/tmp

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["app"]

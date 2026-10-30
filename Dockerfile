# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/London
WORKDIR /app
COPY requirements.txt ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt \
    && test -f /usr/share/zoneinfo/Europe/London && dpkg-query -W tzdata \
    && groupadd --gid 10001 rail \
    && useradd --uid 10001 --gid rail --no-create-home rail \
    && mkdir /data && chown rail:rail /data
COPY --chown=10001:10001 app ./app
USER rail
EXPOSE 8097
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/api/health', timeout=3)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8097", "--no-access-log", "--log-config", "app/logging.json"]

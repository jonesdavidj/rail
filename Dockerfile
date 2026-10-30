FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/London
WORKDIR /app
RUN test -f /usr/share/zoneinfo/Europe/London \
    && dpkg-query -W tzdata \
    && groupadd --gid 10001 rail \
    && useradd --uid 10001 --gid rail --no-create-home rail \
    && mkdir /data && chown rail:rail /data
COPY --chown=rail:rail app /app/app
USER rail
EXPOSE 8097
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/api/health', timeout=2).close()"]
CMD ["python", "-m", "app.main"]

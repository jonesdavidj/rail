FROM python:3.12-slim
# tzdata: the slim image has no zoneinfo database
RUN pip install --no-cache-dir tzdata && useradd --system --no-create-home trains
WORKDIR /app
COPY server.py ./
COPY static ./static
USER trains
ENV PORT=8099
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
  CMD python3 -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/api/health'%os.environ.get('PORT','8099'),timeout=4)"
CMD ["python3", "-I", "server.py"]

FROM python:3.13-slim

WORKDIR /app
COPY . .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

ENV PORT=8080
ENV HOST=0.0.0.0
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import json, urllib.request; json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3))"

CMD ["python3", "server.py"]

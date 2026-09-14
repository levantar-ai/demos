# AgentCore Runtime requires linux/arm64 images (built with --platform linux/arm64)
FROM python:3.12-slim

# Unbuffered stdout so print() reaches CloudWatch immediately
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir boto3==1.43.63 mcp==1.29.0

WORKDIR /app
COPY main.py .
COPY gateway.py .
COPY memory.py .
COPY identity.py .

EXPOSE 8080
USER nobody
# The runtime's own health check is GET /ping; this mirrors it for anything
# that reads the image's HEALTHCHECK, with nothing but the standard library.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ping', timeout=2)"]
CMD ["python", "main.py"]

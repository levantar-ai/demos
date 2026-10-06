# AgentCore Runtime requires linux/arm64 images (built with --platform linux/arm64)
FROM python:3.12-slim

# Unbuffered stdout so print() reaches CloudWatch immediately
ENV PYTHONUNBUFFERED=1

# strands-agents brings the MCP client with it; bedrock-agentcore brings the
# memory session manager. Both pinned, as everything else in the series.
RUN pip install --no-cache-dir boto3==1.43.108 strands-agents==1.57.2 bedrock-agentcore==1.24.0

WORKDIR /app
COPY main.py model.py gateway.py identity.py memory.py sandbox.py trail.py handoff.py ./

EXPOSE 8080
USER nobody
# The runtime's own health check is GET /ping; this mirrors it for anything
# that reads the image's HEALTHCHECK, with nothing but the standard library.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ping', timeout=2)"]
CMD ["python", "main.py"]

# AgentCore Runtime requires linux/arm64 images (built with --platform linux/arm64).
# The base image is pinned by digest (python:3.12-slim as of 2026-10-07), so a
# rebuild starts from the same bytes; the packages below are pinned by version,
# not by hash, which the README notes.
FROM python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

# Unbuffered stdout so print() reaches CloudWatch immediately
ENV PYTHONUNBUFFERED=1

# strands-agents brings the MCP client with it; bedrock-agentcore brings the
# memory session manager and, from this post, the server (BedrockAgentCoreApp,
# on Starlette and uvicorn, which it installs); aws-opentelemetry-distro
# (ADOT) is what sends the spans Strands and botocore emit to CloudWatch.
# All pinned, as everything else in the series. The line is post 07's,
# unchanged: the SDK was already in the image.
RUN pip install --no-cache-dir boto3==1.43.108 strands-agents==1.57.2 bedrock-agentcore==1.24.0 aws-opentelemetry-distro==0.22.0

WORKDIR /app
COPY main.py model.py gateway.py identity.py memory.py sandbox.py trail.py handoff.py ./

EXPOSE 8080
USER nobody
# The runtime's own health check is GET /ping; this mirrors it for anything
# that reads the image's HEALTHCHECK, with nothing but the standard library.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ping', timeout=2)"]
# The runtime injects the ADOT settings as environment variables, but a
# container is started with its own command, so the instrumentation wrapper
# is named here. It sets up the exporters before main.py imports anything,
# which is also what lets it instrument the SDK's server: ADOT swaps in its
# own Starlette class, and the SDK's app subclasses whichever it imports.
CMD ["opentelemetry-instrument", "python", "main.py"]

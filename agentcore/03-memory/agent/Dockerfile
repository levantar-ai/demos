# AgentCore Runtime requires linux/arm64 images (built with --platform linux/arm64)
FROM python:3.12-slim

# Unbuffered stdout so print() reaches CloudWatch immediately
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir boto3==1.43.63 mcp==1.29.0

WORKDIR /app
COPY main.py .
COPY gateway.py .

EXPOSE 8080
USER nobody
CMD ["python", "main.py"]

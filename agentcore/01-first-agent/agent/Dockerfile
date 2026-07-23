# AgentCore Runtime requires linux/arm64 images
FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app
COPY main.py .

EXPOSE 8080
USER nobody
CMD ["python", "main.py"]

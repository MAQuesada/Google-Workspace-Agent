FROM python:3.12-slim

# Environment setup
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app/src" \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    GUARDRAILS_HOME="/home/appuser/.guardrails"

# Accept Guardrails API key at build time
ARG GUARDRAILS_API_KEY
ENV GUARDRAILS_API_KEY=${GUARDRAILS_API_KEY}

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Virtual environment
RUN python -m venv $VIRTUAL_ENV && \
    $VIRTUAL_ENV/bin/pip install --upgrade pip

# Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Guardrails configuration and hub installation
RUN mkdir -p "$GUARDRAILS_HOME" && \
    echo "Configuring Guardrails..." && \
    : "${GUARDRAILS_API_KEY:? GUARDRAILS_API_KEY is missing at build time}" && \
    guardrails configure --enable-metrics --enable-remote-inferencing --token "$GUARDRAILS_API_KEY" && \
    echo "Installing Guardrails hub packages..." && \
    guardrails hub install hub://guardrails/llamaguard_7b && \
    guardrails hub install hub://guardrails/unusual_prompt

# Copy source
COPY . .

RUN chmod +x entrypoint.sh

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app $VIRTUAL_ENV $GUARDRAILS_HOME
USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]

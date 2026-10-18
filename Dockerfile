FROM python:3.13-slim

# poppler-utils: pdftotext/pdfinfo for the rules PDF; curl/git for the Claude Code installer and agents
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# Agents run as a non-root user (Claude Code won't skip permission prompts as root)
RUN useradd --create-home --shell /bin/bash app
USER app
RUN curl -fsSL https://claude.ai/install.sh | bash -s 2.1.302
ENV PATH="/home/app/.local/bin:${PATH}"

USER root
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R app:app /app && chmod +x /app/web/entrypoint.sh

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    RUNS_DIR=/data/runs CLAUDE_CONFIG_DIR=/data/claude-config DISABLE_AUTOUPDATER=1
EXPOSE 8080
CMD ["/app/web/entrypoint.sh"]

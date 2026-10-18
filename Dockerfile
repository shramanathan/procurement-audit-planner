FROM python:3.13-slim

# poppler-utils: pdftotext/pdfinfo for the quote check against the rules PDF
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
# one worker so the "one QA run at a time" lock holds; threads serve the pages
CMD ["gunicorn", "--chdir", "web", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "150", "app:app"]

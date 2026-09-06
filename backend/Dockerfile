FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends iputils-ping && rm -rf /var/lib/apt/lists/*
RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY . .
RUN chmod +x /app/entrypoint.sh && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["/app/entrypoint.sh", "web"]

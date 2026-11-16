FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*
COPY api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY api/app/ ./app/
COPY telephony/ ./telephony/
COPY api/entrypoint.sh /entrypoint.sh
RUN groupadd --gid 10001 famicom && useradd --system --uid 10001 --gid 10001 --home /srv famicom && chmod 755 /entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "web"]

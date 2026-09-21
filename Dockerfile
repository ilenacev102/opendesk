FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home appuser
COPY app.py config.py ./
COPY services/ ./services/
COPY utils/ ./utils/
COPY templates_web/ ./templates_web/
COPY templates/ ./templates/
COPY static/ ./static/
ENV SERVICEDESK_REQUIRE_SECRET=1
ENV SERVICEDESK_HOST=0.0.0.0
VOLUME ["/app/data", "/app/documents", "/app/backup"]
EXPOSE 5000
USER 10001
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health')"
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]

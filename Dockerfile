FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DECLIC_DB_PATH=/var/lib/declic/declic.sqlite3
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-voice.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-voice.txt
RUN useradd --system --uid 10001 --create-home declic && mkdir -p /var/lib/declic /app/voices && chown -R declic:declic /var/lib/declic /app/voices
COPY app /app/app
COPY data/demo_rdm2.pdf /app/data/demo_rdm2.pdf
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1"]

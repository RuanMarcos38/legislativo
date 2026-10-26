FROM python:3.11-slim
WORKDIR /app
COPY app app
COPY migrations migrations
COPY web web
RUN useradd -m observatorio && mkdir -p /app/data && chown -R observatorio:observatorio /app
USER observatorio
ENV BIND_HOST=0.0.0.0 PORT=8080 DATABASE_PATH=/app/data/observatorio.db PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=3)"
CMD ["python","-m","app.server"]

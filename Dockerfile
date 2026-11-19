FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY frontend frontend
RUN useradd --uid 10001 --create-home appuser
USER appuser
EXPOSE 8080
CMD ["python", "-m", "backend.server"]

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/run_all.py
EXPOSE 8090
CMD ["uvicorn","app.api:app","--host","0.0.0.0","--port","8090"]

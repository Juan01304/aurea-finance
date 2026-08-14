FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV AUREA_HOST=0.0.0.0 AUREA_NO_BROWSER=1 AUREA_ENV=production AUREA_SECURE_COOKIE=1
EXPOSE 10000
CMD ["python", "server.py"]

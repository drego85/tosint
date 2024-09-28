FROM python:3.9-slim

WORKDIR /app

COPY tosint.py /app/
COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "/app/tosint.py"]

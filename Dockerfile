FROM python:3.12-slim
WORKDIR /app
COPY . /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8080
WORKDIR /app/src
CMD ["python", "bot.py"]
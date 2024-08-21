FROM --platform=linux/amd64 python:3.12-slim 
WORKDIR /app
COPY . /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8080
CMD ["python", "bot.py"]
FROM python:3.11-slim

WORKDIR /app

# Install runtime deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY version.py app.py ./
COPY mqttplot ./mqttplot
COPY templates ./templates
COPY static ./static

# Defaults (override at runtime)
ENV FLASK_PORT=5000
ENV MQTT_BROKER=broker
ENV MQTT_PORT=1883
ENV MQTT_TOPICS=#

# Persistable locations (override + mount a volume)
ENV DB_PATH=/data/mqtt_data.db
ENV DATA_DB_DIR=/data/topics

EXPOSE 5000

CMD ["python", "app.py"]

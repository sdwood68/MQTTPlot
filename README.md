# 🧠 MQTTPlot  
**MQTT → SQLite → Flask + SocketIO + Plotly Dashboard**

---

## 📘 Overview
**MQTTPlot** is a lightweight Python project that listens to data from an MQTT broker, stores it in a local SQLite database, and provides both:
- A **real-time web dashboard** (using Flask, Socket.IO, and Plotly)
- A **RESTful API** for querying, configuring, and exporting plots (PNG/JSON)

Ideal for IoT, sensor networks, and data visualization.

---

## 🚀 Features
✅ Subscribe to MQTT topics (configurable via environment variables)  
✅ Store all messages in SQLite  
✅ Live Plotly dashboard with auto-updates via WebSocket  
✅ REST API for fetching data, updating config, and exporting plots  
✅ Export interactive Plotly JSON or static PNG images  
✅ Simple setup with Docker support  

---

## 📦 Requirements
- Python 3.9+
- MQTT broker (e.g., Mosquitto)
- Optional: Docker for containerized deployment

### Python dependencies
Installed automatically via:
```bash
pip install -r requirements.txt
```

## Quick Start
### 1️⃣ Clone the repository
``` bash
git clone https://github.com/yourusername/MQTTPlot.git
cd MQTTPlot
```

### 2️⃣ Install dependencies
```bash
pip install -r requirements.txt
```

### 3️⃣ Run the server
```bash
python app.py
```
The Flask server runs on http://localhost:5000

### 4️⃣ Connect your MQTT broker

By default, MQTTPlot connects to:
```yaml
broker: localhost
port: 1883
topics: #
```
Override with environment variables:

```bash
MQTT_BROKER=mybroker.local MQTT_TOPICS="sensors/temp,sensors/humidity" python app.py
```
### 5️⃣ Publish sample data
```bash
mosquitto_pub -h localhost -t sensors/temp -m '{"value": 23.5}'
```
### 6️⃣ Open the dashboard

Go to:
```commandline
http://localhost:5000
```
See:

- List of topics
- Real-time updates
- Interactive Plotly graph (zoom, pan, hover)

### 7️⃣ Use the REST API
List topics
```bash
curl http://localhost:5000/api/topics
```
Fetch data
```bash
curl "http://localhost:5000/api/data?topic=sensors/temp&limit=100"
```

Generate PNG plot
```bash
curl -o plot.png "http://localhost:5000/api/plot_image?topic=sensors/temp"
```

## ⚙️ Environment Variables
| Variable	     | Default        | Description            |
|---------------|----------------|------------------------|
| MQTT_BROKER   | localhost      | MQTT broker address    |
| MQTT_PORT     | 1883	          | MQTT port              |
| MQTT_TOPICS   | #	          | Comma-separated topics |
| MQTT_USERNAME | (empty)	      | Optional username      |
| MQTT_PASSWORD | (empty)	      | Optional password      |
| DB_PATH       | mqtt_data.db   | SQLite database file   |
| FLASK_PORT    | 5000           | Flask server port      |

## 🌐 Web Dashboard
Visit:
```commandline
http://localhost:5000
```

Displays live data and historical plots with adjustable time ranges.

## 🧠 REST API
```GET /api/topics```

List topics and message counts.

```GET /api/data```

Query data:

```php-template
/api/data?topic=<topic>&start=<iso>&end=<iso>&limit=<n>
```

```GET /api/config``` | ```POST /api/config```

Get or update plot configuration.

```GET /api/plot_image```

Return a static PNG or JSON Plotly object:

```bash
curl -o plot.png "http://localhost:5000/api/plot_image?topic=sensors/temp"
```

## 📊 Plot Configuration
| Setting                      | Default | Description |
|------------------------------|---------|-------------|
| ```default_window_minutes``` | ```60``` | ```Time window for plots```
| ```max_points```             | ```10000``` | ```Max datapoints per query``` |
| ```update_interval_ms```     | ```2000``` | ```Websocket update rate``` |

## 🐳 Docker Usage
### Build
```bash
docker build -t mqttplot .
```
### Run
```bash
docker run -it --rm \
  -e MQTT_BROKER=broker.emqx.io \
  -e MQTT_TOPICS="sensors/#" \
  -p 5000:5000 \
  mqttplot
```
Visit http://localhost:5000

## 🧩 Systemd Service (Auto-Start on Boot)

You can run MQTTPlot automatically as a background service on Linux / Raspberry Pi.

### 1️⃣ Create a service file

Save as ```/etc/systemd/system/mqttplot.service:```

```ini
[Unit]
Description=MQTTPlot - MQTT data dashboard
After=network.target

[Service]
WorkingDirectory=/home/pi/MQTTPlot
ExecStart=/usr/bin/python3 /home/pi/MQTTPlot/app.py
Environment=MQTT_BROKER=localhost
Environment=MQTT_TOPICS=sensors/#
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```
(Adjust paths and user as needed.)

### 2️⃣ Enable and start
```bash
sudo systemctl daemon-reload
sudo systemctl enable mqttplot.service
sudo systemctl start mqttplot.service
```

### 3️⃣ Check status
```bash
sudo systemctl status mqttplot.service
```
If it’s running, visit:
```cpp
 http://<your-device-ip>:5000
```
Logs are available with:
```bash
 journalctl -u mqttplot.service -f
```

## 🔒 Optional Authentication
To protect API endpoints, add a token check:

```python
@app.before_request
def require_token():
    if request.path.startswith("/api/"):
        token = request.headers.get("X-API-Token")
        if token != os.environ.get("API_TOKEN", "secret123"):
            return jsonify({"error": "unauthorized"}), 401
```

## 🧹 Database Schema

Table: messages

| Field | Type | Description           |
|-------|------|-----------------------|
|id | INTEGER | Primary key           |
| topic	| TEXT | MQTT topic            |
| ts | TIMESTAMP | Message time          |
| payload | TEXT | Raw MQTT payload      |
| value | REAL | Parsed numeric value  |

## 🧰 Developer Notes

- Built with Plotly + Kaleido for graphing
- Uses Socket.IO for live updates
- Persists messages in SQLite
- Configurable via REST or environment

## 🧩 Example MQTT Publish
```bash
mosquitto_pub -h localhost -t sensors/temp -m '{"value":23.5}'
```

## 🧩 How to Use ``install_service.sh``

### 1️⃣ Save this script in your project root as install_service.sh

```bash
nano install_service.sh
```

Paste the content above.

### 2️⃣ Make it executable:
```bash
chmod +x install_service.sh
```
### 3️⃣ Run it with sudo:
```bash
sudo ./install_service.sh
```
### 4️⃣ Follow the prompts:
```less
📡 MQTT broker address [localhost]:
🔌 MQTT port [1883]:
📋 MQTT topics (comma-separated) [sensors/#]:
🌐 Flask port [5000]:
💾 Database path [/home/pi/MQTTPlot/mqtt_data.db]:
👤 Run service as user [pi]:
🔐 MQTT username (optional):
🔑 MQTT password (optional):
### ✅ What it does
```

Once complete, it automatically:

- reates /etc/systemd/system/mqttplot.service
- Enables auto-start on boot
- Starts the service immediately
- Shows its current status

### 🧠Optional Maintenance Commands

Stop service:
```bash
 sudo systemctl stop mqttplot
```

Restart service:
```bash
 sudo systemctl restart mqttplot
```
View live logs:
```bash
 journalctl -u mqttplot -f
```

## 📄 License

MIT License — use freely for personal or commercial projects.
Created with ❤️ by GPT-5 + You.
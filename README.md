# MQTTPlot

MQTTPlot is a lightweight, self-hosted web application for visualizing time-series data published to MQTT topics. It is designed for local monitoring, experimentation, and embedded/IoT projects where a full metrics stack would be
overkill.

**MQTT → SQLite → Flask + SocketIO + Plotly Dashboard**

**MQTTPlot** provides both:
- A **real-time web dashboard** (using Flask, Socket.IO, and Plotly)
- A **RESTful API** for querying, configuring, and exporting plots (PNG/JSON)


## 🚀 Features
✅ Subscribe to MQTT topics (configurable via environment variables)  
✅ Store all messages in SQLite  
✅ Live Plotly dashboard with auto-updates via WebSocket  
✅ REST API for fetching data, updating config, and exporting plots  
✅ Export interactive Plotly JSON or static PNG images  
✅ Simple setup with Docker support  

---


## Roadmap status

The authoritative plan is maintained in **ROADMAP.md**.

Implemented milestone highlights:
- **0.6.0 (delivered via 0.6.1):** interactive time-window navigation (zoom/slide) and persistent storage per top-level MQTT topic
- **0.6.2 (planned):** code cleaning, review, and reorganization focused on maintainability and testability


## 📦 Requirements
- Python 3.9+
- MQTT broker (e.g., Mosquitto)
- Optional: Docker for containerized deployment

---

## Quick Start (5 minutes)

### Windows (PowerShell)
```powershell
git clone https://github.com/sdwood68/MQTTPlot.git
cd MQTTPlot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:DB_PATH="data\mqttplot_main.db"
$env:DATA_DB_DIR="data\topics"
$env:MQTT_BROKER="<mqtt-broker-ip>"
mkdir data\topics

$env:ADMIN_INIT_PASSWORD="ChangeMeNow!"
python app.py
Remove-Item Env:\ADMIN_INIT_PASSWORD
```

Open: http://localhost:5000

## Linux / macOS
```
git clone https://github.com/sdwood68/MQTTPlot.git
cd MQTTPlot
python3 -m venv .venv
source .venv/bin/activate
pip install flask flask-socketio paho-mqtt

export DB_PATH=$PWD/data/mqttplot_main.db
export DATA_DB_DIR=$PWD/data/topics
export MQTT_BROKER=<mqtt-broker-ip>
mkdir -p data/topics

export ADMIN_INIT_PASSWORD="ChangeMeNow!"
python app.py
unset ADMIN_INIT_PASSWORD
```
Open: http://localhost:5000

### First run initialization
On the very first startup only, MQTTPlot requires creation of an initial administrator account.

This is done by setting the environment variable: ADMIN_INIT_PASSWORD

#### Behavior

If no admin user exists, MQTTPlot will refuse to start unless ADMIN_INIT_PASSWORD is set.

On successful startup:
- The admin user is created
- The password is stored securely in the database

On subsequent runs:
- ADMIN_INIT_PASSWORD is not required
- The variable should be removed

#### Windows (PowerShell)
```
$env:ADMIN_INIT_PASSWORD="ChangeMeNow!"
python app.py
Remove-Item Env:\ADMIN_INIT_PASSWORD
```
### Linux
```
export ADMIN_INIT_PASSWORD="ChangeMeNow!"
python app.py
unset ADMIN_INIT_PASSWORD
```
**Do not leave ADMIN_INIT_PASSWORD set permanently.**

It is only intended for first-time initialization.

## VS Code Debugging
MQTTPlot supports debugging via VS Code, but editor configuration is not
committed to the repository.

Using launch.json
1. Create .vscode/launch.json
2. Example Configuration
```{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "MQTTPlot (venv)",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/app.py",
      "env": {
        "DB_PATH": "data/mqttplot_main.db",
        "DATA_DB_DIR": "data/topics",
        "MQTT_BROKER": "<mqtt-broker-ip>",
        "ADMIN_INIT_PASSWORD": "ChangeMeNow!"
      }
    }
  ]
}
```
3. Press F5 to start debugging

After the first successful run, remove the
ADMIN_INIT_PASSWORD entry from launch.json.

# Architectuer Overview
```
MQTT Broker
     |
     v
 MQTTPlot
 ├── Flask web server
 ├── MQTT client (paho-mqtt)
 ├── SQLite (metadata + per-topic data)
 └── Browser UI (Plotly)
```
## Per Topic Database
One SQLite file per top-level MQTT Topic
```
data/
├── topics/
│   ├── watergauge.db
│   ├── weather.db
│   └── ...
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
MQTT_BROKER=192.168.12.50.local MQTT_TOPICS="watergauge/#" python app.py
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
Created by Stuart Wood with help from GPT-5

import eventlet
eventlet.monkey_patch()
from flask import Flask, send_from_directory, Response
from flask_socketio import SocketIO
from flask_cors import CORS
import serial, threading, time, json, random, os, math

##### ENVIRONMENT #####
environment = "mock"  # "prod" | "dev" | "mock"
#######################

app = Flask(__name__, static_folder="./static", static_url_path="/")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")
# Serial setup depending on environment
if environment == "prod":
	ser = serial.Serial("/dev/ttyUSB0", 115200, timeout=1)
elif environment == "dev":
	ser = serial.Serial("COM3", 9600, timeout=1)
else:
	ser = None

# Global telemetry state
latest_data = {
	"timestamp": 0,
	"speed": 0.0,
	"temperature": 25.0,
	"voltage": 84.0,
	"soc": 100.0,
	"wh": 3600.0,
	"trip_distance": 0.0,
	"trip_efficiency": 0.0,
	"trip_time": 0.0,
}

# ---------- MOCK GENERATOR (Simulated Drive) ----------
def mock_reader():
	global latest_data
	increment = 1 / 60.0
	nominal_voltage = 84.0
	pack_capacity_wh = 3600.0
	trip_duration = 330.0
	regen_efficiency = 0.6

	temperature = 25.0
	energy_remaining_wh = pack_capacity_wh
	distance_km = 0.0
	energy_used_wh = 0.0
	t = 0.0
	prev_speed = 0.0

	stoplights = sorted(random.sample(range(60, 270, 30), 4))
	stoplight_active = False
	stoplight_timer = 0.0

	print("[INFO] Starting new simulated trip...")

	while True:
		if t >= trip_duration:
			trip_eff = (energy_used_wh / distance_km) if distance_km > 0 else 0
			latest_data.update({
				"trip_distance": round(distance_km, 2),
				"trip_efficiency": round(trip_eff, 1),
				"trip_time": round(t, 1),
			})
			print(f"[INFO] Trip complete: {distance_km:.2f} km, "
				  f"{energy_used_wh:.0f} Wh used, {trip_eff:.1f} Wh/km")

			# reset
			t = 0.0
			temperature = 25.0
			energy_remaining_wh = pack_capacity_wh
			distance_km = 0.0
			energy_used_wh = 0.0
			stoplights = sorted(random.sample(range(60, 270, 30), 4))
			stoplight_active = False
			stoplight_timer = 0.0
			time.sleep(2)
			print("[INFO] Starting new simulated trip...")

		# ---- Base driving pattern ----
		if t < 25:
			target_speed = 0
		elif t < 85:
			progress = (t - 25) / 60
			target_speed = 60 * math.sin(progress * math.pi / 2)
		elif t < 235:
			target_speed = 60 + 5 * math.sin(t / 12) + random.uniform(-2, 2)
		elif t < 265:
			progress = (t - 235) / 30
			target_speed = 60 * (1 - progress)
		elif t < 285:
			target_speed = 0
		elif t < 325:
			progress = (t - 285) / 40
			target_speed = 40 * math.sin(progress * math.pi)
		else:
			target_speed = 0

		# ---- Random stoplights ----
		if stoplights and t > stoplights[0]:
			if not stoplight_active:
				stoplight_active = True
				stoplight_timer = random.uniform(5, 12)
				print(f"[INFO] Stoplight at t={int(t)}s for {stoplight_timer:.1f}s")
			stoplight_timer -= increment
			target_speed = 0
			if stoplight_timer <= 0:
				stoplights.pop(0)
				stoplight_active = False

		speed = prev_speed + (target_speed - prev_speed) * 0.1
		speed = max(0.0, min(speed, 100.0))

		# ---- Distance & Temperature ----
		distance_km += (speed / 3600.0) * increment
		if speed > 10:
			temperature += 0.005 * (speed / 40.0)
		else:
			temperature -= 0.008
		temperature = max(15.0, min(temperature, 70.0))

		# ---- Energy Model ----
		accel = (speed - prev_speed) / increment
		discharge_current = (speed ** 2) / 1000.0 + (1 if speed > 0 else 0.2)
		regen_current = 0.0
		if accel < -0.5:
			regen_current = min(abs(accel) * 0.5, 5.0)
			discharge_current -= regen_current * regen_efficiency
		discharge_current = max(0.0, discharge_current)
		power = nominal_voltage * discharge_current
		wh_used = power * increment / 3600.0
		energy_used_wh += wh_used
		energy_remaining_wh -= wh_used
		if regen_current > 0:
			recovered = nominal_voltage * regen_current * increment / 3600.0 * regen_efficiency
			energy_remaining_wh += recovered
			energy_used_wh -= recovered
		energy_remaining_wh = max(0.0, min(energy_remaining_wh, pack_capacity_wh))

		# ---- Electrical Model ----
		soc = (energy_remaining_wh / pack_capacity_wh) * 100.0
		voltage = nominal_voltage * (0.8 + 0.2 * (soc / 100.0))

		latest_data.update({
			"timestamp": round(t * 1000, 1),
			"speed": round(speed, 1),
			"temperature": round(temperature, 1),
			"voltage": round(voltage, 2),
			"soc": round(soc, 1),
			"wh": round(energy_remaining_wh, 1),
		})

		# ---- Emit telemetry (WebSocket) ----
		socketio.emit("telemetry", latest_data)

		prev_speed = speed
		t += increment
		time.sleep(increment)

# ---------- SERIAL READER ----------
def reader():
	global latest_data
	capacity = 3600
	while True:
		line = ser.readline().decode().strip()
		# 11003;35;24;72;100000
		# timestamp;hız;sıcaklık;voltage;watt
		if line:
			try:
				parts = line.split(";")
				latest_data["timestamp"] = parts[0]
				latest_data["speed"] = parts[1]
				latest_data["temperature"] = parts[2]
				latest_data["voltage"] = parts[3]
				latest_data["wh"] = parts[4]
				# SoC calculation, change when arduino gives this
				latest_data["soc"] = (latest_data["wh"] / capacity) * 100 # parts[5]
				socketio.emit("telemetry", latest_data)
			except:
				pass

# ---------- SSE FALLBACK ----------
@app.route("/data")
def data():
	def stream():
		while True:
			yield f"data: {json.dumps(latest_data)}\n\n"
			time.sleep(0.5)
	return Response(stream(), mimetype="text/event-stream")

# ---------- STATIC FRONTEND ----------
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
	if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
		return send_from_directory(app.static_folder, path)
	else:
		return send_from_directory(app.static_folder, "index.html")

# ---------- ENTRY POINT ----------
if __name__ == "__main__":
	if environment == "mock":
		threading.Thread(target=mock_reader, daemon=True).start()
	else:
		threading.Thread(target=reader, daemon=True).start()
	socketio.run(app, host="0.0.0.0", port=5000)


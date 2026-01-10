import cv2
import numpy as np
import paho.mqtt.client as mqtt
import json
import time
import threading
import os
import joblib
import pandas as pd
import requests             
import urllib.request 
from sklearn.ensemble import RandomForestRegressor
from flask import Flask, Response

# ==========================================
# ⚙️ 1. KONFIGURASI SISTEM
# ==========================================

ESP32_CAM_URL = "http://192.168.1.145/capture" 
PORT_SERVER = 5555 

# MQTT
MQTT_BROKER = "broker.hivemq.com"
TOPIC_SENSOR = "fig/sensor"
TOPIC_CONTROL = "fig/control"

# ⚠️ DATA PRIBADI (SUDAH TERISI)
TELEGRAM_BOT_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["CHAT_ID"]

OWM_API_KEY = "4b031f7ed240d398ab4b7696d2361d97"
OWM_CITY = "Sukabumi,ID"
OWM_URL = f"http://api.openweathermap.org/data/2.5/weather?q={OWM_CITY}&appid={OWM_API_KEY}&units=metric"

# Model & Map
MODEL_FILENAME = "fig_model.pkl"
COMMODITY_MAP = {"Pisang": 0, "Tomat": 1, "Bayam": 2}

# Global Variables
sensor_data = {"temp": 28.0, "hum": 60.0} 
external_weather = {"temp": 0, "desc": "Offline", "city": "Luar"}
current_commodity = "Pisang"
model = None
last_alert_time = 0         
ALERT_COOLDOWN = 300 
current_jpeg = None
lock = threading.Lock()

app = Flask(__name__)

# ==========================================
# 📸 2. SERVER FLASK
# ==========================================
@app.route("/snapshot")
def snapshot():
    global current_jpeg
    with lock:
        if current_jpeg is None: return "No Image", 404
        return Response(current_jpeg, mimetype="image/jpeg")

# ==========================================
# ☁️ 3. WEATHER & TELEGRAM
# ==========================================
def fetch_weather_loop():
    global external_weather
    print("☁️ Weather Service Started...")
    while True:
        try:
            r = requests.get(OWM_URL, timeout=10)
            if r.status_code == 200:
                d = r.json()
                external_weather = {
                    "temp": d["main"]["temp"], 
                    "desc": d["weather"][0]["description"], 
                    "city": d["name"]
                }
        except: pass
        time.sleep(900) 

def send_telegram_alert(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload, timeout=5)
    except: pass

# ==========================================
# 📡 4. MQTT LISTENER (DEBUG)
# ==========================================
def get_mqtt_client(name):
    try: return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, name)
    except: return mqtt.Client(name)

def on_message(client, userdata, msg):
    global sensor_data
    raw = msg.payload.decode()
    print(f"📥 MQTT: {raw}") # Debugging
    try:
        p = json.loads(raw)
        if "temp" in p and "hum" in p:
            sensor_data["temp"] = float(p["temp"])
            sensor_data["hum"] = float(p["hum"])
    except: pass

def mqtt_loop():
    print("📡 MQTT Started...")
    c = get_mqtt_client("FIG_Backend")
    c.on_message = on_message
    c.connect(MQTT_BROKER, 1883, 60)
    c.subscribe(TOPIC_SENSOR)
    c.loop_forever()

# ==========================================
# 🧠 5. AI & LOGIC
# ==========================================
def get_model():
    if os.path.exists(MODEL_FILENAME): return joblib.load(MODEL_FILENAME)
    else:
        df = pd.DataFrame({'temp':[30]*5, 'hum':[60]*5, 'ripe':[50]*5, 'type':[0]*5, 'hours':[24]*5})
        rf = RandomForestRegressor(n_estimators=10); rf.fit(df.iloc[:,:4], df.iloc[:,4])
        return rf

def analyze_frame(frame, item_name):
    # Konversi ke HSV
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    height, width, _ = frame.shape
    
    final_score = 0  
    global_status = "MENUNGGU"
    detected_count = 0
    
    # --- KASUS 1: BAYAM ---
    if item_name == "Bayam":
        lower_wilt = np.array([15, 50, 50])
        upper_wilt = np.array([35, 255, 255])
        mask_wilt = cv2.inRange(hsv, lower_wilt, upper_wilt)
        wilt_pixels = cv2.countNonZero(mask_wilt)
        raw_score = (wilt_pixels / (height * width)) * 100 * 5 
        final_score = min(raw_score, 100.0) 
        
        if final_score > 20: 
            global_status = "LAYU / BUSUK"
            color_res = (0, 0, 255)
        else:
            global_status = "SEGAR"
            color_res = (0, 255, 0)

        cv2.rectangle(frame, (0, height-40), (width, height), (0,0,0), -1)
        # UPDATE: Font Besar (1.0), Tebal (3)
        cv2.putText(frame, f"BAYAM: {global_status} ({int(final_score)}%)", (10, height-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color_res, 3)
        return global_status, final_score, frame

    # --- KASUS 2: TOMAT & PISANG ---
    else:
        mask_shape = None
        if item_name == "Tomat":
            l1, u1 = np.array([0, 80, 50]), np.array([15, 255, 255])
            l2, u2 = np.array([160, 80, 50]), np.array([180, 255, 255])
            mask_shape = cv2.inRange(hsv, l1, u1) + cv2.inRange(hsv, l2, u2)
        elif item_name == "Pisang":
            mask_yellow = cv2.inRange(hsv, (15, 40, 40), (40, 255, 255))
            mask_brown = cv2.inRange(hsv, (0, 40, 20), (30, 255, 200))
            mask_dark = cv2.inRange(hsv, (0, 0, 0), (180, 255, 80)) 
            mask_shape = mask_yellow + mask_brown + mask_dark

        kernel = np.ones((5,5), np.uint8)
        mask_shape = cv2.morphologyEx(mask_shape, cv2.MORPH_CLOSE, kernel) 
        mask_shape = cv2.morphologyEx(mask_shape, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask_shape, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rot_found_in_frame = False
        
        if len(contours) > 0:
            global_status = "SEGAR" 
            final_score = 10        

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 1500: continue 
                x, y, w, h = cv2.boundingRect(cnt)
                detected_count += 1
                roi_hsv = hsv[y:y+h, x:x+w]
                rot_ratio, thresh = 0, 0
                
                # Sensitivitas (Agresif)
                if item_name == "Tomat":
                    mask_rot = cv2.inRange(roi_hsv, (0, 10, 0), (180, 255, 130))
                    rot_ratio = (cv2.countNonZero(mask_rot) / (w*h)) * 100
                    thresh = 1.5 
                elif item_name == "Pisang":
                    mask_rot = cv2.inRange(roi_hsv, (0, 30, 0), (180, 255, 110))
                    rot_ratio = (cv2.countNonZero(mask_rot) / (w*h)) * 100
                    thresh = 10.0 

                if rot_ratio > thresh:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 3)
                    # UPDATE: Font Besar (1.2), Tebal (3)
                    cv2.putText(frame, f"BUSUK {int(rot_ratio)}%", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,0,255), 3)
                    rot_found_in_frame = True
                    if rot_ratio > final_score: final_score = rot_ratio * 2.0 
                else:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 3)
                    # UPDATE: Font Besar (1.2), Tebal (3)
                    cv2.putText(frame, "SEGAR", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,255,0), 3)

        if rot_found_in_frame:
            global_status = "BUSUK TERDETEKSI"
            if final_score < 75: final_score = 75 
        elif detected_count > 0:
            global_status = "SEGAR"
            final_score = 10
        else:
            global_status = "TIDAK ADA OBJEK"
            final_score = 0
            
        cv2.rectangle(frame, (0, height-40), (width, height), (0,0,0), -1)
        # UPDATE: Font Besar (1.0), Tebal (3)
        cv2.putText(frame, f"{item_name.upper()}: {global_status}", (10, height-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)

        return global_status, final_score, frame
        
def process_logic(temp, hum, score, status, item):
    global last_alert_time
    client = get_mqtt_client("FIG_Logic")
    try: client.connect(MQTT_BROKER, 1883, 60)
    except: pass
    
    dec = {'shelf_life': 0, 'fan': 'OFF', 'mist': 'OFF', 'alert': ''}
    
    # 1. Prediksi AI (Random Forest)
    predicted_life = 0
    if model:
        type_code = COMMODITY_MAP.get(item, 0)
        input_data = pd.DataFrame([[temp, hum, score, type_code]], columns=['temp', 'hum', 'ripe', 'type'])
        predicted_life = round(model.predict(input_data)[0], 1)

    # =========================================================
    # ### LOGIKA PENTING: VISUAL BUSUK = UMUR 0 JAM ###
    # =========================================================
    if "BUSUK" in status or score > 65: 
        dec['shelf_life'] = 0.0  
    else: 
        dec['shelf_life'] = predicted_life
    # =========================================================

    # --- LOGIKA KONTROL & TELEGRAM ---
    active_alerts = []; telegram_reasons = []; recommendations = []

    # A. Cek Suhu (Panas)
    if item in ["Pisang", "Tomat"]:
        if temp > 30.0:
            client.publish(f"{TOPIC_CONTROL}/fan", "ON"); dec['fan'] = "ON"
            active_alerts.append("⚠️ SUHU PANAS")
            telegram_reasons.append(f"Suhu Tinggi ({temp}°C)")
            if "Cek Pendingin" not in recommendations: recommendations.append("✅ Cek Kipas/Ventilasi Gudang")
        else:
            client.publish(f"{TOPIC_CONTROL}/fan", "OFF")
    
    # B. Cek Kelembaban (Bayam)
    if item == "Bayam":
        if hum < 60.0:
            client.publish(f"{TOPIC_CONTROL}/mist", "ON"); dec['mist'] = "ON"
            active_alerts.append("💧 MELEMBABKAN")
        else:
            client.publish(f"{TOPIC_CONTROL}/mist", "OFF")

    # C. Cek Visual (Busuk)
    if "BUSUK" in status or score > 65:
        active_alerts.append("🚨 BUSUK TERDETEKSI")
        telegram_reasons.append(f"Visual Busuk (Kematangan: {int(score)}%)")
        recommendations.append("💰 REKOMENDASI: Segera beri DISKON atau pisahkan stok!")

    # D. Cek Sisa Waktu
    if dec['shelf_life'] < 12.0 and dec['shelf_life'] > 0.1:
        active_alerts.append(f"⏳ KRITIS (<12h)")
        telegram_reasons.append(f"Sisa Waktu Kritis ({dec['shelf_life']} Jam)")
        recommendations.append("⚡ REKOMENDASI: Prioritaskan penjualan / Flash Sale.")

    if not active_alerts: dec['alert'] = "✅ STATUS AMAN"
    else: dec['alert'] = " | ".join(active_alerts)

    # Kirim Telegram jika ada masalah
    if len(telegram_reasons) > 0 and (time.time() - last_alert_time > ALERT_COOLDOWN):
        msg = f"🔥 *FIG ALERT SYSTEM* 🔥\n📦 Item: *{item}*\n⏰ Waktu: {time.strftime('%H:%M')}\n\n*⚠️ ISU TERDETEKSI:*\n" + "\n".join([f"• {r}" for r in telegram_reasons])
        if len(recommendations) > 0: msg += "\n\n*💡 SARAN TINDAKAN:*\n" + "\n".join([f"👉 {rec}" for rec in recommendations])
        threading.Thread(target=send_telegram_alert, args=(msg,)).start()
        last_alert_time = time.time()
            
    return dec

# ==========================================
# 🚀 6. MAIN LOOP (Updated: Auto-Pause Feature)
# ==========================================
if __name__ == "__main__":
    threading.Thread(target=mqtt_loop, daemon=True).start()
    threading.Thread(target=fetch_weather_loop, daemon=True).start()
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT_SERVER, debug=False, use_reloader=False), daemon=True).start()
    
    model = get_model()
    print("\n🚀 BACKEND RUNNING... (Press Ctrl+C to Stop)\n")

    while True:
        try:
            # --- BAGIAN BARU: CEK STATUS DARI DASHBOARD ---
            sim = False
            live_active = True 
            sim_vals = {}
            try:
                with open("dashboard_config.json") as f: 
                    cfg = json.load(f)
                    current_commodity = cfg.get("commodity", "Pisang")
                    sim = cfg.get("sim_mode", False)
                    # Baca status apakah Dashboard sedang mode Realtime atau Simulasi
                    live_active = cfg.get("live_active", True)
                    sim_vals = cfg
            except: pass

            # === LOGIKA PAUSE: JIKA DASHBOARD SEDANG SIMULASI, BACKEND ISTIRAHAT ===
            if not live_active:
                print(f"⏸️  SISTEM PAUSED (Dashboard dalam Mode Simulasi) - {time.strftime('%H:%M:%S')}")
                time.sleep(1)
                continue # Skip proses kamera, langsung ulang loop
            # =======================================================================

            frame_show = None
            f_stat, f_score, f_temp, f_hum = "WAITING", 0, 0, 0

            # B. AMBIL DATA REALTIME (Sama seperti sebelumnya)
            f_temp = sensor_data['temp']
            f_hum = sensor_data['hum']
            
            try:
                resp = urllib.request.urlopen(ESP32_CAM_URL, timeout=5)
                arr = np.array(bytearray(resp.read()), dtype=np.uint8)
                frame = cv2.imdecode(arr, -1)
                
                if frame is not None:
                    frame = cv2.resize(frame, (400, 300))
                    s, sc, frm = analyze_frame(frame, current_commodity)
                    frame_show = frm
                    f_stat, f_score = s, sc
                else: print("⚠️ Gambar Kosong")
            except Exception as e:
                print(f"⚠️ Cam Error: {e}")
                frame_show = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame_show, "OFFLINE / BAD URL", (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            # C. Update Flask & Logic
            if frame_show is not None:
                fl, enc = cv2.imencode(".jpg", frame_show)
                if fl: 
                    with lock: current_jpeg = enc.tobytes()

            dec = process_logic(f_temp, f_hum, f_score, f_stat, current_commodity)
            
            # D. Simpan State
            state = {
                "sensor": {"temp": f_temp, "hum": f_hum},
                "external": external_weather,
                "decision": dec,
                "visual": {"status": f_stat, "score": f_score},
                "timestamp": time.time()
            }
            with open("system_state.json", "w") as f: json.dump(state, f)

            print(f"✅ [{time.strftime('%H:%M:%S')}] {current_commodity} | T:{f_temp} H:{f_hum} | {f_stat}")
            time.sleep(2.0)

        except KeyboardInterrupt: break
        except Exception as e: print(f"Err: {e}"); time.sleep(1)
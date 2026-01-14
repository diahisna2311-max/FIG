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

ESP32_CAM_URL = "http://192.168.1.108/capture" 
PORT_SERVER = 5555 

# MQTT
MQTT_BROKER = "broker.hivemq.com"
TOPIC_SENSOR = "fig/sensor"
TOPIC_CONTROL = "fig/control"

# ⚠️ DATA PRIBADI (SUDAH TERISI)
TELEGRAM_BOT_TOKEN = "8499021289:AAELtn5L43TTxrm8wNWZWkFpHQt1XSH3gs8"
TELEGRAM_CHAT_ID = "-1003371439420"

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
# 5. AI & LOGIC
# ==========================================
def get_model():
    if os.path.exists(MODEL_FILENAME): return joblib.load(MODEL_FILENAME)
    else:
        df = pd.DataFrame({'temp':[30]*5, 'hum':[60]*5, 'ripe':[50]*5, 'type':[0]*5, 'hours':[24]*5})
        rf = RandomForestRegressor(n_estimators=10); rf.fit(df.iloc[:,:4], df.iloc[:,4])
        return rf

def analyze_frame(frame, item_name):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    height, width, _ = frame.shape
    
    # Default return values
    final_score = 0  # 0 = Segar, 100 = Busuk Parah
    global_status = "MENUNGGU"
    detected_count = 0
    
    # KASUS 1: BAYAM (ANALISIS GLOBAL / TANPA KOTAK)
    if item_name == "Bayam":
        # Logika: Hitung persentase warna Kuning/Coklat (Layu) di seluruh gambar
        # Range warna Layu (Kuning pudar s.d. Coklat)
        lower_wilt = np.array([15, 50, 50])
        upper_wilt = np.array([35, 255, 255])
        mask_wilt = cv2.inRange(hsv, lower_wilt, upper_wilt)
        
        # Hitung skor global
        wilt_pixels = cv2.countNonZero(mask_wilt)
        total_pixels = height * width
        
        # Kalkulasi persentase kerusakan
        raw_score = (wilt_pixels / total_pixels) * 100 * 5 
        final_score = min(raw_score, 100.0) # Cap di 100
        
        # Tentukan Status Teks
        if final_score > 20: 
            global_status = "LAYU / BUSUK"
            color_res = (0, 0, 255) # Merah
        else:
            global_status = "SEGAR"
            color_res = (0, 255, 0) # Hijau

        # Visualisasi Sederhana (Bar di bawah)
        cv2.rectangle(frame, (0, height-40), (width, height), (0,0,0), -1)
        cv2.putText(frame, f"BAYAM: {global_status} ({int(final_score)}%)", (10, height-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_res, 2)
        
        return global_status, final_score, frame

    # KASUS 2: TOMAT & PISANG (ANALISIS PER-ITEM / KOTAK)
    else:
        mask_shape = None
        
        # A. Tentukan Masker BENTUK UTAMA (Agar objek terdeteksi utuh)
        if item_name == "Tomat":
            # Gabungan Merah 1 & Merah 2
            l1, u1 = np.array([0, 100, 50]), np.array([10, 255, 255])
            l2, u2 = np.array([170, 100, 50]), np.array([180, 255, 255])
            mask_shape = cv2.inRange(hsv, l1, u1) + cv2.inRange(hsv, l2, u2)
            
        elif item_name == "Pisang":            
            # 1. Warna Kuning (Badan Pisang)
            mask_yellow = cv2.inRange(hsv, (15, 80, 80), (35, 255, 255))
            
            # 2. Warna Coklat/Gelap (Bintik/Ujung Pisang)
            mask_brown = cv2.inRange(hsv, (10, 50, 20), (25, 200, 150))
            
            mask_shape = mask_yellow + mask_brown # Gabung

        # Bersihkan noise pada bentuk
        kernel = np.ones((5,5), np.uint8)
        mask_shape = cv2.morphologyEx(mask_shape, cv2.MORPH_CLOSE, kernel) # Tutup lubang kecil
        mask_shape = cv2.morphologyEx(mask_shape, cv2.MORPH_OPEN, kernel)  # Hapus noise

        # Cari Kontur
        contours, _ = cv2.findContours(mask_shape, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rot_found_in_frame = False
        
        if len(contours) > 0:
            global_status = "SEGAR" # Asumsi awal
            final_score = 10        # Skor rendah (segar)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 2000: continue # Abaikan objek terlalu kecil
                
                x, y, w, h = cv2.boundingRect(cnt)
                detected_count += 1
                
                # --- ANALISA KERUSAKAN DI DALAM KOTAK ---
                roi_hsv = hsv[y:y+h, x:x+w]
                
                rot_ratio = 0
                thresh = 0
                
                if item_name == "Tomat":
                    # Tomat: Cari Hitam/Gelap (Busuk Basah)
                    mask_rot = cv2.inRange(roi_hsv, (0, 0, 0), (180, 255, 70))
                    rot_ratio = (cv2.countNonZero(mask_rot) / (w*h)) * 100
                    thresh = 5.0 # Sensitivitas Tomat

                elif item_name == "Pisang":
                    # Pisang: Cari Coklat Gelap / Hitam (Busuk)
                    # Threshold value < 60 (Sangat gelap) agar bintik gula tidak dianggap busuk
                    mask_rot = cv2.inRange(roi_hsv, (0, 0, 0), (180, 255, 60)) 
                    rot_ratio = (cv2.countNonZero(mask_rot) / (w*h)) * 100
                    thresh = 8.0 # Sensitivitas Pisang (Toleransi bintik lebih tinggi)

                # --- GAMBAR KOTAK ---
                if rot_ratio > thresh:
                    # KOTAK MERAH (BUSUK)
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
                    label_txt = f"BUSUK {int(rot_ratio)}%"
                    cv2.putText(frame, label_txt, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 2)
                    
                    rot_found_in_frame = True
                    # Update skor global jika ditemukan yang busuk
                    # Kita ambil rot_ratio tertinggi sebagai representasi kerusakan batch ini
                    if rot_ratio > final_score:
                        final_score = rot_ratio * 2 # Perbesar skor agar AI prediksi umur pendek
                else:
                    # KOTAK HIJAU (BAGUS)
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    label_txt = "SEGAR"
                    cv2.putText(frame, label_txt, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)

        # --- TENTUKAN STATUS AKHIR ---
        if rot_found_in_frame:
            global_status = "BUSUK TERDETEKSI"
            # Pastikan skor cukup tinggi untuk memicu alert (> 65 di logika process_logic)
            if final_score < 70: final_score = 75 
        elif detected_count > 0:
            global_status = "SEGAR"
            final_score = 10
        else:
            global_status = "TIDAK ADA OBJEK"
            final_score = 0
            
        # Overlay Teks Bawah Hitam
        cv2.rectangle(frame, (0, height-40), (width, height), (0,0,0), -1)
        cv2.putText(frame, f"{item_name.upper()}: {global_status}", (10, height-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        return global_status, final_score, frame

def process_logic(temp, hum, score, status, item):
    global last_alert_time

    client = get_mqtt_client("FIG_Logic")
    try: client.connect(MQTT_BROKER, 1883, 60)
    except: pass
    
    dec = {'shelf_life': 0, 'fan': 'OFF', 'mist': 'OFF', 'alert': ''}
    
    # --- 1. PREDIKSI ---
    predicted_life = 0
    if model:
        type_code = COMMODITY_MAP.get(item, 0)
        input_data = pd.DataFrame([[temp, hum, score, type_code]], columns=['temp', 'hum', 'ripe', 'type'])
        predicted_life = round(model.predict(input_data)[0], 1)

    if "BUSUK" in status or score > 65:
        dec['shelf_life'] = 0.0
    else:
        dec['shelf_life'] = predicted_life

    # --- 2. LOGIKA KONTROL & ALERT ---
    active_alerts = []
    telegram_reasons = []
    recommendations = []
    
    # Variabel untuk memicu LED Merah via topik Alert
    trigger_red_led = False 

    # A. Cek Suhu (Panas) -> Fan ON
    if item in ["Pisang", "Tomat", "Bayam"]:
        if temp > 30.0:
            client.publish(f"{TOPIC_CONTROL}/fan", "ON"); dec['fan'] = "ON"
            active_alerts.append("⚠️ SUHU PANAS")
            telegram_reasons.append(f"Suhu Tinggi ({temp}°C)")
            if "Cek Pendingin" not in recommendations:
                recommendations.append("✅ Cek Kipas/Ventilasi Gudang")
        else:
            client.publish(f"{TOPIC_CONTROL}/fan", "OFF")
    
    # B. Cek Kelembaban (Bayam Kering) -> Mist ON
    if item == "Bayam":
        if hum < 60.0:
            client.publish(f"{TOPIC_CONTROL}/mist", "ON"); dec['mist'] = "ON"
            active_alerts.append("💧 KERING (LEMBABKAN)")
            # Mist ON otomatis menyalakan LED Merah di ESP32 (karena logika isMistOn)
        else:
            client.publish(f"{TOPIC_CONTROL}/mist", "OFF")

    # C. Cek Visual (Busuk) -> Trigger Alert
    if "BUSUK" in status or score > 65:
        active_alerts.append("🚨 BUSUK TERDETEKSI")
        telegram_reasons.append(f"Visual Busuk (Kematangan: {int(score)}%)")
        recommendations.append("💰 REKOMENDASI: Segera beri DISKON atau pisahkan stok!")
        trigger_red_led = True # Tandai bahaya visual

    # --- D. KIRIM SINYAL ALERT KE ESP32 ---
    # Jika Busuk terdeteksi, kirim ON ke topik alert agar LED Merah nyala
    if trigger_red_led:
        client.publish(f"{TOPIC_CONTROL}/alert", "ON")
    else:
        client.publish(f"{TOPIC_CONTROL}/alert", "OFF")

    # --- E. MONITORING Dashboard ---
    if dec['shelf_life'] < 12.0 and dec['shelf_life'] > 0.1:
        active_alerts.append(f"⏳ KRITIS (<12h)")
        telegram_reasons.append(f"Sisa Waktu Kritis ({dec['shelf_life']} Jam)")

    if not active_alerts:
        dec['alert'] = "✅ STATUS AMAN"
    else:
        dec['alert'] = " | ".join(active_alerts)

    # --- F. TELEGRAM ---
    if len(telegram_reasons) > 0 and (time.time() - last_alert_time > ALERT_COOLDOWN):
        msg = f"🔥 *FIG ALERT SYSTEM* 🔥\n📦 Item: *{item}*\n⏰ Waktu: {time.strftime('%H:%M')}\n\n"
        msg += "*⚠️ ISU TERDETEKSI:*\n" + "\n".join([f"• {r}" for r in telegram_reasons])
        if recommendations:
            msg += "\n\n*💡 SARAN TINDAKAN:*\n" + "\n".join([f"👉 {rec}" for rec in recommendations])
        
        threading.Thread(target=send_telegram_alert, args=(msg,)).start()
        last_alert_time = time.time()
            
    return dec

# ==========================================
# 🚀 6. MAIN LOOP
# ==========================================
if __name__ == "__main__":
    threading.Thread(target=mqtt_loop, daemon=True).start()
    threading.Thread(target=fetch_weather_loop, daemon=True).start()
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT_SERVER, debug=False, use_reloader=False), daemon=True).start()
    
    model = get_model()
    print("\n🚀 BACKEND RUNNING... (Press Ctrl+C to Stop)\n")

    while True:
        try:
            # A. Baca Config
            sim = False
            sim_vals = {}
            try:
                with open("dashboard_config.json") as f: 
                    cfg = json.load(f)
                    current_commodity = cfg.get("commodity", "Pisang")
                    sim = cfg.get("sim_mode", False)
                    sim_vals = cfg
            except: pass

            frame_show = None
            f_stat, f_score, f_temp, f_hum = "WAITING", 0, 0, 0

            # B. Ambil Data
            if sim:
                f_temp = sim_vals.get('sim_temp', 28)
                f_hum = sim_vals.get('sim_hum', 60)
                f_score = sim_vals.get('sim_score', 0)
                frame_show = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame_show, "SIMULATION MODE", (180, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            else:
                f_temp = sensor_data['temp']
                f_hum = sensor_data['hum']
                
                # --- SNAPSHOT CAPTURE (PENTING: VERSI STABIL) ---
                try:
                    # Request 1 gambar ke ESP32 (Timeout 5 detik)
                    resp = urllib.request.urlopen(ESP32_CAM_URL, timeout=5)
                    arr = np.array(bytearray(resp.read()), dtype=np.uint8)
                    frame = cv2.imdecode(arr, -1)
                    
                    if frame is not None:
                        frame = cv2.resize(frame, (640, 480))
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

            print(f"✅ [{time.strftime('%H:%M:%S')}] {current_commodity} | T:{f_temp} H:{f_hum}")
            time.sleep(2.0) # Jeda 2 detik agar tidak memberatkan ESP32

        except KeyboardInterrupt: break
        except Exception as e: print(f"Err: {e}"); time.sleep(1)
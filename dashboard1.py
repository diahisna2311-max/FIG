import streamlit as st
import json
import time
import os
import pandas as pd
import altair as alt 
import numpy as np 
import cv2         
from datetime import datetime
from PIL import Image

# ==========================================
# 1. KONFIGURASI & CSS
# ==========================================
st.set_page_config(
    page_title="FIG - Smart Warehouse",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .block-container { padding-top: 2rem; padding-bottom: 3rem; }
    div[data-testid="stMetric"] {
        background-color: #1E1E1E; border: 1px solid #333;
        padding: 10px; border-radius: 8px;
    }
    div[data-testid="stMetricLabel"] p { color: #AAA !important; font-size: 13px; }
    div[data-testid="stMetricValue"] div { color: #FFF !important; font-size: 24px; font-weight: bold; }
    
    .stButton button { 
        width: 100%; height: 70px; font-size: 18px !important;
        font-weight: bold !important; border-radius: 10px !important;
        transition: 0.3s; border: 2px solid #444;
    }
    .stButton button:hover { border-color: #ff4b4b; color: #ff4b4b; }

    .hardware-badge-on {
        background-color: #f1c40f; color: #000; padding: 8px 15px; 
        border-radius: 20px; font-weight: bold; text-align: center; border: 2px solid #d4ac0d; margin-bottom: 10px;
    }
    .hardware-badge-off {
        background-color: #27ae60; color: #fff; padding: 8px 15px; 
        border-radius: 20px; font-weight: bold; text-align: center; border: 2px solid #1e8449; margin-bottom: 10px;
    }
    
    h1, h2, h3 { color: #EEE !important; text-align: center; }
    .guide-text { font-size: 16px; color: #DDD; text-align: left !important; line-height: 1.6; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. STATE & FUNGSI BANTUAN
# ==========================================
if 'page' not in st.session_state: st.session_state['page'] = 'home'
if 'commodity' not in st.session_state: st.session_state['commodity'] = "Pisang"
if 'init_sim' not in st.session_state: st.session_state['init_sim'] = True

if 'data_history' not in st.session_state:
    st.session_state['data_history'] = pd.DataFrame(columns=['Waktu', 'Komoditas', 'Suhu', 'Lembab', 'Sisa Umur', 'Status'])

def save_cfg(com, sim=False, t=28, h=60, s=0):
    try:
        with open("dashboard_config.json", "w") as f:
            json.dump({"commodity": com, "sim_mode": sim, "sim_temp": t, "sim_hum": h, "sim_score": s}, f)
    except: pass

def create_sim_image(commodity, status_score):
    if commodity == "Pisang": bg_color = (80, 200, 255) 
    elif commodity == "Tomat": bg_color = (80, 80, 220) 
    else: bg_color = (80, 180, 80) 
    
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = bg_color 
    
    text_status = "MENTAH/SEGAR"
    if status_score > 25: text_status = "MATANG"
    if status_score > 65: text_status = "BUSUK"
    
    cv2.putText(img, f"SIMULASI: {commodity.upper()}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(img, f"VISUAL AI: {text_status} ({int(status_score)}%)", (30, 440), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    
    if int(time.time()) % 2 == 0: 
        cv2.circle(img, (600, 40), 10, (0, 0, 255), -1) 
    cv2.putText(img, "REC", (530, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return img

# --- FUNGSI AI LOKAL (AGRESIF & FONT BESAR) ---
def analyze_image_local(frame, item_name):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    height, width, _ = frame.shape
    detected_count = 0
    global_status = "TIDAK TERDETEKSI"
    
    if item_name == "Bayam":
        lower_wilt = np.array([15, 50, 50])
        upper_wilt = np.array([35, 255, 255])
        mask_wilt = cv2.inRange(hsv, lower_wilt, upper_wilt)
        wilt_pixels = cv2.countNonZero(mask_wilt)
        score = (wilt_pixels / (height * width)) * 100 * 5
        
        if score > 20: 
            global_status = f"LAYU/BUSUK ({int(score)}%)"; color_res = (0, 0, 255)
        else:
            global_status = "SEGAR"; color_res = (0, 255, 0)
        
        cv2.rectangle(frame, (0, height-40), (width, height), (0,0,0), -1)
        cv2.putText(frame, f"BAYAM: {global_status}", (10, height-10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color_res, 3)
        return frame, global_status, 1, score

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
        rot_found = False
        max_score = 0

        if len(contours) > 0:
            global_status = "BAGUS"
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 1500: continue 
                x, y, w, h = cv2.boundingRect(cnt)
                detected_count += 1
                roi_hsv = hsv[y:y+h, x:x+w]
                rot_ratio, thresh = 0, 0
                
                # --- SENSITIVITAS AGRESIF ---
                if item_name == "Tomat":
                    mask_rot = cv2.inRange(roi_hsv, (0, 10, 0), (180, 255, 130))
                    rot_ratio = (cv2.countNonZero(mask_rot) / (w*h)) * 100
                    thresh = 1.5 
                elif item_name == "Pisang":
                    mask_rot = cv2.inRange(roi_hsv, (0, 30, 0), (180, 255, 110))
                    rot_ratio = (cv2.countNonZero(mask_rot) / (w*h)) * 100
                    thresh = 10.0 
                
                if rot_ratio > max_score: max_score = rot_ratio

                if rot_ratio > thresh:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 3)
                    # Font 1.2 & Tebal 3
                    cv2.putText(frame, f"BUSUK {int(rot_ratio)}%", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,0,255), 3)
                    rot_found = True
                else:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 3)
                    # Font 1.2 & Tebal 3
                    cv2.putText(frame, "SEGAR", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,255,0), 3)
        
        if rot_found: global_status = "ADA BUSUK"
        elif detected_count > 0: global_status = "SEGAR"
        else: max_score = 0
        
        return frame, global_status, detected_count, max_score

# ==========================================
# HALAMAN 1: HOME (MENU UTAMA)
# ==========================================
if st.session_state['page'] == 'home':
    c1, c2, c3 = st.columns([1.5, 1, 1.5])
    with c2:
        if os.path.exists("logo.png"): 
            st.image("logo.png", width="stretch")
        else: 
            st.markdown("<div style='text-align:center; font-size:80px;'>🛡️</div>", unsafe_allow_html=True)
    
    st.markdown("<h1>FIG: Food Inventory Guardian</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Sistem Monitoring Cerdas Gudang Penyimpanan</p>", unsafe_allow_html=True)
    
    col_guide1, col_guide2, col_guide3 = st.columns([1, 2, 1])
    with col_guide2:
        if st.button("📖 BUKA MANUAL BOOK / PANDUAN PENGGUNAAN", width="stretch"):
            st.session_state['page'] = 'guide'
            st.rerun()

    st.markdown("---")
    st.markdown("### 1️⃣ Pilih Mode Operasi")
    
    m1, m2 = st.columns(2)
    with m1:
        if st.button("📡 MODE REALTIME", type="primary" if not st.session_state['init_sim'] else "secondary", width="stretch"):
            st.session_state['init_sim'] = False
            st.rerun()
    with m2:
        if st.button("🛠️ MODE SIMULASI", type="primary" if st.session_state['init_sim'] else "secondary", width="stretch"):
            st.session_state['init_sim'] = True
            st.rerun()
    
    # --- RATA TENGAH ---
    st.markdown("<br><h3 style='text-align: center;'>2️⃣ Pilih Komoditas</h3>", unsafe_allow_html=True)
    
    c_pisang, c_tomat, c_bayam = st.columns(3)
    
    def start_dashboard(item):
        st.session_state['commodity'] = item
        st.session_state['data_history'] = pd.DataFrame(columns=['Waktu', 'Komoditas', 'Suhu', 'Lembab', 'Sisa Umur', 'Status'])
        if st.session_state['init_sim']: 
            st.session_state.update(sim_temp=27.0, sim_hum=70.0, sim_score=5.0)
        st.session_state['page'] = 'dashboard'
        st.rerun()
        
    with c_pisang: 
        if st.button("🍌 PISANG", width="stretch"): start_dashboard("Pisang")
    with c_tomat: 
        if st.button("🍅 TOMAT", width="stretch"): start_dashboard("Tomat")
    with c_bayam: 
        if st.button("🥬 BAYAM", width="stretch"): start_dashboard("Bayam")

# ==========================================
# HALAMAN 2: USER GUIDE (MANUAL BOOK) - DIPERBAIKI
# ==========================================
elif st.session_state['page'] == 'guide':
    st.sidebar.button("⬅️ Kembali ke Menu Utama", on_click=lambda: st.session_state.update(page='home'))
    st.markdown("<h1>📖 Panduan Penggunaan FIG</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Dokumentasi Resmi Food Inventory Guardian</p>", unsafe_allow_html=True)
    
    if os.path.exists("logo.png"):
        lc1, lc2, lc3 = st.columns([2, 1, 2])
        with lc2: st.image("logo.png", width="stretch")

    st.markdown("---")
    
    with st.expander("🛠️ 1. Memahami Mode Operasi (Realtime vs Simulasi)", expanded=True):
        st.markdown("""
        <div class='guide-text'>
        Sistem FIG memiliki dua mode operasi yang dapat dipilih di halaman utama:
        <ul>
        <li><b>📡 MODE REALTIME:</b> Menggunakan data asli dari sensor (DHT22) dan Kamera (ESP32-CAM). Gunakan mode ini saat alat perangkat keras terhubung.</li>
        <li><b>🛠️ MODE SIMULASI:</b> Menggunakan data palsu (dummy) yang bisa diatur menggunakan slider. Mode ini berguna untuk presentasi atau pengujian logika sistem tanpa perangkat keras.</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)

    with st.expander("📊 2. Membaca Dashboard & Grafik"):
        st.markdown("""
        <div class='guide-text'>
        Dashboard dibagi menjadi dua area utama:
        <ul>
        <li><b>🔴 Live Camera (Kiri):</b> Menampilkan snapshot terbaru dari gudang. AI akan mendeteksi warna buah secara otomatis.</li>
        <li><b>⏳ Prediksi Umur Simpan (Kanan Atas):</b> Menampilkan sisa waktu (Jam) sebelum buah menjadi tidak layak jual.</li>
        <li><b>🌡️ Kondisi Lingkungan (Kanan Bawah):</b> Menampilkan suhu & kelembaban gudang dibandingkan dengan cuaca luar.</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)
        
    with st.expander("🚨 3. Arti Notifikasi & Alert"):
        st.markdown("""
        <div class='guide-text'>
        Sistem akan memberikan peringatan (Alert) di bagian atas dashboard:
        <br><br>
        <table>
        <tr>
        <th>Pesan</th>
        <th>Arti</th>
        <th>Tindakan Sistem</th>
        </tr>
        <tr>
        <td>✅ STATUS AMAN</td>
        <td>Suhu normal, buah segar.</td>
        <td>Kipas & Mist OFF.</td>
        </tr>
        <tr>
        <td>⚠️ SUHU PANAS</td>
        <td>Suhu gudang > 30°C.</td>
        <td><b>Kipas (Fan) Otomatis MENYALA.</b></td>
        </tr>
        <tr>
        <td>💧 MELEMBABKAN</td>
        <td>Kelembaban Bayam < 60%.</td>
        <td><b>Humidifier (Mist) Otomatis MENYALA.</b></td>
        </tr>
        <tr>
        <td>🚨 BUSUK TERDETEKSI</td>
        <td>Kamera mendeteksi warna buah tidak wajar.</td>
        <td>Mengirim <b>Notifikasi Telegram</b> ke manajer.</td>
        </tr>
        </table>
        </div>
        """, unsafe_allow_html=True)

    with st.expander("📱 4. Integrasi Telegram"):
        st.markdown("""
        <div class='guide-text'>
        Sistem akan mengirim pesan ke Telegram secara otomatis jika:
        <ol>
        <li>Terdeteksi <b>BUAH BUSUK</b> secara visual.</li>
        <li><b>SUHU EKSTREM</b> (sangat panas) yang berpotensi merusak stok.</li>
        <li><b>SISA UMUR SIMPAN</b> kurang dari 12 Jam.</li>
        </ol>
        <i>Pesan Telegram juga berisi rekomendasi tindakan, seperti "Beri Diskon" atau "Cek Ventilasi".</i>
        </div>
        """, unsafe_allow_html=True)
        
    if st.button("⬅️ Kembali ke Menu Utama", width="stretch"):
        st.session_state['page'] = 'home'
        st.rerun()

# ==========================================
# HALAMAN 3: DASHBOARD (LAYOUT KLASIK + SIMULASI UPLOAD)
# ==========================================
else:
    # --- A. SIDEBAR NAVIGASI & KONTROL ---
    st.sidebar.markdown("### Navigasi")
    if st.sidebar.button("⬅️ Ganti Komoditas", width="stretch"): 
        st.session_state['page'] = 'home'
        st.rerun()
    st.sidebar.markdown("---")
    
    sim_mode = st.session_state['init_sim']
    uploaded_file = None
    
    # --- LOGIKA SIDEBAR: REALTIME VS SIMULASI ---
    if sim_mode:
        # TAMPILAN SIDEBAR SIMULASI (TANPA UPLOAD, HANYA SLIDER)
        st.sidebar.header("🛠️ Panel Simulasi")
        st.sidebar.info("Atur kondisi lingkungan & visual (Dummy).")
        
        if st.sidebar.button("🔄 Reset Aman"):
            st.session_state.update(sim_temp=27.0, sim_hum=70.0, sim_score=5.0)
            st.rerun()

        sim_t = st.sidebar.slider("Suhu (°C)", 15.0, 45.0, key='sim_temp')
        sim_h = st.sidebar.slider("Kelembaban (%)", 0, 100, key='sim_hum')
        
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📸 Input Visual (Dummy)")
        # FITUR UPLOAD DIHAPUS, LANGSUNG SLIDER
        sim_s = st.sidebar.slider("Tingkat Busuk Dummy (%)", 0, 100, key='sim_score')
            
        save_cfg(st.session_state['commodity'], True, sim_t, sim_h, sim_s)
    
    else:
        # TAMPILAN SIDEBAR REALTIME
        st.sidebar.success("✅ Realtime Connected")
        st.sidebar.info("Menggunakan data dari sensor & kamera asli.")
        save_cfg(st.session_state['commodity'], False)

    # FITUR DOWNLOAD DI SIDEBAR
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📥 Ekspor Data")
    if not st.session_state['data_history'].empty:
        csv = st.session_state['data_history'].to_csv(index=False).encode('utf-8')
        st.sidebar.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"fig_log_{st.session_state['commodity']}_{int(time.time())}.csv",
            mime="text/csv",
        )
    else:
        st.sidebar.caption("Menunggu data masuk...")

    # --- B. PERSIAPAN DATA (PROCESS LOGIC) ---
    data = {"sensor": {"temp":0, "hum":0}, "external":{}, "visual":{"status":"-", "score":0}, "decision":{}}
    if os.path.exists("system_state.json"):
        try: 
            with open("system_state.json") as f: 
                data = json.load(f)
        except: 
            pass

    # -- VARIABEL DEFAULT --
    temp = 0; hum = 0; alert = "-"; shelf = 0; vis_score = 0
    fan = "OFF"; mist = "OFF"
    img_display = None; img_caption = ""
    is_bgr = True # Flag untuk konversi warna

    if sim_mode:
        # === MODE SIMULASI (LOGIKA UTAMA) ===
        temp = sim_t
        hum = sim_h
        vis_score = sim_s # Nilai diambil langsung dari Slider
        
        # Gambar Dummy (Kartun)
        img_display = create_sim_image(st.session_state['commodity'], vis_score)
        img_caption = "Visual Simulasi (Dummy)"
        is_bgr = True

        # 2. HITUNG SHELF LIFE (RULE: BUSUK = 0 JAM)
        if vis_score > 65:
            shelf = 0.0
            alert = "🚨 BUSUK TERDETEKSI (DUMMY)"
        else:
            base_life = 168
            reduction = (temp - 25) * 5 + (vis_score * 1.5)
            shelf = max(0, round(base_life - reduction, 1))
            
            alert = "✅ STATUS AMAN"
            if temp > 30: alert = "⚠️ SUHU PANAS"
            if st.session_state['commodity'] == "Bayam" and hum < 60: alert = "💧 KERING (LEMBABKAN)"

        # 3. Hardware Simulation
        if temp > 30: fan = "ON"
        if st.session_state['commodity'] == "Bayam" and hum < 60: mist = "ON"
        
    else:
        # === MODE REALTIME (AMBIL DARI BACKEND) ===
        # ... (Kode bagian else/realtime biarkan sama seperti sebelumnya)
        temp = data['sensor'].get('temp', 0)
        hum = data['sensor'].get('hum', 0)
        alert = data.get('decision', {}).get('alert', '-')
        shelf = data.get('decision', {}).get('shelf_life', 0)
        vis_score = data.get('visual', {}).get('score', 0)
        fan = data.get('decision', {}).get('fan', 'OFF')
        mist = data.get('decision', {}).get('mist', 'OFF')
        
        # Gambar Live CCTV
        img_display = f"http://localhost:5555/snapshot?t={time.time()}"
        img_caption = f"Live CCTV: {st.session_state['commodity']}"
        is_bgr = False

    # --- C. TAMPILAN DASHBOARD ---
    last_ts = data.get('timestamp', time.time())
    ext_t = data.get('external', {}).get('temp', 0)
    
    hd1, hd2 = st.columns([3, 1])
    with hd1: st.markdown(f"<h2 style='text-align:left;'>🛡️ Monitoring: {st.session_state['commodity']}</h2>", unsafe_allow_html=True)
    with hd2: st.metric("Last Update", datetime.fromtimestamp(last_ts).strftime('%H:%M:%S'))

    if "PANIC" in alert or "WARNING" in alert or "PANAS" in alert or "BUSUK" in alert: 
        st.error(f"🔥 {alert}", icon="⚠️")
    else: 
        st.success(f"✅ {alert}", icon="✅")
    st.markdown("---")

    col_left, col_right = st.columns([1.3, 1])

    # --- KOLOM KIRI (VISUAL) ---
    with col_left:
        st.subheader("Visual Monitoring")
        if isinstance(img_display, str): # URL String
            st.image(img_display, caption=img_caption, width="stretch")
        else: # Numpy Array
            st.image(img_display, caption=img_caption, channels="BGR" if is_bgr else "RGB", width="stretch")

    # UPDATE HISTORY
    current_time_str = datetime.now().strftime('%H:%M:%S')
    if st.session_state['data_history'].empty or current_time_str != st.session_state['data_history'].iloc[-1]['Waktu']:
         new_row = pd.DataFrame([{'Waktu': current_time_str, 'Komoditas': st.session_state['commodity'], 'Suhu': temp, 'Lembab': hum, 'Sisa Umur': shelf, 'Status': alert}])
         if st.session_state['data_history'].empty: st.session_state['data_history'] = new_row
         else: st.session_state['data_history'] = pd.concat([st.session_state['data_history'], new_row], ignore_index=True)
         if len(st.session_state['data_history']) > 100: st.session_state['data_history'] = st.session_state['data_history'].iloc[1:]

    # --- KOLOM KANAN (METRIK) ---
    with col_right:
        st.subheader("⏳ Prediksi Umur Simpan")
        prog_val = min(max(shelf / 72.0, 0.0), 1.0); pct = int(prog_val * 100)
        bar_color = "#2ecc71" if pct >= 50 else "#f1c40f" if pct >= 25 else "#e74c3c"
        
        cm1, cm2 = st.columns([1, 2])
        with cm1: st.metric("Sisa Waktu", f"{shelf} Jam")
        with cm2:
            st.caption(f"Kualitas: {pct}%")
            df_chart = pd.DataFrame({'Persen': [pct], 'Sisa': [100-pct]})
            bg = alt.Chart(pd.DataFrame({'val': [100]})).mark_bar(color="#333", size=25).encode(x=alt.X('val', axis=None))
            fg = alt.Chart(df_chart).mark_bar(color=bar_color, size=25).encode(x=alt.X('Persen', axis=None, scale=alt.Scale(domain=[0, 100])))
            st.altair_chart((bg + fg).properties(height=30), width="stretch")

        st.markdown("---")
        st.subheader("🌡️ Kondisi Lingkungan")
        e1, e2, e3, e4 = st.columns(4)
        
        # LABEL DIPERJELAS: GUDANG vs SUKABUMI
        with e1: st.metric("Suhu Gudang", f"{temp}°C", f"{temp-30:.1f}")
        with e2: st.metric("RH Gudang", f"{hum}%", f"{hum-60:.1f}")
        with e3: st.metric("Sukabumi (Luar)", f"{ext_t}°C", help="Data Live dari OpenWeatherMap")
        with e4: st.info(f"{data.get('external', {}).get('desc', '-').upper()}")
                 
        st.markdown("---")
        st.subheader("⚙️ Status Perangkat")
        
        if sim_mode:
            st.info("Status Virtual (Simulasi)")
            
        alert_on = "ON" if "BUSUK" in alert or "PANAS" in alert else "OFF"
        
        h1, h2, h3 = st.columns(3)
        with h1: 
            st.write("Fan")
            st.markdown(f'<div class="hardware-badge-{"on" if fan=="ON" else "off"}">{fan}</div>', unsafe_allow_html=True)
        with h2: 
            st.write("Mist")
            st.markdown(f'<div class="hardware-badge-{"on" if mist=="ON" else "off"}">{mist}</div>', unsafe_allow_html=True)
        with h3: 
            st.write("LED")
            st.markdown(f'<div class="hardware-badge-{"on" if alert_on=="ON" else "off"}">{alert_on}</div>', unsafe_allow_html=True)

    # --- E. BAGIAN BAWAH: TABEL & GRAFIK (KLASIK) ---
    st.markdown("---")
    st.subheader("📊 Analisis Data Tren")
    
    tab_chart, tab_data = st.tabs(["📈 Grafik Live", "📄 Data Tabel"])
    
    with tab_chart:
        if not st.session_state['data_history'].empty:
            df_melt = st.session_state['data_history'].melt(
                'Waktu', 
                ['Suhu', 'Lembab', 'Sisa Umur'], 
                var_name='Parameter', 
                value_name='Nilai'
            )
            chart = alt.Chart(df_melt).mark_line(point=True).encode(
                x='Waktu', 
                y='Nilai', 
                color='Parameter', 
                tooltip=['Waktu', 'Parameter', 'Nilai']
            ).interactive()
            st.altair_chart(chart, width="stretch")
        else:
            st.info("Belum ada data terekam. Aktifkan Mode Live untuk mulai merekam data.")

    with tab_data:
        st.dataframe(st.session_state['data_history'].sort_index(ascending=False), width="stretch")

    time.sleep(2)
    st.rerun()
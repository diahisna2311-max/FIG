import streamlit as st
import json
import time
import os
import pandas as pd
import altair as alt 
import numpy as np 
import cv2         
from datetime import datetime

# ==========================================
# 1. KONFIGURASI & CSS
# ==========================================
st.set_page_config(
    page_title="FIG - Smart Warehouse",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    /* Global Background & Padding */
    .block-container { padding-top: 2rem; padding-bottom: 3rem; }
    
    /* Style untuk Kartu Metrik */
    div[data-testid="stMetric"] {
        background-color: #1E1E1E; 
        border: 1px solid #333;
        padding: 10px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    div[data-testid="stMetricLabel"] p { color: #AAA !important; font-size: 13px; }
    div[data-testid="stMetricValue"] div { color: #FFF !important; font-size: 24px; font-weight: bold; }
    
    /* Tombol Besar */
    .stButton button { 
        width: 100%;
        height: 70px;
        font-size: 18px !important;
        font-weight: bold !important;
        border-radius: 10px !important;
        transition: 0.3s;
        border: 2px solid #444;
    }
    .stButton button:hover {
        border-color: #ff4b4b;
        color: #ff4b4b;
    }

    /* Badge Status Hardware */
    .hardware-badge-on {
        background-color: #f1c40f; color: #000; padding: 8px 15px; 
        border-radius: 20px; font-weight: bold; text-align: center; border: 2px solid #d4ac0d;
        margin-bottom: 10px;
    }
    .hardware-badge-off {
        background-color: #27ae60; color: #fff; padding: 8px 15px; 
        border-radius: 20px; font-weight: bold; text-align: center; border: 2px solid #1e8449;
        margin-bottom: 10px;
    }
    
    h1, h2, h3 { color: #EEE !important; text-align: center; }
    
    /* Style Text Guide */
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

# History Data (DataFrame)
if 'data_history' not in st.session_state:
    st.session_state['data_history'] = pd.DataFrame(columns=['Waktu', 'Komoditas', 'Suhu (°C)', 'Kelembaban (%)', 'Sisa Umur (Jam)', 'Status'])

def save_cfg(com, sim=False, t=28, h=60, s=0):
    try:
        with open("dashboard_config.json", "w") as f:
            json.dump({"commodity": com, "sim_mode": sim, "sim_temp": t, "sim_hum": h, "sim_score": s}, f)
    except: pass

def create_sim_image(commodity, status_score):
    # Logika Warna Background berdasarkan Komoditas
    if commodity == "Pisang": bg_color = (80, 200, 255) # Kuning-ish
    elif commodity == "Tomat": bg_color = (80, 80, 220) # Merah-ish
    else: bg_color = (80, 180, 80) # Hijau
    
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = bg_color 
    
    text_status = "MENTAH/SEGAR"
    if status_score > 25: text_status = "MATANG"
    if status_score > 65: text_status = "BUSUK"
    
    cv2.putText(img, f"SIMULASI: {commodity.upper()}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(img, f"VISUAL AI: {text_status} ({int(status_score)}%)", (30, 440), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    
    # Indikator Kedip (Recording)
    if int(time.time()) % 2 == 0:
        cv2.circle(img, (600, 40), 10, (0, 0, 255), -1) 
    cv2.putText(img, "REC", (530, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return img

def get_smart_recommendation(shelf_life, commodity, status_alert):
    if shelf_life <= 0:
        return "🚨 **STOK RUSAK:** Segera keluarkan dari gudang untuk mencegah kontaminasi ke stok lain.", "error"
    elif shelf_life <= 48:
        return f"⚠️ **TINDAKAN CEPAT:** Sisa umur {commodity} < 2 hari. Rekomendasi: Beri diskon 50% atau olah menjadi produk turunan segera.", "warning"
    elif shelf_life <= 72:
        return f"💡 **STRATEGI PENJUALAN:** Stok harus dipindahkan ke area display utama. Prioritaskan pengiriman ke toko terdekat.", "info"
    elif "PANAS" in status_alert:
        return "🌡️ **OPTIMASI LINGKUNGAN:** Suhu terlalu tinggi. Pastikan ventilasi tidak terhalang dan kipas bekerja maksimal.", "warning"
    else:
        return "✅ **KONDISI OPTIMAL:** Stok dalam keadaan segar. Pertahankan suhu dan kelembaban saat ini.", "success"

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
        if st.button("📖 BUKA MANUAL BOOK / PANDUAN PENGGUNAAN", use_container_width=True):
            st.session_state['page'] = 'guide'
            st.rerun()

    st.markdown("---")

    st.markdown("### 1️⃣ Pilih Mode Operasi")
    cur_mode = "🛠️ SIMULASI" if st.session_state['init_sim'] else "📡 REALTIME"
    st.info(f"Mode Terpilih: **{cur_mode}**")

    m1, m2 = st.columns(2)
    with m1:
        is_rt = not st.session_state['init_sim']
        if st.button("📡 MODE REALTIME", type="primary" if is_rt else "secondary", use_container_width=True):
            st.session_state['init_sim'] = False
            st.rerun()
    with m2:
        is_sim = st.session_state['init_sim']
        if st.button("🛠️ MODE SIMULASI", type="primary" if is_sim else "secondary", use_container_width=True):
            st.session_state['init_sim'] = True
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 2️⃣ Pilih Komoditas & Mulai")
    
    c_pisang, c_tomat, c_bayam = st.columns(3)

    def start_dashboard(item):
        st.session_state['commodity'] = item
        
        # Reset data history saat mulai baru
        st.session_state['data_history'] = pd.DataFrame(columns=['Waktu', 'Komoditas', 'Suhu (°C)', 'Kelembaban (%)', 'Sisa Umur (Jam)', 'Status'])
        
        # Jika mode simulasi, reset nilai slider ke Default Aman
        if st.session_state['init_sim']:
            st.session_state['sim_temp'] = 27.0
            st.session_state['sim_hum'] = 70.0
            st.session_state['sim_score'] = 5.0

        st.session_state['page'] = 'dashboard'
        st.rerun()

    with c_pisang:
        if st.button("🍌 PISANG", use_container_width=True): start_dashboard("Pisang")
    with c_tomat:
        if st.button("🍅 TOMAT", use_container_width=True): start_dashboard("Tomat")
    with c_bayam:
        if st.button("🥬 BAYAM", use_container_width=True): start_dashboard("Bayam")

# ==========================================
# HALAMAN 2: USER GUIDE
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
# HALAMAN 3: DASHBOARD (MONITORING)
# ==========================================
else:
    # --- SIDEBAR NAVIGASI & KONTROL ---
    st.sidebar.markdown("### Navigasi")
    if st.sidebar.button("⬅️ Ganti Komoditas", use_container_width=True):
        st.session_state['page'] = 'home'
        st.rerun()
    
    st.sidebar.markdown("---")
    
    sim_mode = st.session_state['init_sim']
    sim_t, sim_h, sim_s = 28.0, 60.0, 0.0

    if sim_mode:
        st.sidebar.header("🛠️ Kontrol Simulasi")
        st.sidebar.warning("Mode Simulasi Aktif")
        
        # --- DEFINISI NILAI AMAN (DEFAULT) ---
        SAFE_TEMP = 27.0  # Suhu Sejuk
        SAFE_HUM = 70     # Kelembaban Cukup
        SAFE_SCORE = 5    # Visual Segar (0-100)

        # Inisialisasi Session State jika belum ada
        if 'sim_temp' not in st.session_state: st.session_state['sim_temp'] = SAFE_TEMP
        if 'sim_hum' not in st.session_state: st.session_state['sim_hum'] = SAFE_HUM
        if 'sim_score' not in st.session_state: st.session_state['sim_score'] = SAFE_SCORE

        # Tombol RESET
        if st.sidebar.button("🔄 Reset ke Aman", type="primary", use_container_width=True):
            st.session_state['sim_temp'] = SAFE_TEMP
            st.session_state['sim_hum'] = SAFE_HUM
            st.session_state['sim_score'] = SAFE_SCORE
            st.rerun()

        # Slider Kontrol (Terkoneksi ke Session State)
        sim_t = st.sidebar.slider("Suhu (°C)", 15.0, 45.0, key='sim_temp')
        sim_h = st.sidebar.slider("Kelembaban (%)", 0, 100, key='sim_hum')
        sim_s = st.sidebar.slider("Kematangan Visual (%)", 0, 100, key='sim_score')
        
        save_cfg(st.session_state['commodity'], True, sim_t, sim_h, sim_s)
    else:
        st.sidebar.success("✅ Mode Realtime")
        save_cfg(st.session_state['commodity'], False)

    # --- SIDEBAR UNDUH DATA ---
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📥 Ekspor Data")
    if not st.session_state['data_history'].empty:
        csv = st.session_state['data_history'].to_csv(index=False).encode('utf-8')
        st.sidebar.download_button(
            label="Download Data (CSV)",
            data=csv,
            file_name=f"fig_log_{st.session_state['commodity']}_{int(time.time())}.csv",
            mime="text/csv",
        )
    else:
        st.sidebar.caption("Belum ada data terekam.")

    # --- LOAD DATA BACKEND ---
    data = {"sensor": {"temp":0, "hum":0}, "external":{}, "visual":{"status":"-", "score":0}, "decision":{}}
    if os.path.exists("system_state.json"):
        try: 
            with open("system_state.json") as f: data = json.load(f)
        except: pass

    com = st.session_state['commodity']
    temp = data['sensor'].get('temp', 0)
    hum = data['sensor'].get('hum', 0)
    alert = data.get('decision', {}).get('alert', '-')
    shelf = data.get('decision', {}).get('shelf_life', 0)
    vis_score = data.get('visual', {}).get('score', 0)
    last_ts = data.get('timestamp', time.time())
    
    ext = data.get('external', {})
    ext_t = ext.get('temp', 0)

    # --- LOGGING DATA ---
    current_time_str = datetime.fromtimestamp(last_ts).strftime('%H:%M:%S')
    
    if st.session_state['data_history'].empty or current_time_str != st.session_state['data_history'].iloc[-1]['Waktu']:
        new_row = pd.DataFrame([{
            'Waktu': current_time_str,
            'Komoditas': com,
            'Suhu (°C)': temp,
            'Kelembaban (%)': hum,
            'Sisa Umur (Jam)': shelf,
            'Status': alert
        }])
        
        if st.session_state['data_history'].empty:
            st.session_state['data_history'] = new_row
        else:
            st.session_state['data_history'] = pd.concat([st.session_state['data_history'], new_row], ignore_index=True)
            
        if len(st.session_state['data_history']) > 100:
             st.session_state['data_history'] = st.session_state['data_history'].iloc[1:]

    # --- HEADER ---
    hd1, hd2 = st.columns([3, 1])
    with hd1: st.markdown(f"<h2 style='text-align:left;'>🛡️ Monitoring: {com}</h2>", unsafe_allow_html=True)
    with hd2: st.metric("Last Update", datetime.fromtimestamp(last_ts).strftime('%H:%M:%S'))

    # ALERT BANNER
    if "PANIC" in alert or "WARNING" in alert or "PANAS" in alert or "BUSUK" in alert or "KRITIS" in alert:
        st.error(f"🔥 {alert}", icon="⚠️")
    else:
        st.success(f"✅ {alert}", icon="✅")
    
    st.markdown("---")

    # --- MAIN CONTENT LAYOUT ---
    col_left, col_right = st.columns([1.3, 1])

    with col_left:
        st.subheader(f"🔴 Live Camera")
        if sim_mode:
            img_show = create_sim_image(com, vis_score)
            st.image(img_show, channels="BGR", width="stretch")
        else:
            # Gunakan timestamp untuk mencegah cache gambar
            st.image(f"http://localhost:5555/snapshot?t={time.time()}", caption=f"CCTV: {com}", width="stretch")

    with col_right:
        st.subheader("⏳ Prediksi Umur Simpan")
        prog_val = min(max(shelf / 72.0, 0.0), 1.0)
        pct = int(prog_val * 100)
        
        bar_color = "#2ecc71" 
        status_txt = "AMAN"
        if pct < 25: bar_color = "#e74c3c"; status_txt = "KRITIS!"
        elif pct < 50: bar_color = "#f1c40f"; status_txt = "WASPADA"

        cm1, cm2 = st.columns([1, 2])
        with cm1: st.metric("Sisa Waktu", f"{shelf} Jam")
        with cm2:
            st.caption(f"Kualitas: {pct}% ({status_txt})")
            df_chart = pd.DataFrame({'Persen': [pct], 'Sisa': [100-pct]})
            bg_bar = alt.Chart(pd.DataFrame({'val': [100]})).mark_bar(color="#333", size=25).encode(x=alt.X('val', axis=None))
            fg_bar = alt.Chart(df_chart).mark_bar(color=bar_color, size=25).encode(
                x=alt.X('Persen', axis=None, scale=alt.Scale(domain=[0, 100])))
            
            st.altair_chart((bg_bar + fg_bar).properties(height=30), width="stretch")

        st.markdown("---")
        
        st.subheader("🌡️ Kondisi Lingkungan")
        env1, env2, env3, env4 = st.columns(4)
        with env1:
            st.caption("📦 Gudang")
            st.metric("Suhu", f"{temp}°C", delta=f"{temp-30:.1f}")
        with env2:
            st.caption("📦 Lembab")
            st.metric("RH", f"{hum}%", delta=f"{hum-60:.1f}")
        with env3:
            st.caption(f"☁️ Luar")
            st.metric("Suhu", f"{ext_t}°C")
        with env4:
            st.caption(f"☁️ Cuaca")
            st.info(f"{ext.get('desc', '-').upper()}")
            
        st.markdown("---")

        st.subheader("⚙️ Status Perangkat")
        fan_state = data.get('decision', {}).get('fan', 'OFF')
        mist_state = data.get('decision', {}).get('mist', 'OFF')
        alert_state = "ON" if "BUSUK" in alert or "PANAS" in alert or "KERING" in alert else "OFF"
        
        h1, h2, h3 = st.columns(3)
        with h1:
            st.write("**Fan (Kipas)**")
            if fan_state == "ON": st.markdown('<div class="hardware-badge-on">⚠️ ON</div>', unsafe_allow_html=True)
            else: st.markdown('<div class="hardware-badge-off">✅ OFF</div>', unsafe_allow_html=True)
        with h2:
            st.write("**Mist (Embun)**")
            if mist_state == "ON": st.markdown('<div class="hardware-badge-on">⚠️ ON</div>', unsafe_allow_html=True)
            else: st.markdown('<div class="hardware-badge-off">✅ OFF</div>', unsafe_allow_html=True)
        with h3:
            st.write("**Led Merah**")
            if alert_state == "ON" or fan_state == "ON" or mist_state == "ON": 
                st.markdown('<div class="hardware-badge-on">🔴 ON</div>', unsafe_allow_html=True)
            else: 
                st.markdown('<div class="hardware-badge-off">⚪ OFF</div>', unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("🤖 Rekomendasi ")

        # Panggil fungsi rekomendasi
        rec_text, rec_type = get_smart_recommendation(shelf, st.session_state['commodity'], alert)

        # Tampilkan box berdasarkan tipe (success, info, warning, atau error)
        if rec_type == "success":
            st.success(rec_text)
        elif rec_type == "info":
            st.info(rec_text)
        elif rec_type == "warning":
            st.warning(rec_text)
        else:
            st.error(rec_text)

    # --- BAGIAN BAWAH: GRAFIK DAN TABEL DATA ---
    st.markdown("---")
    st.subheader("📊 Analisis Data Terkini")
    
    tab_grafik, tab_tabel = st.tabs(["📈 Grafik Tren", "📄 Tabel Data"])
    
    with tab_grafik:
        if not st.session_state['data_history'].empty:
            df_chart = st.session_state['data_history'].copy()
            df_melt = df_chart.melt(
                'Waktu', 
                ['Suhu (°C)', 'Kelembaban (%)', 'Sisa Umur (Jam)'], 
                var_name='Parameter', 
                value_name='Nilai'
            )
            
            line_chart = alt.Chart(df_melt).mark_line(point=True).encode(
                x=alt.X('Waktu', title='Waktu'),
                y=alt.Y('Nilai', title='Nilai'),
                color='Parameter',
                tooltip=['Waktu', 'Parameter', 'Nilai']
            ).interactive()
            
            st.altair_chart(line_chart, width="stretch")
        else:
            st.info("Menunggu data masuk...")

    with tab_tabel:
        st.dataframe(st.session_state['data_history'].sort_index(ascending=False), width="stretch")

    time.sleep(2)
    st.rerun()
/* * PROJECT: FIG - Node B (Control Unit)
 * DEVICE: ESP32 DevKit V1
 * FUNGSI: Sensor, Relay, LED, & Serial Monitor Log
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include "DHT.h"

// --- 1. KONFIGURASI WIFI & MQTT ---
const char* ssid = "LABCOM MAN 1 Kota Sukabumi";       
const char* password = "@Userlabcom1234"; 
const char* mqtt_server = "broker.hivemq.com"; 

// --- 2. PIN DEFINITIONS ---
#define DHTPIN 4        
#define DHTTYPE DHT11

#define RELAY_FAN 18    
#define RELAY_MIST 5   
#define LED_GREEN 19    
#define LED_RED 21      

// KONFIGURASI RELAY (Ubah jika logika terbalik)
#define RELAY_ON LOW
#define RELAY_OFF HIGH

DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient client(espClient);

bool isFanOn = false;
bool isMistOn = false;
bool isAlertOn = false; 

void setup() {
  Serial.begin(115200);
  
  pinMode(RELAY_FAN, OUTPUT);
  pinMode(RELAY_MIST, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  
  digitalWrite(RELAY_FAN, RELAY_OFF);
  digitalWrite(RELAY_MIST, RELAY_OFF);
  digitalWrite(LED_GREEN, HIGH);
  digitalWrite(LED_RED, LOW);
  
  dht.begin();
  
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected");
  
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void updateStatusLEDs() {
  if (isFanOn || isMistOn || isAlertOn) {
    digitalWrite(LED_GREEN, LOW);  
    digitalWrite(LED_RED, HIGH);   
  } else {
    digitalWrite(LED_GREEN, HIGH); 
    digitalWrite(LED_RED, LOW);    
  }
}

void callback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.print("CMD ["); Serial.print(topic); Serial.print("]: "); Serial.println(message);
  
  if (String(topic) == "fig/control/fan") {
    if (message == "ON") {
      digitalWrite(RELAY_FAN, RELAY_ON);
      isFanOn = true;
    } else {
      digitalWrite(RELAY_FAN, RELAY_OFF);
      isFanOn = false;
    }
  } 
  else if (String(topic) == "fig/control/mist") {
    if (message == "ON") {
      digitalWrite(RELAY_MIST, RELAY_ON);
      isMistOn = true;
    } else {
      digitalWrite(RELAY_MIST, RELAY_OFF);
      isMistOn = false;
    }
  }
  else if (String(topic) == "fig/control/alert") {
    if (message == "ON") {
      isAlertOn = true;
    } else {
      isAlertOn = false;
    }
  }
  
  updateStatusLEDs();
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect("FIG_Control_Node")) {
      client.subscribe("fig/control/#");
    } else {
      delay(5000);
    }
  }
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // --- BAGIAN PENGIRIMAN DATA ---
  static unsigned long lastMsg = 0;
  unsigned long now = millis();
  
  // Kirim setiap 2 detik (2000 ms)
  if (now - lastMsg > 2000) {
    lastMsg = now;
    float h = dht.readHumidity();
    float t = dht.readTemperature();

    if (!isnan(h) && !isnan(t)) {
      // 1. Buat Data JSON
      String payload = "{\"temp\": " + String(t) + ", \"hum\": " + String(h) + "}";
      
      // 2. Kirim ke MQTT
      client.publish("fig/sensor", payload.c_str());
      
      // 3. TAMPILKAN DI SERIAL MONITOR (Disini perubahannya)
      Serial.println("-----------------------------");
      Serial.print("🌡️ Suhu       : "); Serial.print(t); Serial.println(" °C");
      Serial.print("💧 Kelembaban : "); Serial.print(h); Serial.println(" %");
      Serial.print("📡 MQTT Payload: "); Serial.println(payload);
      Serial.println("-----------------------------");
    } else {
      Serial.println("⚠️ Gagal membaca sensor DHT11!");
    }
  }
}
// Firmware de la LED bicolore (consigne additionnelle 1).
// L'application envoie un mode : POST http://192.168.137.200/led?mode=<mode>&k=<LED_TOKEN>
// L'ESP gère seul durées et clignotements, sans bloquer (millis()).
//   off          éteinte (défaut)
//   green_blink  vert clignotant, jusqu'au mode suivant
//   green_fixed  vert fixe 30 s, puis extinction
//   red_blink10  rouge clignotant 10 fois, puis extinction
//   red_fixed    rouge fixe 30 s, puis extinction
#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include "secrets.h"   // WIFI_SSID, WIFI_PASS, LED_TOKEN (non versionné)

const uint8_t PIN_R = D5;   // GPIO14, patte rouge (vérifié au montage)
const uint8_t PIN_G = D7;   // GPIO13, patte verte (vérifié au montage)
const unsigned long BLINK_MS = 250, FIXED_MS = 30000;

IPAddress ip(192, 168, 137, 200), gw(192, 168, 137, 1), mask(255, 255, 255, 0);
ESP8266WebServer server(80);

enum Mode { OFF, GREEN_BLINK, GREEN_FIXED, RED_BLINK10, RED_FIXED };
const char* NAMES[] = {"off", "green_blink", "green_fixed", "red_blink10", "red_fixed"};
Mode mode = OFF;
unsigned long since = 0, lastToggle = 0;
bool on = false;
int toggles = 0;

void led(bool r, bool g) { digitalWrite(PIN_R, r); digitalWrite(PIN_G, g); }

void apply(Mode m) {
  mode = m; since = lastToggle = millis(); toggles = 0; on = (m != OFF);
  bool red = (m == RED_BLINK10 || m == RED_FIXED);
  led(on && red, on && !red);
  Serial.printf("mode %s\n", NAMES[m]);
}

void handleLed() {
  if (server.arg("k") != LED_TOKEN) { server.send(403, "text/plain", "forbidden"); return; }
  String m = server.arg("mode");
  for (int i = 0; i < 5; i++)
    if (m == NAMES[i]) { apply((Mode)i); server.send(200, "text/plain", m); return; }
  server.send(400, "text/plain", "unknown mode");
}

void setup() {
  pinMode(PIN_R, OUTPUT); pinMode(PIN_G, OUTPUT); led(false, false);
  pinMode(LED_BUILTIN, OUTPUT); digitalWrite(LED_BUILTIN, HIGH);   // LED bleue éteinte
  Serial.begin(115200);
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.config(ip, gw, mask);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print('.'); }
  Serial.printf("\nIP %s\n", WiFi.localIP().toString().c_str());
  server.on("/led", HTTP_POST, handleLed);
  server.on("/health", HTTP_GET, [] {
    server.send(200, "application/json",
                String("{\"mode\":\"") + NAMES[mode] + "\",\"rssi\":" + WiFi.RSSI() + "}");
  });
  server.begin();
}

void loop() {
  server.handleClient();
  unsigned long now = millis();
  switch (mode) {
    case GREEN_BLINK:
      if (now - lastToggle >= BLINK_MS) { lastToggle = now; on = !on; led(false, on); }
      break;
    case RED_BLINK10:
      if (now - lastToggle >= BLINK_MS) {
        lastToggle = now; on = !on; led(on, false);
        if (++toggles >= 19) apply(OFF);          // 10 allumages, puis extinction
      }
      break;
    case GREEN_FIXED:
    case RED_FIXED:
      if (now - since >= FIXED_MS) apply(OFF);
      break;
    default: break;
  }
}

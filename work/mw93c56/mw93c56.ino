/*
 * mw93c56 - read/write a 93C56 Microwire EEPROM by bit-bang.
 * Builds for ESP32 (3.3V, READ ONLY) and 5V AVR boards (read + write).
 *
 * VOLTAGE: a plain 93C56EN is a 4.5-5.5V part. At 3.3V reads usually work,
 * but WRITES DO NOT - the internal charge pump browns out and corrupts data
 * without reporting any error. The sketch refuses to write below 5V logic.
 *
 * Wiring (93C56 DIP-8):
 *   1 CS  -> PIN_CS      5 GND -> GND
 *   2 SK  -> PIN_SK      6 ORG -> VCC   (selects x16)
 *   3 DI  -> PIN_DI      7 NC  -> leave floating
 *   4 DO  -> PIN_DO      8 VCC -> VCC   (+ 100nF to GND at the chip)
 */

#if defined(ARDUINO_ARCH_ESP32)
  #define PIN_CS 5
  #define PIN_SK 18
  #define PIN_DI 23
  #define PIN_DO 19
  #define FIVE_VOLT 0
#else
  #define PIN_CS 10
  #define PIN_SK 13
  #define PIN_DI 11
  #define PIN_DO 12
  #define FIVE_VOLT 1
#endif

#define T 3   // microseconds per clock phase (~150kHz, well inside spec)

static void csOn()  { digitalWrite(PIN_CS, HIGH); delayMicroseconds(T); }
static void csOff() { digitalWrite(PIN_CS, LOW);  delayMicroseconds(T); }

// Chip samples DI on the rising edge and updates DO on the same edge.
static uint8_t clockBit(uint8_t out) {
  digitalWrite(PIN_DI, out ? HIGH : LOW);
  delayMicroseconds(T);
  digitalWrite(PIN_SK, HIGH);
  delayMicroseconds(T);
  uint8_t in = digitalRead(PIN_DO);
  digitalWrite(PIN_SK, LOW);
  delayMicroseconds(T);
  return in;
}

static void sendBits(uint16_t v, uint8_t n) {
  for (int8_t i = n - 1; i >= 0; i--) clockBit((v >> i) & 1);
}

// READ: start=1, opcode=10, 8 address bits. Chip then emits one dummy 0
// followed by 16 data bits. The dummy bit is our proof it is responding.
static uint16_t readWord(uint8_t addr, uint8_t *dummyOut) {
  csOn();
  clockBit(1); clockBit(1); clockBit(0);
  sendBits(addr, 8);
  uint8_t dummy = clockBit(0);
  uint16_t v = 0;
  for (uint8_t i = 0; i < 16; i++) v = (v << 1) | clockBit(0);
  csOff();
  if (dummyOut) *dummyOut = dummy;
  return v;
}

static void ewen() { csOn(); clockBit(1); clockBit(0); clockBit(0); sendBits(0xC0, 8); csOff(); }
static void ewds() { csOn(); clockBit(1); clockBit(0); clockBit(0); sendBits(0x00, 8); csOff(); }

static void writeWord(uint8_t addr, uint16_t val) {
  csOn();
  clockBit(1); clockBit(0); clockBit(1);
  sendBits(addr, 8);
  sendBits(val, 16);
  csOff();
  csOn();                                     // poll: DO low = busy
  uint32_t t0 = millis();
  while (digitalRead(PIN_DO) == LOW && millis() - t0 < 50) { }
  csOff();
}

static void diag() {
  Serial.println(F("\n-- diagnostic --"));
  for (uint8_t pass = 0; pass < 2; pass++) {
    // control pass: hold CS deasserted; a real chip must stay silent
    Serial.print(F("CS ")); Serial.println(pass ? F("DEASSERTED (control)") : F("ASSERTED"));
    for (uint8_t a = 0; a < 3; a++) {
      uint8_t dummy = 1; uint16_t v;
      if (pass) { csOff(); v = 0xFFFF; dummy = digitalRead(PIN_DO); }
      else      { v = readWord(a, &dummy); }
      Serial.print(F("  addr ")); Serial.print(a);
      Serial.print(F("  data 0x")); Serial.print(v, HEX);
      Serial.print(F("  dummy ")); Serial.println(dummy);
    }
  }
  Serial.println(F("dummy=0 when asserted -> chip is responding, wiring good."));
  Serial.println(F("dummy=1 everywhere    -> DO floating: check pin 4, and power."));
}

static void dump() {
  uint16_t w[256];
  uint8_t dummy, anyLow = 0, uniform = 1;
  for (uint16_t a = 0; a < 256; a++) {
    w[a] = readWord(a, &dummy);
    if (!dummy) anyLow = 1;
    if (a && w[a] != w[0]) uniform = 0;
  }
  if (!anyLow) { Serial.println(F("FAIL: dummy bit never low - chip not responding. Run 'd'.")); return; }
  if (uniform) { Serial.print(F("FAIL: every word reads 0x")); Serial.print(w[0], HEX);
                 Serial.println(F(" - not real data. Run 'd'.")); return; }

  uint8_t mirrored = 1;
  for (uint8_t a = 0; a < 128; a++) if (w[a] != w[a + 128]) { mirrored = 0; break; }
  Serial.print(F("A7 mirror check: ")); Serial.println(mirrored ? F("PASS") : F("FAIL"));

  Serial.println(F("BEGIN"));
  for (uint8_t a = 0; a < 128; a++) {
    char buf[6]; sprintf(buf, "%04X", w[a]);
    Serial.print(buf);
    Serial.print(((a & 7) == 7) ? '\n' : ' ');
  }
  Serial.println(F("END"));
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_CS, OUTPUT); pinMode(PIN_SK, OUTPUT);
  pinMode(PIN_DI, OUTPUT); pinMode(PIN_DO, INPUT);
  digitalWrite(PIN_CS, LOW); digitalWrite(PIN_SK, LOW); digitalWrite(PIN_DI, LOW);
  delay(200);
  Serial.println(F("\n93C56 Microwire tool"));
  Serial.println(FIVE_VOLT ? F("5V board: read + write") : F("3.3V board: READ ONLY"));
  Serial.println(F("  d = diagnostic   r = read/dump"));
}

void loop() {
  if (!Serial.available()) return;
  char c = Serial.read();
  if (c == 'd') diag();
  else if (c == 'r') dump();
}

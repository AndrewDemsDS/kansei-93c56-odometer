/*
 * ch341_93cxx - read/write 93Cxx Microwire EEPROMs via a CH341A.
 *
 * The CH341A's own SPI engine drives CS active-LOW; Microwire chip-select is
 * active-HIGH. So CS is driven by hand through the CH341's UIO (GPIO) stream
 * on D0, and only the clock/data phase is handed to the SPI engine.
 *
 * Wiring, 93C56 pin -> CH341A ZIF socket pin (board in 25-series/SPI position):
 *   1 CS  -> 1  (D0)      5 GND -> 4  (GND)
 *   2 SK  -> 6  (D3 SCK)  6 ORG -> 8  (VCC) for x16, GND for x8   [ST parts only]
 *   3 DI  -> 5  (D5 DO)   7 NC  -> leave floating
 *   4 DO  -> 2  (D7 DI)   8 VCC -> 8  (VCC)
 *
 * The CH341A's socket VCC is 5V, which is what a standard (non-"L") 93C56
 * wants. The usual CH341A 5V hazard applies to 3.3V SPI flash, not to this.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <libusb-1.0/libusb.h>

#define VID 0x1a86
#define PID 0x5512
#define EP_OUT 0x02
#define EP_IN  0x82
#define TIMEOUT 1000

#define CMD_I2C_STREAM  0xAA
#define CMD_I2C_STM_SET 0x60
#define CMD_I2C_STM_END 0x00
#define CMD_SPI_STREAM  0xA8
#define CMD_UIO_STREAM  0xAB
#define CMD_UIO_STM_DIR 0x40
#define CMD_UIO_STM_OUT 0x80
#define CMD_UIO_STM_END 0x20

/* D0=CS(ours, active high) D1,D2=unused CS lines D3=SCK D4=unused D5=DOUT */
#define PINS_CS_HIGH 0x07   /* 0b000111: D0=1 select, SCK=0 */
#define PINS_CS_LOW  0x06   /* 0b000110: D0=0 deselect      */

static libusb_device_handle *dev;
static uint8_t g_cs_on = PINS_CS_HIGH;
static uint8_t g_speed = 0x01;   /* CH341 stream speed index 0..3 */

/*
 * In-circuit use: the cluster MCU shares this Microwire bus and will drive
 * CS/SK/DI itself unless it is held in reset. Bits set here are forced LOW on
 * every pin update, so a CH341 pin wired to the MCU's (active-low) reset pad
 * holds the MCU off the bus for the whole session.
 */
static uint8_t g_force_low = 0x00;   /* flipped by diag to probe CS polarity */

/* CH341 SPI stream shifts LSB-first; Microwire is MSB-first. */
static uint8_t rev(uint8_t x)
{
	x = (x >> 4) | (x << 4);
	x = ((x & 0xCC) >> 2) | ((x & 0x33) << 2);
	x = ((x & 0xAA) >> 1) | ((x & 0x55) << 1);
	return x;
}

static int usb_wr(const uint8_t *buf, int len)
{
	int got;
	int r = libusb_bulk_transfer(dev, EP_OUT, (uint8_t *)buf, len, &got, TIMEOUT);
	if (r < 0 || got != len) {
		fprintf(stderr, "bulk out failed: %s (%d/%d)\n", libusb_error_name(r), got, len);
		return -1;
	}
	return 0;
}

static int usb_rd(uint8_t *buf, int len)
{
	int got;
	int r = libusb_bulk_transfer(dev, EP_IN, buf, len, &got, TIMEOUT);
	if (r < 0 || got != len) {
		fprintf(stderr, "bulk in failed: %s (%d/%d)\n", libusb_error_name(r), got, len);
		return -1;
	}
	return 0;
}

static int uio_set(uint8_t pins)
{
	pins &= (uint8_t)~g_force_low;
	{
	uint8_t p[] = { CMD_UIO_STREAM,
	                CMD_UIO_STM_DIR | 0x3F,   /* D0-D5 outputs */
	                CMD_UIO_STM_OUT | pins,
	                CMD_UIO_STM_END };
	return usb_wr(p, sizeof(p));
	}
}

/* Clock len bytes out on DI and simultaneously in from DO, CS held asserted. */
static int mw_frame(const uint8_t *tx, uint8_t *rx, int len)
{
	uint8_t pkt[32];
	uint8_t in[32];
	int i;

	if (len < 1 || len > 31) { fprintf(stderr, "frame len %d out of range\n", len); return -1; }

	if (uio_set(g_cs_on) < 0) return -1;

	pkt[0] = CMD_SPI_STREAM;
	for (i = 0; i < len; i++) pkt[1 + i] = rev(tx[i]);

	if (usb_wr(pkt, len + 1) < 0) return -1;
	if (usb_rd(in, len) < 0) return -1;

	if (uio_set(PINS_CS_LOW) < 0) return -1;

	if (rx) for (i = 0; i < len; i++) rx[i] = rev(in[i]);
	return 0;
}

/*
 * x16 READ, byte-aligned with 5 leading pad zeros (Microwire ignores anything
 * before the start bit):
 *   tx[0] = 00000 1 10   start bit + opcode 10 (READ)
 *   tx[1] = A7..A0
 *   tx[2..4] = clocked while the chip shifts out 1 dummy 0 + 16 data bits
 */
static int mw_read16(uint8_t addr, uint16_t *out)
{
	uint8_t tx[5] = { 0x06, addr, 0x00, 0x00, 0x00 };
	uint8_t rx[5];

	if (mw_frame(tx, rx, 5) < 0) return -1;

	/* rx[2]: b7=dummy0, b6..b0=D15..D9 | rx[3]=D8..D1 | rx[4] b7=D0 */
	*out = (uint16_t)(((rx[2] & 0x7F) << 9) | (rx[3] << 1) | (rx[4] >> 7));
	return 0;
}

/*
 * Drive each CH341 pin high in turn so the socket holes can be identified with
 * a multimeter. The board's silkscreen and jumper routing vary between
 * revisions, so this measures the mapping rather than assuming it.
 */
static void pinwalk(void)
{
	int i;
	printf("Pin walk - probe the socket holes, black lead on GND.\n");
	printf("Each pin is held high for 4 seconds. Note which hole follows it.\n");
	printf("Needed: D0=CS, D3=SCK, D5=MOSI. (D7=MISO is an input, found by\n");
	printf("elimination: the hole that never goes high and is not GND or VCC.)\n\n");
	for (i = 0; i <= 5; i++) {
		printf("  --> D%d HIGH now%s\n", i,
		       i == 0 ? "   [CS]" : i == 3 ? "   [SCK]" : i == 5 ? "   [MOSI]" : "");
		fflush(stdout);
		uio_set((uint8_t)(1 << i));
		sleep(4);
	}
	uio_set(0x00);
	printf("\nall pins low. Also find GND (continuity to USB shell) and VCC (~5V).\n");
}

static int mw_read_raw(uint8_t addr, uint8_t *rx5)
{
	uint8_t tx[5] = { 0x06, addr, 0x00, 0x00, 0x00 };
	return mw_frame(tx, rx5, 5);
}

/*
 * Is the chip actually talking? On a correct read the 93C56 drives DO low for
 * one dummy bit after the address, before the data. That bit appears even on a
 * blank chip, so it separates "not wired / not powered" from "genuinely erased".
 * Deasserting CS is the control: a selected chip must behave differently from
 * an unselected one, or it is not responding at all.
 */
static void diag(void)
{
	uint8_t rx[5], ref[5];
	int i, k, unstable = 0, responding = 0, ctrl_live = 0;
	int on_zero = 1, ctrl_ff = 1;
	uint8_t on = g_cs_on;
	uint8_t off = (on == PINS_CS_HIGH) ? PINS_CS_LOW : PINS_CS_HIGH;

	printf("Microwire response diagnostic\n=============================\n");
	printf("\nCS ASSERTED - each address read 5x to check repeatability:\n");

	g_cs_on = on;
	for (i = 0; i < 4; i++) {
		int stable = 1;
		if (mw_read_raw((uint8_t)i, ref) < 0) return;
		for (k = 1; k < 5; k++) {
			if (mw_read_raw((uint8_t)i, rx) < 0) return;
			if (memcmp(rx, ref, 5)) stable = 0;
		}
		printf("  addr %d:", i);
		for (k = 0; k < 5; k++) printf(" %02x", ref[k]);
		printf("   dummy=%d  %s\n", (ref[2] >> 7) & 1, stable ? "stable" : "UNSTABLE");
		if (!stable) unstable = 1;
		for (k = 0; k < 5; k++) {
			if (ref[k] != 0x00 && ref[k] != 0xFF) responding = 1;
			if (ref[k] != 0x00) on_zero = 0;
		}
	}

	printf("\nCS DEASSERTED (control - chip must stay silent):\n");
	g_cs_on = off;
	/* A deselected DO floats up through a weak pull-up, which takes time.
	 * Discard one read and settle, or the first sample reads stale-low. */
	mw_read_raw(0, rx);
	usleep(20000);
	for (i = 0; i < 4; i++) {
		if (mw_read_raw((uint8_t)i, rx) < 0) return;
		printf("  addr %d:", i);
		for (k = 0; k < 5; k++) printf(" %02x", rx[k]);
		printf("\n");
		for (k = 0; k < 5; k++) {
			if (rx[k] != 0x00 && rx[k] != 0xFF) ctrl_live = 1;
			if (rx[k] != 0xFF) ctrl_ff = 0;
		}
	}
	g_cs_on = on;

	printf("\nverdict: ");
	if (on_zero && ctrl_ff)
		printf("COMMAND PATH BROKEN - but the chip is alive.\n"
		       "         Selected it drives DO low; deselected DO floats high. Only a\n"
		       "         powered, correctly-selected chip does that, so VCC, GND, CS and\n"
		       "         DO are all good. It never shifts data out, so it is not seeing a\n"
		       "         valid command. Check, in this order:\n"
		       "           1. chip pin 2 (SK) -> socket pin 6 (CLK)\n"
		       "           2. chip pin 3 (DI) -> socket pin 5 (MOSI)\n"
		       "         Note SK and DI cross over: pin 2 goes to 6, pin 3 goes to 5.\n");
	else if (!responding)
		printf("NO RESPONSE - line stuck at 0x00/0xFF.\n"
		       "         Check DO (pin 4) -> socket pin 2, and the supply.\n");
	else if (ctrl_live)
		printf("CS NOT WORKING - chip answers when deselected.\n"
		       "         Check chip pin 1 -> socket pin 1.\n");
	else if (unstable)
		printf("RESPONDING BUT UNSTABLE - repeated reads of one address differ.\n"
		       "         The data cannot be trusted. Signal integrity, in order:\n"
		       "           1. 100nF cap across chip pins 8 and 5, AT the chip\n"
		       "           2. shorten every wire - under 10cm, ideally under 5\n"
		       "           3. separate DO from SK and DI, do not bundle them\n"
		       "           4. measure 5V under load at the chip legs, not the socket\n"
		       "           5. reseat GND - a marginal ground looks exactly like this\n");
	else
		printf("GOOD - responding, stable, silent when deselected. Proceed to dump3.sh\n");
}

static int mw_ewen(void) { uint8_t tx[2] = { 0x04, 0xC0 }; return mw_frame(tx, NULL, 2); }
static int mw_ewds(void) { uint8_t tx[2] = { 0x04, 0x00 }; return mw_frame(tx, NULL, 2); }

static int mw_write16(uint8_t addr, uint16_t val)
{
	uint8_t tx[4] = { 0x05, addr, (uint8_t)(val >> 8), (uint8_t)(val & 0xFF) };
	if (mw_frame(tx, NULL, 4) < 0) return -1;
	usleep(15000);   /* tWP is ~5-10ms; 15ms is a safe margin */
	return 0;
}

static int ch341_init(void)
{
	uint8_t cfg[] = { CMD_I2C_STREAM, (uint8_t)(CMD_I2C_STM_SET | g_speed), CMD_I2C_STM_END };
	if (usb_wr(cfg, sizeof(cfg)) < 0) return -1;
	return uio_set(PINS_CS_LOW);
}

static int open_dev(void)
{
	if (libusb_init(NULL) < 0) { fprintf(stderr, "libusb_init failed\n"); return -1; }
	dev = libusb_open_device_with_vid_pid(NULL, VID, PID);
	if (!dev) {
		fprintf(stderr, "CH341A (%04x:%04x) not found, or no permission.\n", VID, PID);
		fprintf(stderr, "Install the udev rule in work/99-ch341a.rules and replug.\n");
		return -1;
	}
	libusb_set_auto_detach_kernel_driver(dev, 1);   /* kicks spi-ch341 off the interface */
	if (libusb_claim_interface(dev, 0) < 0) {
		fprintf(stderr, "claim_interface failed - is spi-ch341 still bound?\n");
		return -1;
	}
	return ch341_init();
}

int main(int argc, char **argv)
{
	const char *cmd = argc > 1 ? argv[1] : "";
	uint16_t words[256];
	int i;
	char *av[8]; int ac = 0;

	/* --cs-low: this board inverts CS, so a LOW D0 selects the chip. */
	for (i = 0; i < argc && ac < 8; i++) {
		if (!strcmp(argv[i], "--cs-low")) { g_cs_on = PINS_CS_LOW; continue; }
		if (!strncmp(argv[i], "--speed=", 8)) { g_speed = (uint8_t)(atoi(argv[i]+8) & 3); continue; }
		if (!strncmp(argv[i], "--hold-low=", 11)) {
			int pin = atoi(argv[i] + 11);
			if (pin < 0 || pin > 5) { fprintf(stderr, "--hold-low pin must be 0..5\n"); return 1; }
			g_force_low |= (uint8_t)(1 << pin);
			continue;
		}
		av[ac++] = argv[i];
	}
	argv = av; argc = ac;
	cmd = argc > 1 ? argv[1] : "";
	if (g_cs_on == PINS_CS_LOW) fprintf(stderr, "[CS polarity inverted]\n");
	if (g_force_low) fprintf(stderr, "[holding D%d low - MCU reset]\n",
	                         g_force_low & 2 ? 1 : (g_force_low & 4 ? 2 : 0));

	if (!strcmp(cmd, "pinwalk")) {
		if (open_dev() < 0) return 1;
		pinwalk();
		return 0;
	}

	if (!strcmp(cmd, "rawdump") && argc == 3) {
		/* Raw 5-byte frames, undecoded, so the bit alignment of the data
		 * phase can be re-derived offline instead of trusted. */
		uint8_t rx[5];
		FILE *f;
		if (open_dev() < 0) return 1;
		f = fopen(argv[2], "wb");
		if (!f) { perror("fopen"); return 1; }
		for (i = 0; i < 128; i++) {
			if (mw_read_raw((uint8_t)i, rx) < 0) { fclose(f); return 1; }
			fwrite(rx, 1, 5, f);
		}
		fclose(f);
		fprintf(stderr, "wrote 128 frames x 5 bytes to %s\n", argv[2]);
		return 0;
	}

	if (!strcmp(cmd, "diag")) {
		if (open_dev() < 0) return 1;
		diag();
		return 0;
	}

	if (!strcmp(cmd, "dump") && argc == 3) {
		if (open_dev() < 0) return 1;
		for (i = 0; i < 256; i++)
			if (mw_read16((uint8_t)i, &words[i]) < 0) return 1;

		/* 93C56 x16 is 128 words with A7 unused, so the upper half must
		 * mirror the lower half. If it does not, the part is not what we
		 * think it is (or the wiring is wrong) - say so rather than
		 * silently writing a 512-byte file of half-garbage. */
		int mirrored = !memcmp(words, words + 128, 128 * sizeof(uint16_t));
		int uniform = 1;
		for (i = 1; i < 256; i++) if (words[i] != words[0]) { uniform = 0; break; }
		if (uniform) {
			fprintf(stderr, "REFUSING: every word reads 0x%04x - this is not real data.\n"
			                "Run '%s diag' to find out why.\n", words[0], argv[0]);
			return 3;
		}
		fprintf(stderr, "A7 mirror check: %s\n",
		        mirrored ? "PASS (128 words x16 = 256 bytes, as expected for 93C56)"
		                 : "FAIL - upper 128 words differ; check wiring/organization");

		FILE *f = fopen(argv[2], "wb");
		if (!f) { perror("fopen"); return 1; }
		int n = mirrored ? 128 : 256;
		for (i = 0; i < n; i++) {          /* store big-endian: D15..D8 then D7..D0 */
			fputc(words[i] >> 8, f);
			fputc(words[i] & 0xFF, f);
		}
		fclose(f);
		fprintf(stderr, "wrote %d bytes to %s\n", n * 2, argv[2]);
		return mirrored ? 0 : 2;
	}

	if (!strcmp(cmd, "write") && argc == 4 && !strcmp(argv[3], "--yes-really-write")) {
		/* Demand everything diag calls GOOD: the chip must answer when
		 * selected, read the same value twice, AND stay silent when
		 * deselected. Checking only "it answers" is not enough - a chip
		 * with a broken CS line answers too, and writing in that state
		 * corrupts it. */
		{
			uint8_t a[5], b[5], oc[5];
			int k, j, responding = 0, stable = 1, ctrl_live = 0;
			uint8_t on, offp;
			if (open_dev() < 0) return 1;
			on = g_cs_on;
			offp = (on == PINS_CS_HIGH) ? PINS_CS_LOW : PINS_CS_HIGH;
			for (k = 0; k < 4; k++) {
				g_cs_on = on;
				if (mw_read_raw((uint8_t)k, a) < 0) return 1;
				if (mw_read_raw((uint8_t)k, b) < 0) return 1;
				if (memcmp(a, b, 5)) stable = 0;
				for (j = 0; j < 5; j++)
					if (a[j] != 0x00 && a[j] != 0xFF) responding = 1;
				g_cs_on = offp;
				if (mw_read_raw((uint8_t)k, oc) < 0) return 1;
				for (j = 0; j < 5; j++)
					if (oc[j] != 0x00 && oc[j] != 0xFF) ctrl_live = 1;
			}
			g_cs_on = on;
			if (!responding || !stable || ctrl_live) {
				fprintf(stderr, "REFUSING to write: %s. Run 'diag' first.\n",
				        !responding ? "chip not responding" :
				        !stable     ? "reads are unstable" :
				                      "chip answers when deselected (CS fault)");
				return 2;
			}
		}
		FILE *f = fopen(argv[2], "rb");
		if (!f) { perror("fopen"); return 1; }
		uint8_t img[256];
		size_t n = fread(img, 1, sizeof(img), f);
		fclose(f);
		if (n != 256) { fprintf(stderr, "image must be exactly 256 bytes, got %zu\n", n); return 1; }

		if (mw_ewen() < 0) return 1;
		for (i = 0; i < 128; i++) {
			uint16_t v = (uint16_t)((img[i * 2] << 8) | img[i * 2 + 1]);
			if (mw_write16((uint8_t)i, v) < 0) { mw_ewds(); return 1; }
		}
		mw_ewds();
		fprintf(stderr, "wrote 128 words; verify with a fresh dump before refitting\n");
		return 0;
	}

	fprintf(stderr,
	        "usage:\n"
	        "  %s pinwalk\n"
	        "  (in-circuit: add --hold-low=N to hold CH341 pin DN low, e.g. MCU reset)\n"
	        "  %s rawdump <out.bin>\n"
	        "  %s diag\n"
	        "  %s dump  <out.bin>\n"
	        "  %s write <in.bin> --yes-really-write\n",
	        argv[0], argv[0], argv[0], argv[0], argv[0]);
	return 1;
}

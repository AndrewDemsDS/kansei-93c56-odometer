/*
 * ch341_pulse - square-wave generator on the CH341A's MOSI pin (D5).
 *
 * For bench-driving an instrument cluster's vehicle-speed-sensor input so the
 * odometer advances without the vehicle moving.
 *
 * The CH341's SPI engine clocks bytes out of MOSI at a fixed rate, so a
 * repeating bit pattern is a square wave: N bits high then N bits low gives
 * clock/(2N). USB scheduling puts small gaps between packets, which makes the
 * output jittery - that does not matter here. The cluster counts edges, and we
 * read the resulting distance off the LCD rather than computing it, so only
 * the total pulse count matters, never the precise frequency.
 *
 * Wiring (CH341A socket, 25-series position - the SAME holes as before):
 *      socket pin 5 (MOSI) --[ 1k ]-- cluster VSS input
 *      socket pin 4 (GND)  ---------- cluster ground   (MUST be common)
 *
 * Output swing is 5V push-pull. Keep the 1k series resistor: if you have the
 * wrong pin, or the input sits at 12V through a pull-up, that resistor is what
 * saves both the cluster's MCU and the CH341.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <signal.h>
#include <libusb-1.0/libusb.h>

#define VID 0x1a86
#define PID 0x5512
#define EP_OUT 0x02
#define EP_IN  0x82

#define CMD_I2C_STREAM  0xAA
#define CMD_I2C_STM_SET 0x60
#define CMD_I2C_STM_END 0x00
#define CMD_SPI_STREAM  0xA8

/* CH341 SPI clock for stream-speed index 0..3, in Hz (from the WCH docs). */
static const long CLK[4] = { 20000, 100000, 400000, 750000 };

static libusb_device_handle *dev;
static volatile sig_atomic_t stop;
static void on_sigint(int s) { (void)s; stop = 1; }

static uint8_t rev(uint8_t x)
{
	x = (x >> 4) | (x << 4);
	x = ((x & 0xCC) >> 2) | ((x & 0x33) << 2);
	x = ((x & 0xAA) >> 1) | ((x & 0x55) << 1);
	return x;
}

int main(int argc, char **argv)
{
	long want = argc > 1 ? atol(argv[1]) : 0;
	int speed = 0, half, i, bit = 0, n, got;
	uint8_t pkt[32], in[32];
	unsigned long long pulses = 0;

	if (want <= 0) {
		fprintf(stderr,
			"usage: %s <frequency_hz>\n\n"
			"Start around 100 Hz and work up, watching the speedometer.\n"
			"Ctrl-C to stop. Read the distance off the LCD - do not compute it.\n", argv[0]);
		return 1;
	}

	/* Pick the slowest clock that can still express this frequency, so the
	 * half-period is as many bits as possible and the shape stays clean. */
	for (i = 0; i < 4; i++) {
		if (CLK[i] / (2 * want) >= 1) { speed = i; break; }
	}
	half = (int)(CLK[speed] / (2 * want));
	if (half < 1) half = 1;
	if (half > 100000) half = 100000;   /* the bit counter carries across
	                                     * packets, so a half-period may span
	                                     * many packets - no low-end limit */
	fprintf(stderr, "clock %ld Hz, %d bits per half-period -> ~%ld Hz out\n",
		CLK[speed], half, CLK[speed] / (2 * half));

	if (libusb_init(NULL) < 0) return 1;
	dev = libusb_open_device_with_vid_pid(NULL, VID, PID);
	if (!dev) { fprintf(stderr, "CH341A not found / no permission\n"); return 1; }
	libusb_set_auto_detach_kernel_driver(dev, 1);
	if (libusb_claim_interface(dev, 0) < 0) { fprintf(stderr, "claim failed\n"); return 1; }

	{
		uint8_t cfg[] = { CMD_I2C_STREAM, (uint8_t)(CMD_I2C_STM_SET | speed), CMD_I2C_STM_END };
		libusb_bulk_transfer(dev, EP_OUT, cfg, sizeof(cfg), &got, 1000);
	}

	signal(SIGINT, on_sigint);
	fprintf(stderr, "running - Ctrl-C to stop\n");

	/* Build 31 payload bytes of alternating runs, then send it over and over. */
	while (!stop) {
		pkt[0] = CMD_SPI_STREAM;
		for (n = 1; n < 32; n++) {
			uint8_t b = 0;
			for (i = 0; i < 8; i++) {
				b = (uint8_t)((b << 1) | (bit < half));
				if (++bit >= 2 * half) { bit = 0; pulses++; }
			}
			pkt[n] = rev(b);
		}
		if (libusb_bulk_transfer(dev, EP_OUT, pkt, 32, &got, 1000) < 0) break;
		if (libusb_bulk_transfer(dev, EP_IN, in, 31, &got, 1000) < 0) break;
	}

	fprintf(stderr, "\nstopped after ~%llu pulses\n", pulses);
	libusb_release_interface(dev, 0);
	libusb_close(dev);
	return 0;
}

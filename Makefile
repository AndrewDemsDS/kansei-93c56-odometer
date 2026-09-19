CFLAGS = -Wall -O2
LDLIBS = -lusb-1.0

all: work/ch341_93cxx work/ch341_pulse

work/ch341_93cxx: work/ch341_93cxx.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

work/ch341_pulse: work/ch341_pulse.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

clean:
	rm -f work/ch341_93cxx work/ch341_pulse

.PHONY: all clean

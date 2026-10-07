import serial
import time

ser = serial.Serial(
    "/dev/ttyAMA0",
    9600,
    bytesize=8,
    parity="N",
    stopbits=1,
    timeout=0.05,
)

start = time.monotonic()

try:
    while True:
        data = ser.read(256)
        if data:
            elapsed = time.monotonic() - start
            print(
                f"+{elapsed:8.3f}s  "
                + " ".join(f"{b:02X}" for b in data),
                flush=True,
            )
finally:
    ser.close()

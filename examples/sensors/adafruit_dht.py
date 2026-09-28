#!/usr/bin/python3
# Simple DHT22 temperature and humidity reader using Adafruit CircuitPython library.
# Usage: sudo ./adafruit_dht.py [11|22] <GPIO pin number>
# Example: sudo ./adafruit_dht.py 22 4

import sys
import adafruit_dht
import board

sensor_args = {
    '11': adafruit_dht.DHT11,
    '22': adafruit_dht.DHT22,
}

# adafruit_dht takes a board pin object (board.D4), not a plain GPIO number
pin = getattr(board, f"D{sys.argv[2]}", None) if len(sys.argv) == 3 else None

if sys.argv[1:2] and sys.argv[1] in sensor_args and pin is not None:
    sensor = sensor_args[sys.argv[1]]
else:
    print('Usage: sudo ./adafruit_dht.py [11|22] <GPIO pin number>')
    print('Example: sudo ./adafruit_dht.py 22 4 - Read from a DHT22 connected to GPIO pin #4')
    sys.exit(1)

dhtDevice = sensor(pin)

try:
    humidity = dhtDevice.humidity
    temperature = dhtDevice.temperature
except RuntimeError as e:
    # DHT reads fail regularly (timing/checksum errors); just try again
    humidity = temperature = None
    print(f'Read error: {e}')
finally:
    dhtDevice.exit()

if humidity is not None and temperature is not None:
    print('Temp={0:0.1f}°C  Humidity={1:0.1f}%'.format(temperature, humidity))
else:
    print('Failed to get reading. Try again!')
    sys.exit(1)

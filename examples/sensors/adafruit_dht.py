#!/usr/bin/python3
# Simple DHT22 temperature and humidity reader using Adafruit CircuitPython library.
# Usage: sudo ./AdafruitDHT.py [11|22] <GPIO pin number>
# Example: sudo ./AdafruitDHT.py 22 4

import sys
import adafruit_dht

sensor_args = {
    '11': adafruit_dht.DHT11,
    '22': adafruit_dht.DHT22,
}

if len(sys.argv) == 3 and sys.argv[1] in sensor_args:
    sensor = sensor_args[sys.argv[1]]
    pin = int(sys.argv[2])
else:
    print('Usage: sudo ./AdafruitDHT.py [11|22] <GPIO pin number>')
    print('Example: sudo ./AdafruitDHT.py 22 4 - Read from a DHT22 connected to GPIO pin #4')
    sys.exit(1)

dhtDevice = sensor(pin)

humidity = dhtDevice.humidity
temperature = dhtDevice.temperature

if humidity is not None and temperature is not None:
    print('Temp={0:0.1f}°C  Humidity={1:0.1f}%'.format(temperature, humidity))
else:
    print('Failed to get reading. Try again!')
    sys.exit(1)

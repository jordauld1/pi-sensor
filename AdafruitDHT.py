#!/usr/bin/python3
# Copyright (c) 2014 Adafruit Industries

import sys

#import Adafruit_DHT

import time
import board
import adafruit_dht


# Parse command line parameters.
sensor_args = { '11': adafruit_dht.DHT11,
                '22': adafruit_dht.DHT22 }
                #'2302': adafruit_dht.AM2302

if len(sys.argv) == 3 and sys.argv[1] in sensor_args:
    sensor = sensor_args[sys.argv[1]]
    pin = sys.argv[2]
else:
    print('Usage: sudo ./Adafruit_DHT.py [11|22] <GPIO pin number>')
    print('Example: sudo ./Adafruit_DHT.py 22 4 - Read from an AM2302 connected to GPIO pin #4')
    sys.exit(1)

#dhtDevice = adafruit_dht.sensor(board.pin)
dhtDevice = adafruit_dht.DHT22(4)

#sensor = adafruit_dht.DHT22
#pin = 4

# Try to grab a sensor reading.  Use the read_retry method which will retry up
# to 15 times to get a sensor reading (waiting 2 seconds between each retry).

#humidity, temperature = adafruit_dht.read_retry(sensor, pin)

humidity = dhtDevice.humidity
temperature = dhtDevice.temperature

# Un-comment the line below to convert the temperature to Fahrenheit.
# temperature = temperature * 9/5.0 + 32

# Note that sometimes you won't get a reading and
# the results will be null (because Linux can't
# guarantee the timing of calls to read the sensor).
# If this happens try again!
if humidity is not None and temperature is not None:
    print('Temp={0:0.1f}*  Humidity={1:0.1f}%'.format(temperature, humidity))
else:
    print('Failed to get reading. Try again!')
    sys.exit(1)

#!/usr/bin/python3

import os
import time
import Adafruit_DHT
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = 4
FILENAME = '/home/pi/humidity.csv'

def initialize_file():
    if not os.path.exists(FILENAME) or os.stat(FILENAME).st_size == 0:
        with open(FILENAME, 'w') as f:
            f.write('Date,Time,Temperature,Humidity\r\n')

def log_sensor_data():
    humidity, temperature = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
    if humidity is not None and temperature is not None:
        logging.info("Temp: %s, Humidity: %s", temperature, humidity)
        print("Temp: %s, Humidity: %s", temperature, humidity)
        with open(FILENAME, 'a') as f:
            f.write('{0},{1},{2:0.1f},{3:0.1f}%\r\n'.format(time.strftime('%d/%m/%y'), time.strftime('%H:%M'), temperature, humidity))
    else:
        print("Failed to retrieve data from humidity sensor.")
        logging.error("Failed to retrieve data from humidity sensor")

def main():
    initialize_file()
    while True:
        log_sensor_data()
        time.sleep(15)

if __name__ == "__main__":
    main()

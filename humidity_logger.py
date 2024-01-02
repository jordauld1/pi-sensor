#!/usr/bin/python3

import os
import time
import Adafruit_DHT
import logging
import influxdb_client
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

token = os.environ.get("INFLUXDB_TOKEN")
org = "raider"
url = "http://192.168.1.10:8086"
bucket = "sensorData"

print("Token: ", token)  # Remove this line after verification

# Initialize InfluxDB Client
write_client = InfluxDBClient(url=url, token=token, org=org)
write_api = write_client.write_api(write_options=SYNCHRONOUS)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = 4
FILENAME = "/home/pi/humidity.csv"


def initialize_file():
    if not os.path.exists(FILENAME) or os.stat(FILENAME).st_size == 0:
        with open(FILENAME, "w") as f:
            f.write("Date,Time,Temperature,Humidity\r\n")


def write_to_influx(temperature, humidity):
    try:
        point = (
            Point("sensorReading")
            .tag("sensor", "DHT22")
            .tag("location", "bedroom3")
            .field("temperature", temperature)
            .field("humidity", humidity)
        )
        write_api.write(bucket=bucket, org=org, record=point)
    except Exception as e:
        logging.error("Error writing to InfluxDB: %s", e)


def log_sensor_data():
    try:
        humidity, temperature = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
        if humidity is not None and temperature is not None:
            logging.info("Temp: %s, Humidity: %s", temperature, humidity)
            with open(FILENAME, "a") as f:
                f.write(
                    "{0},{1},{2:0.1f},{3:0.1f}%\r\n".format(
                        time.strftime("%d/%m/%y"),
                        time.strftime("%H:%M"),
                        temperature,
                        humidity,
                    )
                )
            write_to_influx(temperature, humidity)
    except Exception as e:
        logging.error("Error occurred: %s", e)


def main():
    initialize_file()
    while True:
        log_sensor_data()
        time.sleep(15)


if __name__ == "__main__":
    main()

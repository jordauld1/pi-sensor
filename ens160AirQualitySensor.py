# Read air quality metrics from the PiicoDev Air Quality Sensor ENS160
# Shows three metrics: AQI, TVOC and eCO2

import math
from PiicoDev_SSD1306 import *  # import the OLED device driver
from PiicoDev_ENS160 import PiicoDev_ENS160  # import the device driver
from PiicoDev_BME280 import (
    PiicoDev_BME280,
)  # import the atmospheric sensor device driver
from PiicoDev_TMP117 import PiicoDev_TMP117  # import TMP117 device driver
from PiicoDev_Unified import sleep_ms  # a cross-platform sleep function


# Initialize sensors and display
def init_devices():
    temp_sensor = PiicoDev_TMP117()  # initialise the precision temperature sensor
    air_quality_sensor = PiicoDev_ENS160()  # Initialise the ENS160 air quality sensor
    atmospheric_sensor = PiicoDev_BME280()  # initialise the atmospheric sensor
    display = create_PiicoDev_SSD1306()      # initialise the OLED display driver
    return temp_sensor, air_quality_sensor, atmospheric_sensor, display


# Air Quality signal characteristics
# TVOC: 0 - 65,000 ppb
# eCO2: 400 - 65,000 ppm CO2 equiv.
# AQI-UBA: 1 to 5


# Read sensor data
def read_sensors(temp_sensor, air_quality_sensor, atmospheric_sensor):
    tempC, presPa, humRH = atmospheric_sensor.values()
    # atmospheric sensor temp is not super accurate, so use the TMP117 instead
    pres_hPa = presPa / 100  # Convert Pascals to hPa

    tempC_tempSensor = temp_sensor.readTempC()
    # tempF = temp_sensor.readTempF()  # Farenheit
    # tempK = temp_sensor.readTempK()  # Kelvin

    # Set Air Quality Sensor temp and humidity params (ENS160)
    air_quality_sensor.temperature = tempC_tempSensor
    air_quality_sensor.humidity = humRH

    aqi = air_quality_sensor.aqi
    tvoc = air_quality_sensor.tvoc
    eco2 = air_quality_sensor.eco2

    return {
        "tempC": tempC_tempSensor,
        "pres_hPa": pres_hPa,
        "humRH": humRH,
        "aqi": aqi.value,
        "aqi_rating": aqi.rating,
        "tvoc": tvoc,
        "eco2": eco2.value,
        "eco2_rating": eco2.rating,
        "sensor_status": air_quality_sensor.operation,
    }


# Update console
def update_console(sensor_data):
    print(
        f"Temp: {sensor_data['tempC']} °C, Press: {sensor_data['pres_hPa']} hPa, Humid: {sensor_data['humRH']} %RH"
    )
    print(
        f"AQI: {sensor_data['aqi']}, TVOC: {sensor_data['tvoc']} ppb, eCO2: {sensor_data['eco2']} ppm"
    )
    print(f"Sensor Status: {sensor_data['sensor_status']}")
    print("--------------------------------")


def update_display(display, sensor_data, page=0):
    display.fill(0)  # Clear the display

    if page == 0:
        # First page: Temperature, Humidity, Pressure
        display.text(f"Temp: {sensor_data['tempC']}C", 0, 0, 1)
        display.text(f"Humid: {sensor_data['humRH']}%", 0, 10, 1)
        display.text(f"Press: {sensor_data['pres_hPa']}hPa", 0, 20, 1)
        display.text(f"AQI: {sensor_data['aqi']}" + " [" + str(sensor_data['aqi_rating']) + "]", 0, 30, 1)
        display.text(f"TVOC: {sensor_data['tvoc']}ppb", 0, 40, 1)
        display.text(f"eCO2: {sensor_data['eco2']}ppm" + " [" + str(sensor_data['eco2_rating']) + "]", 0, 50, 1)
        

    # elif page == 1:
        # Third page: Other metrics or messages
        #display.text(f"Sensor Status: {sensor_data['sensor_status']}", 0, 0, 1)

    display.show()


# Main program loop
def main():
    temp_sensor, air_quality_sensor, atmospheric_sensor, display = init_devices()
    page = 0
    while True:
        try:
            sensor_data = read_sensors(
                temp_sensor, air_quality_sensor, atmospheric_sensor
            )
            update_console(sensor_data)
            update_display(display, sensor_data, page)
            #page = (page + 1) % 2  # Cycle through 2 pages
            sleep_ms(1000)
        except Exception as e:
            print(f"Error: {e}")

        """
        pres_hPa = presPa / 100  # convert Pascals to hPa (mbar)

        # Read and print the temperature in various units
        tempC = temp_sensor.readTempC()  # Celsius
        tempF = temp_sensor.readTempF()  # Farenheit
        tempK = temp_sensor.readTempK()  # Kelvin

        # Set Air Quality Sensor temp and humidity params
        
        air_quality_sensor.temperature = tempC  # [degC]
        air_quality_sensor.humidity = humRH  # [%RH]
				
        # Read from the sensor
        aqi = air_quality_sensor.aqi
        tvoc = air_quality_sensor.tvoc
        eco2 = air_quality_sensor.eco2

        # Print air temperature metrics
        print("   Temp: " + str(tempC) + " °C")
        print("  Press: " + str(pres_hPa) + " hPa")
        print("  Humid: " + str(humRH) + " %RH")
        # Print air quality metrics
        print("    AQI: " + str(aqi.value) + " [" + str(aqi.rating) + "]")
        print("   TVOC: " + str(tvoc) + " ppb")
        print("   eCO2: " + str(eco2.value) + " ppm [" + str(eco2.rating) + "]")
        print(" Sensor Status: " + air_quality_sensor.operation)
        print("--------------------------------")
        """


if __name__ == "__main__":
    main()

import math
import logging
import os
import signal
import sys
import time
from typing import Dict, Any, Tuple, List
from collections import deque
from datetime import datetime
from statistics import mean, median

from PiicoDev_SSD1306 import *
from PiicoDev_ENS160 import PiicoDev_ENS160
from PiicoDev_BME280 import PiicoDev_BME280
from PiicoDev_TMP117 import PiicoDev_TMP117
from PiicoDev_Unified import sleep_ms

import influxdb_client
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Configuration
CONFIG = {
    'MEASUREMENT_INTERVAL_MS': 1000,  # How often to take measurements
    'DISPLAY_PAGES': 6,              # Increased number of display pages
    'INFLUXDB': {
        'URL': "http://192.168.1.10:8086",
        'ORG': "raider",
        'BUCKET': "sensorData",
        'TOKEN_ENV_VAR': "INFLUXDB_TOKEN",
        'BATCH_SIZE': 60,            # Number of readings to batch before sending
        'SEND_INTERVAL_SEC': 60,     # Send data every minute
    },
    'SENSOR_LOCATION': "bedroom3",   # Location tag for InfluxDB
    'CACHE': {
        'MAX_SIZE': 1000,           # Maximum number of readings to cache in RAM
    },
    'HEALTH_CHECK': {
        'TEMP_RANGE': (-10, 50),     # Valid temperature range in Celsius
        'HUMID_RANGE': (0, 100),     # Valid humidity range in %
        'PRESSURE_RANGE': (900, 1100),  # Valid pressure range in hPa
        'MAX_READING_AGE_SEC': 5,    # Maximum age of readings before considered stale
        'ERROR_THRESHOLD': 3         # Number of errors before marking sensor as unhealthy
    },
    'ENS160': {
        'TVOC_RANGE': (0, 65000),      # ppb (parts per billion)
        'ECO2_RANGE': (400, 65000),    # ppm (parts per million)
        'AQI_RATINGS': {               # Based on UBA guidelines
            1: 'Excellent',
            2: 'Good',
            3: 'Moderate',
            4: 'Poor',
            5: 'Unhealthy'
        },
        'STATUS': {
            'OK': "operating ok",
            'ERROR': "error",
            'WARMUP': "warm-up",
            'STARTUP': "initial start-up",
            'INVALID': "no valid output"
        },
        'DEFAULT_VALUES': {
            'AQI': 1,
            'TVOC': 0,
            'ECO2': 400
        }
    },
    'ENVIRONMENT_RATINGS': {
        'CO2': {
            'EXCELLENT': (400, 800),
            'GOOD': (800, 1000),
            'FAIR': (1000, 1500),
            'POOR': (1500, 2000),
            'DANGEROUS': (2000, 65000)
        },
        'HUMIDITY': {
            'TOO_DRY': (0, 30),
            'GOOD': (30, 60),
            'TOO_HUMID': (60, 100)
        },
        'RECOMMENDATIONS': {
            'HIGH_CO2': 'Open windows for fresh air',
            'HIGH_HUMIDITY': 'Increase ventilation',
            'LOW_HUMIDITY': 'Consider humidifier',
            'POOR_AQI': 'Air purification recommended'
        }
    },
    'DISPLAY': {
        'PAGES': 5,           # Total number of pages (0-4)
        'PAGE_TITLES': [
            'Main Stats',      # Page 0
            'Air Quality',     # Page 1
            'Temp Graph',      # Page 2
            'Sensor Health',   # Page 3
            'Environment'      # Page 4
        ],
        'UPDATE_INTERVAL_SEC': 3  # Seconds between page changes
    },
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class SensorHealth:
    def __init__(self):
        self.error_counts = {
            'temp_sensor': 0,
            'air_quality': 0,
            'atmospheric': 0
        }
        self.last_readings = {
            'temp_sensor': None,
            'air_quality': None,
            'atmospheric': None
        }
        self.last_reading_time = {
            'temp_sensor': 0,
            'air_quality': 0,
            'atmospheric': 0
        }

    def update_sensor_time(self, sensor_name):
        self.last_reading_time[sensor_name] = time.time()

    def increment_error(self, sensor_name):
        self.error_counts[sensor_name] += 1
        logger.warning(f"{sensor_name} error count: {self.error_counts[sensor_name]}")

    def reset_error(self, sensor_name):
        if self.error_counts[sensor_name] > 0:
            self.error_counts[sensor_name] = 0
            logger.info(f"Reset error count for {sensor_name}")

    def is_sensor_healthy(self, sensor_name) -> bool:
        return self.error_counts[sensor_name] < CONFIG['HEALTH_CHECK']['ERROR_THRESHOLD']

    def is_reading_fresh(self, sensor_name) -> bool:
        age = time.time() - self.last_reading_time[sensor_name]
        return age < CONFIG['HEALTH_CHECK']['MAX_READING_AGE_SEC']

    def validate_reading(self, reading_type: str, value: float) -> bool:
        if reading_type == 'temperature':
            return CONFIG['HEALTH_CHECK']['TEMP_RANGE'][0] <= value <= CONFIG['HEALTH_CHECK']['TEMP_RANGE'][1]
        elif reading_type == 'humidity':
            return CONFIG['HEALTH_CHECK']['HUMID_RANGE'][0] <= value <= CONFIG['HEALTH_CHECK']['HUMID_RANGE'][1]
        elif reading_type == 'pressure':
            return CONFIG['HEALTH_CHECK']['PRESSURE_RANGE'][0] <= value <= CONFIG['HEALTH_CHECK']['PRESSURE_RANGE'][1]
        return True

    def validate_sensor_reading(self, sensor_type: str, value: Any) -> bool:
        if sensor_type == 'tvoc':
            return CONFIG['ENS160']['TVOC_RANGE'][0] <= value <= CONFIG['ENS160']['TVOC_RANGE'][1]
        elif sensor_type == 'eco2':
            return CONFIG['ENS160']['ECO2_RANGE'][0] <= value <= CONFIG['ENS160']['ECO2_RANGE'][1]
        elif sensor_type == 'aqi':
            return isinstance(value, int) and 1 <= value <= 5
        return True

class EnvironmentAnalyzer:
    @staticmethod
    def get_environment_score(sensor_data: Dict[str, Any]) -> Tuple[str, List[str]]:
        # Use the actual AQI rating from ENS160 as our base score
        base_score = sensor_data['aqi_rating']
        recommendations = []
        
        # Check CO2 levels using more granular thresholds
        eco2 = sensor_data['eco2']
        if eco2 > 2000:
            recommendations.append('Ventilate now!')
        elif eco2 > 1200:
            recommendations.append('Open windows')
        elif eco2 > 800:
            recommendations.append('Consider fresh air')
            
        # Check TVOC levels with more granular thresholds
        tvoc = sensor_data['tvoc']
        if tvoc > 10000:
            recommendations.append('Air purify now!')
        elif tvoc > 2000:
            recommendations.append('Ventilate space')
        elif tvoc > 500:
            recommendations.append('Check VOC sources')
            
        # More sensitive humidity recommendations
        humidity = sensor_data['humRH']
        if humidity < 30:
            recommendations.append('Too dry: humidify')
        elif humidity < 40:
            recommendations.append('Slightly dry')
        elif humidity > 70:
            recommendations.append('Very humid: dehumidify')
        elif humidity > 60:
            recommendations.append('Getting humid')
            
        # Temperature comfort recommendations
        temp = sensor_data['tempC']
        if temp > 26:
            recommendations.append('Space too warm')
        elif temp < 17:
            recommendations.append('Space too cool')
            
        # Add AQI-based recommendations
        if sensor_data['aqi'] >= 4:
            recommendations.append('Poor air: purify!')
            
        return base_score, list(set(recommendations))[:2]  # Return up to 2 unique recommendations

    @staticmethod
    def get_comfort_status(sensor_data: Dict[str, Any]) -> str:
        """Get overall comfort status when no immediate actions needed"""
        if (18 <= sensor_data['tempC'] <= 25 and 
            30 <= sensor_data['humRH'] <= 60 and 
            sensor_data['eco2'] < 800 and 
            sensor_data['tvoc'] < 500 and 
            sensor_data['aqi'] <= 2):
            return "All parameters OK"
        return "Monitor values"

class SensorManager:
    def __init__(self):
        self.temp_sensor = None
        self.air_quality_sensor = None
        self.atmospheric_sensor = None
        self.display = None
        self.influx_client = None
        self.write_api = None
        self.running = True
        self.data_cache = deque(maxlen=CONFIG['CACHE']['MAX_SIZE'])
        self.last_influx_send = 0
        self.health = SensorHealth()
        self.error_history = []
        self.reading_history = deque(maxlen=128)  # Match display width for graphing
        self.temp_graph = None  # Will be initialized when display is ready
        self.environment_analyzer = EnvironmentAnalyzer()
        self.current_page = 0

    def init_influxdb(self):
        token = os.environ.get(CONFIG['INFLUXDB']['TOKEN_ENV_VAR'])
        if not token:
            raise ValueError(f"Missing {CONFIG['INFLUXDB']['TOKEN_ENV_VAR']} environment variable")
        
        self.influx_client = InfluxDBClient(
            url=CONFIG['INFLUXDB']['URL'],
            token=token,
            org=CONFIG['INFLUXDB']['ORG']
        )
        self.write_api = self.influx_client.write_api(write_options=SYNCHRONOUS)
        logger.info("InfluxDB client initialized successfully")

    def init_devices(self):
        try:
            # Initialize sensors
            self.temp_sensor = PiicoDev_TMP117()
            self.air_quality_sensor = PiicoDev_ENS160()
            self.atmospheric_sensor = PiicoDev_BME280()
            self.display = create_PiicoDev_SSD1306()
            # Initialize the temperature graph with appropriate min/max values
            self.temp_graph = self.display.graph2D(
                minValue=15,  # Typical indoor minimum temperature
                maxValue=30,  # Typical indoor maximum temperature
                height=35     # Leave space for labels
            )
            
            # Show initialization message
            self.display.fill(0)
            self.display.text("Initializing", 0, 0, 1)
            self.display.text("sensors...", 0, 10, 1)
            self.display.show()
            sleep_ms(1000)
            
            logger.info("All sensors initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize devices: {e}")
            raise

    def cleanup(self):
        logger.info("Cleaning up resources...")
        if self.display:
            try:
                self.display.fill(0)
                self.display.text("Shutting down", 0, 20, 1)
                self.display.text("Please wait...", 0, 35, 1)
                self.display.show()
                sleep_ms(1000)  # Show message briefly
                self.display.fill(0)
                self.display.show()
            except Exception as e:
                logger.error(f"Error during display cleanup: {e}")

        if self.influx_client:
            try:
                logger.info("Saving final data to InfluxDB...")
                self.flush_cache()
                self.influx_client.close()
            except Exception as e:
                logger.error(f"Error during InfluxDB cleanup: {e}")

        self.running = False
        logger.info("Cleanup completed")

    def validate_data_point(self, data: Dict[str, Any]) -> bool:
        """Validate sensor data against documented ranges before sending to InfluxDB"""
        try:
            # First check operational status
            if data['sensor_status'] != CONFIG['ENS160']['STATUS']['OK']:
                logger.warning(f"ENS160 not ready: {data['sensor_status']}")
                return False
                
            # Temperature validation
            if not CONFIG['HEALTH_CHECK']['TEMP_RANGE'][0] <= data['tempC'] <= CONFIG['HEALTH_CHECK']['TEMP_RANGE'][1]:
                return False
                
            # ENS160 validations based on documentation
            if not (CONFIG['ENS160']['TVOC_RANGE'][0] <= data['tvoc'] <= CONFIG['ENS160']['TVOC_RANGE'][1]):
                return False
                
            if not (CONFIG['ENS160']['ECO2_RANGE'][0] <= data['eco2'] <= CONFIG['ENS160']['ECO2_RANGE'][1]):
                return False
                
            # AQI must be 1-5 per ENS160 docs
            if not (1 <= data['aqi'] <= len(CONFIG['ENS160']['AQI_RATINGS'])):
                return False
                
            # Basic range checks for atmospheric data
            if not (0 <= data['humRH'] <= 100):
                return False
                
            if not (CONFIG['HEALTH_CHECK']['PRESSURE_RANGE'][0] <= data['pres_hPa'] <= CONFIG['HEALTH_CHECK']['PRESSURE_RANGE'][1]):
                return False
                
            return True
        except (KeyError, TypeError):
            return False

    def write_to_influx(self, sensor_data: Dict[str, Any]):
        """Add data to cache and potentially send to InfluxDB"""
        if self.validate_data_point(sensor_data):
            self.data_cache.append(sensor_data)
            
            current_time = time.time()
            if (current_time - self.last_influx_send >= CONFIG['INFLUXDB']['SEND_INTERVAL_SEC'] and 
                len(self.data_cache) >= CONFIG['INFLUXDB']['BATCH_SIZE']):
                self.flush_cache()
        else:
            logger.warning("Invalid sensor data point detected, skipping InfluxDB storage")

    def flush_cache(self):
        """Attempt to send all cached data to InfluxDB"""
        if not self.data_cache:
            return

        try:
            points = []
            for data in self.data_cache:
                point = (
                    Point("sensorReading")
                    .tag("sensor", "PiicoDevSensors")
                    .tag("location", CONFIG['SENSOR_LOCATION'])
                    .field("temperature", data['tempC'])
                    .field("humidity", data['humRH'])
                    .field("pressure", data['pres_hPa'])
                    .field("aqi", data['aqi'])
                    .field("tvoc", data['tvoc'])
                    .field("eco2", data['eco2'])
                    .field("aqi_rating", data['aqi_rating'])
                    .field("eco2_rating", data['eco2_rating'])
                    .field("sensor_status", data['sensor_status'])
                )
                points.append(point)

            self.write_api.write(
                bucket=CONFIG['INFLUXDB']['BUCKET'],
                org=CONFIG['INFLUXDB']['ORG'],
                record=points
            )
            
            self.data_cache.clear()
            self.last_influx_send = time.time()
            logger.info(f"Successfully sent {len(points)} readings to InfluxDB")
        except Exception as e:
            logger.error(f"Error writing to InfluxDB: {e}")
            # Data remains in cache for next attempt

    def read_sensors(self) -> Dict[str, Any]:
        try:
            tempC, presPa, humRH = self.atmospheric_sensor.values()
            self.health.update_sensor_time('atmospheric')
            
            if not all(self.health.validate_reading(t, v) for t, v in [
                ('temperature', tempC),
                ('humidity', humRH),
                ('pressure', presPa/100)
            ]):
                self.health.increment_error('atmospheric')
            else:
                self.health.reset_error('atmospheric')
        except Exception as e:
            self.health.increment_error('atmospheric')
            logger.error(f"Atmospheric sensor error: {e}")
            tempC, presPa, humRH = self.health.last_readings.get('atmospheric', (20, 101325, 50))

        try:
            tempC_tempSensor = self.temp_sensor.readTempC()
            self.health.update_sensor_time('temp_sensor')
            
            if not self.health.validate_reading('temperature', tempC_tempSensor):
                self.health.increment_error('temp_sensor')
            else:
                self.health.reset_error('temp_sensor')
        except Exception as e:
            self.health.increment_error('temp_sensor')
            logger.error(f"Temperature sensor error: {e}")
            tempC_tempSensor = tempC

        # Initialize air quality variables with defaults
        aqi = type('obj', (), {'value': CONFIG['ENS160']['DEFAULT_VALUES']['AQI'], 
                              'rating': CONFIG['ENS160']['AQI_RATINGS'][CONFIG['ENS160']['DEFAULT_VALUES']['AQI']]})()
        tvoc = CONFIG['ENS160']['DEFAULT_VALUES']['TVOC']
        eco2 = type('obj', (), {'value': CONFIG['ENS160']['DEFAULT_VALUES']['ECO2'], 
                               'rating': 'Normal'})()
        sensor_status = CONFIG['ENS160']['STATUS']['ERROR']

        try:
            # Update ENS160 with current temperature and humidity for compensation
            self.air_quality_sensor.temperature = tempC_tempSensor
            self.air_quality_sensor.humidity = humRH
            
            # Check operational status
            sensor_status = self.air_quality_sensor.operation
            if sensor_status != CONFIG['ENS160']['STATUS']['OK']:
                logger.info(f"ENS160 not ready: {sensor_status}")
                raise ValueError(f"ENS160 not operating correctly: {sensor_status}")
            
            aqi = self.air_quality_sensor.aqi
            tvoc = self.air_quality_sensor.tvoc
            eco2 = self.air_quality_sensor.eco2
            
            # Validate readings against documented ranges
            if not all(self.health.validate_sensor_reading(t, v) for t, v in [
                ('tvoc', tvoc),
                ('eco2', eco2.value),
                ('aqi', aqi.value)
            ]):
                self.health.increment_error('air_quality')
            else:
                self.health.reset_error('air_quality')
                
            self.health.update_sensor_time('air_quality')
        except Exception as e:
            self.health.increment_error('air_quality')
            logger.error(f"Air quality sensor error: {e}")
            if self.health.last_readings.get('air_quality'):
                aqi, tvoc, eco2 = self.health.last_readings['air_quality']

        reading = {
            "tempC": tempC_tempSensor,
            "pres_hPa": presPa / 100,
            "humRH": humRH,
            "aqi": aqi.value,
            "aqi_rating": CONFIG['ENS160']['AQI_RATINGS'].get(aqi.value, 'Unknown'),
            "tvoc": tvoc,
            "eco2": eco2.value,
            "eco2_rating": eco2.rating,
            "sensor_status": sensor_status,
            "timestamp": time.time()
        }

        # Store reading history if sensor is operating correctly
        if sensor_status == CONFIG['ENS160']['STATUS']['OK']:
            self.reading_history.append(reading)
            self.health.last_readings['atmospheric'] = (tempC, presPa, humRH)
            self.health.last_readings['temp_sensor'] = tempC_tempSensor
            self.health.last_readings['air_quality'] = (aqi, tvoc, eco2)

        return reading

    def update_graph(self, temperature: float):
        """Update temperature graph"""
        try:
            # Scale temperature by 10 to get better resolution
            temp_val = int(temperature * 10)
            if self.temp_graph is not None:
                self.display.updateGraph2D(self.temp_graph, temp_val)
        except Exception as e:
            logger.error(f"Error updating temperature graph: {e}")

    def get_sensor_health_status(self):
        status = []
        for sensor in ['temp_sensor', 'air_quality', 'atmospheric']:
            healthy = self.health.is_sensor_healthy(sensor)
            fresh = self.health.is_reading_fresh(sensor)
            status.append({
                'name': sensor,
                'healthy': healthy,
                'fresh': fresh,
                'errors': self.health.error_counts[sensor]
            })
        return status

    def update_console(self, sensor_data):
        print(
            f"Temp: {sensor_data['tempC']} °C, Press: {sensor_data['pres_hPa']} hPa, Humid: {sensor_data['humRH']} %RH"
        )
        print(
            f"AQI: {sensor_data['aqi']}, TVOC: {sensor_data['tvoc']} ppb, eCO2: {sensor_data['eco2']} ppm"
        )
        print(f"Sensor Status: {sensor_data['sensor_status']}")
        print("--------------------------------")

    def reset_display(self):
        """Reset display and graph if errors occur"""
        try:
            self.display.fill(0)
            self.display.show()
            sleep_ms(100)  # Brief pause to ensure display is cleared
            logger.info("Display reset successfully")
        except Exception as e:
            logger.error(f"Critical display error: {e}")

    def update_display(self, display, sensor_data, page=0):
        try:
            display.fill(0)
            
            if page == 0:
                # Main readings page (no changes)
                display.text(CONFIG['DISPLAY']['PAGE_TITLES'][page], 0, 0, 1)
                display.text(f"Temp: {sensor_data['tempC']:.1f}C", 0, 12, 1)
                display.text(f"Humid: {sensor_data['humRH']:.1f}%", 0, 22, 1)
                display.text(f"Press: {sensor_data['pres_hPa']:.1f}", 0, 32, 1)
                
                if sensor_data['sensor_status'] != CONFIG['ENS160']['STATUS']['OK']:
                    display.text("Status:", 0, 42, 1)
                    status_text = sensor_data['sensor_status'][:16]
                    display.text(status_text, 0, 52, 1)
                else:
                    display.text("Air Quality:", 0, 42, 1)
                    rating_text = sensor_data['aqi_rating'][:16]
                    display.text(rating_text, 0, 52, 1)

            elif page == 1:
                # Air quality details
                display.text(CONFIG['DISPLAY']['PAGE_TITLES'][page], 0, 0, 1)
                if sensor_data['sensor_status'] == CONFIG['ENS160']['STATUS']['OK']:
                    display.text(f"AQI: {sensor_data['aqi']}/5", 0, 15, 1)
                    display.text(f"TVOC:{sensor_data['tvoc']}ppb", 0, 25, 1)
                    eco2_val = sensor_data['eco2']
                    if eco2_val > 9999:
                        display.text(f"CO2:{eco2_val//1000}k", 0, 35, 1)
                    else:
                        display.text(f"CO2:{eco2_val}ppm", 0, 35, 1)
                else:
                    display.text("Sensor not ready", 0, 25, 1)
                    status_text = sensor_data['sensor_status'][:16]
                    display.text(status_text, 0, 35, 1)

            elif page == 2:
                # Temperature history graph
                display.text(CONFIG['DISPLAY']['PAGE_TITLES'][page], 0, 0, 1)
                temp = sensor_data['tempC']
                display.text(f"{temp:.1f}C", 90, 0, 1)
                
                # Update and draw the temperature graph
                if self.temp_graph is not None:
                    display.updateGraph2D(self.temp_graph, temp)
                    
                # Show min/max from reading history
                if self.reading_history:
                    temp_values = [r['tempC'] for r in self.reading_history]
                    min_temp = min(temp_values)
                    max_temp = max(temp_values)
                    display.text(f"L:{min_temp:.1f}", 0, 55, 1)
                    display.text(f"H:{max_temp:.1f}", 64, 55, 1)

            elif page == 3:
                # Only show health status page if there are issues
                health_status = self.get_sensor_health_status()
                all_healthy = all(status['healthy'] and status['fresh'] and status['errors'] == 0 
                                for status in health_status)
                if not all_healthy:
                    display.text(CONFIG['DISPLAY']['PAGE_TITLES'][page], 0, 0, 1)
                    y = 15
                    for status in health_status:
                        if not (status['healthy'] and status['fresh'] and status['errors'] == 0):
                            icon = "+" if status['healthy'] and status['fresh'] else "x"
                            name = status['name'][:12]
                            display.text(f"{icon} {name}", 0, y, 1)
                            if status['errors'] > 0:
                                display.text(f"Err:{status['errors']}", 70, y, 1)
                            y += 12

            elif page == 4:
                # Environment recommendations with more detailed triggers
                display.text(CONFIG['DISPLAY']['PAGE_TITLES'][page], 0, 0, 1)
                env_score, recommendations = self.environment_analyzer.get_environment_score(sensor_data)
                
                score_text = f"Level: {env_score}"[:16]
                display.text(score_text, 0, 15, 1)
                
                # Always show at least basic status even if no recommendations
                if not recommendations:
                    if sensor_data['sensor_status'] == CONFIG['ENS160']['STATUS']['OK']:
                        if sensor_data['aqi'] == 1:
                            display.text("Air quality ideal", 0, 27, 1)
                        elif sensor_data['aqi'] == 2:
                            display.text("Air quality good", 0, 27, 1)
                            display.text("Continue ventilation", 0, 39, 1)
                    else:
                        display.text("Sensor warming up", 0, 27, 1)
                else:
                    y = 27
                    for rec in recommendations[:2]:
                        # Split long recommendations
                        if len(rec) > 16:
                            display.text(rec[:16], 0, y, 1)
                            if len(rec) > 16:
                                display.text(rec[16:32], 0, y + 10, 1)
                                y += 20
                        else:
                            display.text(rec, 0, y, 1)
                            y += 12

            display.show()
            
        except Exception as e:
            logger.error(f"Display update error on page {page}: {e}")
            try:
                display.fill(0)
                display.show()
            except:
                pass

    def run(self):
        page_update_time = time.time()
        startup_message_shown = False
        
        while self.running:
            try:
                current_time = time.time()
                sensor_data = self.read_sensors()
                self.update_console(sensor_data)
                
                # Show startup message on first successful reading
                if not startup_message_shown and sensor_data['sensor_status'] == CONFIG['ENS160']['STATUS']['OK']:
                    self.display.fill(0)
                    self.display.text("Sensors ready", 0, 20, 1)
                    self.display.text("Starting...", 0, 35, 1)
                    self.display.show()
                    sleep_ms(1000)
                    startup_message_shown = True
                
                # Update display with error handling
                try:
                    health_status = self.get_sensor_health_status()
                    all_healthy = all(status['healthy'] and status['fresh'] and status['errors'] == 0 
                                    for status in health_status)
                    
                    if current_time - page_update_time >= CONFIG['DISPLAY']['UPDATE_INTERVAL_SEC']:
                        next_page = (self.current_page + 1) % CONFIG['DISPLAY']['PAGES']
                        if all_healthy and next_page == 3:
                            next_page = 4  # Skip health page if all healthy
                        self.current_page = next_page
                        page_update_time = current_time
                    
                    self.update_display(self.display, sensor_data, self.current_page)
                    
                except Exception as e:
                    logger.error(f"Display error: {e}")
                    self.current_page = 0
                    self.reset_display()
                
                self.write_to_influx(sensor_data)
                sleep_ms(CONFIG['MEASUREMENT_INTERVAL_MS'])
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                sleep_ms(5000)  # Wait before retrying

def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}")
    if sensor_manager:
        sensor_manager.cleanup()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    sensor_manager = None
    try:
        sensor_manager = SensorManager()
        sensor_manager.init_influxdb()
        sensor_manager.init_devices()
        logger.info("Starting sensor monitoring...")
        sensor_manager.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if sensor_manager:
            sensor_manager.cleanup()
        sys.exit(1)

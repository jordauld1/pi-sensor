import json
import logging
import os
import signal
import sys
import textwrap
import time
from typing import Dict, Any, Tuple, List
from collections import deque
from statistics import mean

import PiicoDev_SSD1306 as ssd1306_driver
from PiicoDev_SSD1306 import create_PiicoDev_SSD1306, WIDTH, HEIGHT
from PiicoDev_ENS160 import PiicoDev_ENS160
from PiicoDev_BME280 import PiicoDev_BME280
from PiicoDev_TMP117 import PiicoDev_TMP117
from PiicoDev_Buzzer import PiicoDev_Buzzer
from PiicoDev_Unified import sleep_ms

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Configuration
CONFIG = {
    'MEASUREMENT_INTERVAL_MS': 1000,  # How often to take measurements
    'INFLUXDB': {
        'URL': "http://192.168.1.10:8086",
        'ORG': "raider",
        'BUCKET': "sensorData",
        'TOKEN_ENV_VAR': "INFLUXDB_TOKEN",
        'POINT_INTERVAL_SEC': 60,    # Average readings into one stored point per interval
        'SEND_INTERVAL_SEC': 300,    # Upload queued points (or retry) once per interval
        'TIMEOUT_MS': 5000,          # HTTP timeout; a write blocks the main loop
    },
    'SENSOR_LOCATION': "bedroom3",   # Location tag for InfluxDB
    'LATEST_READING_PATH': "",       # If set, each averaged point is also written here as JSON
    'CACHE': {
        'MAX_SIZE': 1440,           # Points kept in RAM while InfluxDB is unreachable (~24 hours)
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
    'DISPLAY': {
        'PAGES': 5,           # Total number of pages (0-4)
        'PAGE_TITLES': [
            'Main Stats',      # Page 0
            'Air Quality',     # Page 1
            'Temp Graph',      # Page 2
            'Sensor Health',   # Page 3
            'Environment'      # Page 4
        ],
        'UPDATE_INTERVAL_SEC': 3,  # Seconds between page changes
        'GRAPH_SAMPLE_INTERVAL_SEC': 60,  # One graph point per minute -> ~2 hours across the screen
    },
    'CO2_ALARM': {
        'ENABLED': False,         # Opt in per room: CO2_ALARM_ENABLED=1
        'TRIGGER_PPM': 1500,      # Alarm when eCO2 is ABOVE this; same as ENVIRONMENT_RATINGS ECO2_ABOVE_PPM top band
        'CLEAR_PPM': 1000,        # Clear when eCO2 is at or below this; must be below TRIGGER_PPM
        'SUSTAIN_SEC': 120,       # eCO2 must stay above TRIGGER_PPM this long before alarming
        'MAX_GAP_SEC': 30,        # A longer gap without usable readings restarts the sustain timer
        'REPEAT_SEC': 600,        # Beep again this often while still high
        'QUIET_HOURS': (22, 7),   # Local hours [start, end) with no sound (banner only); None = never quiet
        'TONE_HZ': 2000,
        'TONE_MS': 150,
        'BEEPS': 3,
        'VOLUME': 1,              # PiicoDev buzzer volume: 0, 1 or 2
    },
    'ENVIRONMENT_RATINGS': {
        # Sources and reasoning: docs/air-quality-guide.md. Keep the guide in sync with this table.
        # Each rule is (threshold, severity, message); the first matching rule per list applies.
        # Severity: 3 act now, 2 act soon, 1 advisory. Messages word-wrap at 16 characters per line.
        'ECO2_ABOVE_PPM': [            # ENS160 datasheet Table 5 (Poor/Bad bands; same as eco2_rating())
            (1500, 3, 'Ventilate now!'),
            (1000, 2, 'Open a window'),
            (800, 1, 'Get fresh air'),
        ],
        'AQI_AT_LEAST': [              # ENS160 AQI-UBA level (TVOC-based, UBA 2007 guidance)
            (5, 3, 'VOCs high: air out'),
            (4, 2, 'Ventilate: VOCs'),
            (3, 1, 'Find VOC source'),
        ],
        'HUMIDITY_BELOW': [(30, 2, 'Too dry: humidify')],      # US EPA: ideally 30-50 %RH
        'HUMIDITY_ABOVE': [(60, 2, 'Too humid: dehumidify')],  # US EPA: keep below 60 %RH
        'TEMP_BELOW': [(18, 1, 'Too cold')],                   # WHO Housing and Health Guidelines 2018
        'TEMP_ABOVE': [(26, 1, 'Too warm')],                   # ASHRAE 55 summer comfort upper bound
    },
}

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "font-pet-me-128.dat")
CHARS_PER_LINE = WIDTH // 8

# Configure logging (set LOG_LEVEL=DEBUG to print every reading)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def on_off(raw: str) -> bool:
    """Parse 1/0, true/false, yes/no, on/off."""
    value = raw.strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    raise ValueError(raw)


def quiet_hours(raw: str):
    """Parse 'START-END' local hours (e.g. '22-7'), or 'off' for no quiet hours."""
    if raw.strip().lower() in ('off', 'none'):
        return None
    start, end = (int(part) for part in raw.split('-'))
    if not (0 <= start <= 23 and 0 <= end <= 23):
        raise ValueError(raw)
    return (start, end)


# Environment variables that override CONFIG, so one copy of this script can run in any room.
# name -> (path of keys into CONFIG, function converting the string value)
ENV_OVERRIDES = {
    'SENSOR_LOCATION': (('SENSOR_LOCATION',), str),
    'LATEST_READING_PATH': (('LATEST_READING_PATH',), str),
    'INFLUXDB_URL': (('INFLUXDB', 'URL'), str),
    'INFLUXDB_ORG': (('INFLUXDB', 'ORG'), str),
    'INFLUXDB_BUCKET': (('INFLUXDB', 'BUCKET'), str),
    'CO2_ALARM_ENABLED': (('CO2_ALARM', 'ENABLED'), on_off),
    'CO2_ALARM_TRIGGER_PPM': (('CO2_ALARM', 'TRIGGER_PPM'), int),
    'CO2_ALARM_CLEAR_PPM': (('CO2_ALARM', 'CLEAR_PPM'), int),
    'CO2_ALARM_SUSTAIN_SEC': (('CO2_ALARM', 'SUSTAIN_SEC'), int),
    'CO2_ALARM_QUIET_HOURS': (('CO2_ALARM', 'QUIET_HOURS'), quiet_hours),
}


def apply_env_overrides(config: Dict[str, Any], environ) -> List[str]:
    """Apply ENV_OVERRIDES found in environ to config, in place. Returns the names applied.

    Empty values are ignored. Raises ValueError if a value can't be converted."""
    applied = []
    for name, (path, convert) in ENV_OVERRIDES.items():
        raw = environ.get(name, '').strip()
        if not raw:
            continue
        try:
            value = convert(raw)
        except ValueError:
            raise ValueError(f"Environment variable {name} has an invalid value")
        target = config
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        applied.append(name)
    return applied


def patch_display_driver():
    """Speed up the PiicoDev SSD1306 driver on Linux.

    The stock driver sends three I2C commands for every pixel it sets and
    re-reads the font file (relative to the current directory) on every text()
    call, even though show() pushes the whole framebuffer anyway. Draw into the
    buffer only and load the font once, from next to this script.
    """
    if getattr(ssd1306_driver, '_SYSNAME', None) != 'Linux':
        return

    with open(FONT_PATH, 'rb') as f:
        font = f.read()

    def pixel(self, x, y, color):
        x = x & (WIDTH - 1)
        y = y & (HEIGHT - 1)
        page, shift_page = divmod(y, 8)
        ind = x + page * WIDTH
        if color:
            self.buffer[ind] |= 1 << shift_page
        else:
            self.buffer[ind] &= ~(1 << shift_page)

    def fill(self, c=0):
        self.buffer[:] = (b'\xff' if c > 0 else b'\x00') * len(self.buffer)

    def text(self, text, x, y, c=1):
        for text_index, char in enumerate(text):
            base = (ord(char) - 32) * 8
            if base < 0 or base + 8 > len(font):
                continue  # Character not in the font
            for col in range(8):
                x_coordinate = x + col + text_index * 8
                if x_coordinate >= WIDTH:
                    break
                bits = font[base + col]
                for i in range(7):
                    if bits & (1 << i) and y + i < HEIGHT:
                        pixel(self, x_coordinate, y + i, c)

    ssd1306_driver.PiicoDev_SSD1306.pixel = pixel
    ssd1306_driver.PiicoDev_SSD1306.fill = fill
    ssd1306_driver.PiicoDev_SSD1306.text = text


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
    # (CONFIG['ENVIRONMENT_RATINGS'] key, reading key, comparison) in tie-break order
    RULES = (
        ('ECO2_ABOVE_PPM', 'eco2', lambda value, threshold: value > threshold),
        ('AQI_AT_LEAST', 'aqi', lambda value, threshold: value >= threshold),
        ('HUMIDITY_BELOW', 'humRH', lambda value, threshold: value < threshold),
        ('HUMIDITY_ABOVE', 'humRH', lambda value, threshold: value > threshold),
        ('TEMP_BELOW', 'tempC', lambda value, threshold: value < threshold),
        ('TEMP_ABOVE', 'tempC', lambda value, threshold: value > threshold),
    )

    @staticmethod
    def get_environment_score(sensor_data: Dict[str, Any]) -> Tuple[str, List[str]]:
        """Return the ENS160 AQI rating and up to 2 recommendations, most severe first."""
        candidates = []  # (severity, message) in RULES order
        for config_key, reading_key, matches in EnvironmentAnalyzer.RULES:
            for threshold, severity, message in CONFIG['ENVIRONMENT_RATINGS'][config_key]:
                if matches(sensor_data[reading_key], threshold):
                    candidates.append((severity, message))
                    break  # only the first (strongest) matching rule per list

        # sorted() is stable, so equal severities keep RULES order
        recommendations = [message for _, message in sorted(candidates, key=lambda c: -c[0])]
        return sensor_data['aqi_rating'], recommendations[:2]

class Co2Alarm:
    """Decides when to sound the CO2 alarm. Pure logic: the caller does the beeping."""

    def __init__(self, settings: Dict[str, Any]):
        # Only validate when enabled, so a bad pair in a room with the alarm off can't stop startup
        if settings['ENABLED'] and settings['CLEAR_PPM'] >= settings['TRIGGER_PPM']:
            raise ValueError("CO2_ALARM CLEAR_PPM must be below TRIGGER_PPM")
        self.settings = settings
        self.active = False
        self.high_since = None    # when eCO2 first went above TRIGGER_PPM in this episode
        self.last_sounded = None
        self.last_usable = None   # time of the last reading we could trust

    def in_quiet_hours(self, local_hour: int) -> bool:
        hours = self.settings['QUIET_HOURS']
        if hours is None:
            return False
        start, end = hours
        if start <= end:
            return start <= local_hour < end
        return local_hour >= start or local_hour < end   # wraps past midnight

    def update(self, reading: Dict[str, Any], now: float, local_hour: int) -> bool:
        """Feed one reading. Returns True when the buzzer should sound now."""
        if reading['sensor_status'] != CONFIG['ENS160']['STATUS']['OK']:
            return False  # warm-up or failed read: don't trigger, clear or reset timers
        if self.last_usable is not None and now - self.last_usable > self.settings['MAX_GAP_SEC']:
            self.high_since = None  # too long without trustworthy data to call the level "sustained"
        self.last_usable = now

        eco2 = reading['eco2']
        if self.active:
            if eco2 <= self.settings['CLEAR_PPM']:
                logger.info(f"CO2 alarm cleared (eCO2 {eco2} ppm)")
                self.active = False
                self.high_since = None
                self.last_sounded = None
                return False
        elif eco2 > self.settings['TRIGGER_PPM']:
            if self.high_since is None:
                self.high_since = now
            if now - self.high_since >= self.settings['SUSTAIN_SEC']:
                logger.warning(f"CO2 alarm: eCO2 {eco2} ppm for {now - self.high_since:.0f}s")
                self.active = True
        else:
            self.high_since = None

        if not self.active or self.in_quiet_hours(local_hour):
            return False
        if self.last_sounded is None or now - self.last_sounded >= self.settings['REPEAT_SEC']:
            self.last_sounded = now
            return True
        return False


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
        self.point_window = []  # Valid readings waiting to be averaged into a point
        self.point_window_start = time.time()
        self.last_influx_send = 0
        self.health = SensorHealth()
        self.temp_history = deque(maxlen=WIDTH)  # One point per pixel column
        self.last_graph_sample = 0
        self.last_ens160_status = None
        self.environment_analyzer = EnvironmentAnalyzer()
        self.current_page = 0
        self.buzzer = None
        self.co2_alarm = Co2Alarm(CONFIG['CO2_ALARM'])

    def init_influxdb(self):
        token = os.environ.get(CONFIG['INFLUXDB']['TOKEN_ENV_VAR'])
        if not token:
            raise ValueError(f"Missing {CONFIG['INFLUXDB']['TOKEN_ENV_VAR']} environment variable")

        self.influx_client = InfluxDBClient(
            url=CONFIG['INFLUXDB']['URL'],
            token=token,
            org=CONFIG['INFLUXDB']['ORG'],
            timeout=CONFIG['INFLUXDB']['TIMEOUT_MS']
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

            # Show initialization message
            self.display.fill(0)
            self.display.text("Initializing", 0, 0, 1)
            self.display.text("sensors...", 0, 10, 1)
            self.display.show()
            sleep_ms(1000)

            self.init_buzzer()
            logger.info("All sensors initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize devices: {e}")
            raise

    def init_buzzer(self):
        """Connect the buzzer if the CO2 alarm is enabled. A missing buzzer is not fatal."""
        if not CONFIG['CO2_ALARM']['ENABLED']:
            return
        try:
            self.buzzer = PiicoDev_Buzzer(volume=CONFIG['CO2_ALARM']['VOLUME'])
            self.buzzer.pwrLED(False)  # no glowing LED in a bedroom
            logger.info("CO2 alarm enabled with buzzer")
        except Exception as e:
            self.buzzer = None
            logger.warning(f"CO2 alarm enabled but buzzer not available, banner only: {e}")

    def check_co2_alarm(self, sensor_data: Dict[str, Any], now: float, local_hour: int):
        """Update CO2 alarm state and beep when it's due."""
        if not CONFIG['CO2_ALARM']['ENABLED']:
            return
        if self.co2_alarm.update(sensor_data, now, local_hour) and self.buzzer is not None:
            settings = CONFIG['CO2_ALARM']
            for _ in range(settings['BEEPS']):
                if self.buzzer.tone(settings['TONE_HZ'], settings['TONE_MS']) != 0:
                    logger.warning("Buzzer did not respond")
                    break
                sleep_ms(settings['TONE_MS'] * 2)

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
                self.close_point_window()
                self.flush_cache()
                self.influx_client.close()
            except Exception as e:
                logger.error(f"Error during InfluxDB cleanup: {e}")

        self.running = False
        logger.info("Cleanup completed")

    def validate_data_point(self, data: Dict[str, Any]) -> bool:
        """Validate sensor data against documented ranges before sending to InfluxDB"""
        try:
            # ENS160 warm-up is expected and logged on status change, so skip quietly
            if data['sensor_status'] != CONFIG['ENS160']['STATUS']['OK']:
                return False

            # Atmospheric values are substituted from the last good reading on
            # failure; those are fine for the display but must not be stored
            if not data['atmospheric_ok']:
                return False

            # Same for temperature: the BME280 fallback reads warm, so only store TMP117 values
            if not data['temp_ok']:
                return False

            checks = [
                ('temperature', data['tempC'], CONFIG['HEALTH_CHECK']['TEMP_RANGE']),
                ('humidity', data['humRH'], CONFIG['HEALTH_CHECK']['HUMID_RANGE']),
                ('pressure', data['pres_hPa'], CONFIG['HEALTH_CHECK']['PRESSURE_RANGE']),
                # ENS160 validations based on documentation
                ('tvoc', data['tvoc'], CONFIG['ENS160']['TVOC_RANGE']),
                ('eco2', data['eco2'], CONFIG['ENS160']['ECO2_RANGE']),
                # AQI must be 1-5 per ENS160 docs
                ('aqi', data['aqi'], (1, len(CONFIG['ENS160']['AQI_RATINGS']))),
            ]
            for name, value, (low, high) in checks:
                if not low <= value <= high:
                    logger.warning(f"Skipping InfluxDB storage: {name}={value} outside {low}-{high}")
                    return False

            return True
        except (KeyError, TypeError) as e:
            logger.warning(f"Skipping InfluxDB storage: malformed reading ({e})")
            return False

    def write_to_influx(self, sensor_data: Dict[str, Any]):
        """Collect valid readings, average them into one point per interval, and
        upload the queued points in a single request per send interval"""
        if self.validate_data_point(sensor_data):
            self.point_window.append(sensor_data)

        current_time = time.time()
        if current_time - self.point_window_start >= CONFIG['INFLUXDB']['POINT_INTERVAL_SEC']:
            self.close_point_window()

        if (self.data_cache and
            current_time - self.last_influx_send >= CONFIG['INFLUXDB']['SEND_INTERVAL_SEC']):
            self.flush_cache()

    def close_point_window(self):
        """Average the readings collected this interval into one queued point"""
        readings = self.point_window
        self.point_window = []
        self.point_window_start = time.time()
        if not readings:
            return

        # aqi/tvoc/eco2 are stored as integers; keep them that way so the
        # field types match existing data
        aqi = round(mean(r['aqi'] for r in readings))
        eco2 = round(mean(r['eco2'] for r in readings))
        self.data_cache.append({
            "tempC": mean(r['tempC'] for r in readings),
            "pres_hPa": mean(r['pres_hPa'] for r in readings),
            "humRH": mean(r['humRH'] for r in readings),
            "aqi": aqi,
            "aqi_rating": CONFIG['ENS160']['AQI_RATINGS'].get(aqi, 'Unknown'),
            "tvoc": round(mean(r['tvoc'] for r in readings)),
            "eco2": eco2,
            "eco2_rating": self.eco2_rating(eco2),
            "sensor_status": readings[-1]['sensor_status'],
            "timestamp_ms": readings[-1]['timestamp_ms'],
        })
        self.write_latest_reading(self.data_cache[-1])

    @staticmethod
    def write_latest_reading(point: Dict[str, Any]):
        """Write the latest averaged point to LATEST_READING_PATH for other programs
        on this Pi (e.g. room_control.py in actron-local). Does nothing if unset."""
        path = CONFIG['LATEST_READING_PATH']
        if not path:
            return
        tmp = path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump({
                    "location": CONFIG['SENSOR_LOCATION'],
                    "time": time.time(),
                    "tempC": round(point['tempC'], 2),
                    "humRH": round(point['humRH'], 1),
                    "eco2": point['eco2'],
                }, f)
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        except OSError as e:
            logger.warning(f"Couldn't write latest reading to {path}: {e}")

    @staticmethod
    def eco2_rating(eco2: int) -> str:
        """Same thresholds the PiicoDev_ENS160 driver uses for eco2.rating"""
        if eco2 < 400:
            return 'invalid'
        for threshold, rating in ((1500, 'bad'), (1000, 'poor'), (800, 'fair'), (600, 'good')):
            if eco2 > threshold:
                return rating
        return 'excellent'

    def flush_cache(self):
        """Attempt to send all cached data to InfluxDB"""
        if not self.data_cache:
            return

        # Count failed attempts too, so an unreachable server is retried once per
        # interval instead of on every reading (each attempt blocks for the timeout)
        self.last_influx_send = time.time()

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
                    # Without an explicit time every point in the batch gets the
                    # server's receive time and they overwrite each other
                    .time(data['timestamp_ms'], WritePrecision.MS)
                )
                points.append(point)

            self.write_api.write(
                bucket=CONFIG['INFLUXDB']['BUCKET'],
                org=CONFIG['INFLUXDB']['ORG'],
                record=points
            )

            self.data_cache.clear()
            logger.info(f"Successfully sent {len(points)} points to InfluxDB")
        except Exception as e:
            logger.error(f"Error writing to InfluxDB ({len(self.data_cache)} points kept for retry): {e}")

    def log_ens160_status(self, sensor_status: str):
        if sensor_status != self.last_ens160_status:
            logger.info(f"ENS160 status: {sensor_status}")
            self.last_ens160_status = sensor_status

    def read_sensors(self) -> Dict[str, Any]:
        atmospheric_ok = False
        try:
            tempC, presPa, humRH = self.atmospheric_sensor.values()
            self.health.update_sensor_time('atmospheric')
            atmospheric_ok = True
            self.health.last_readings['atmospheric'] = (tempC, presPa, humRH)

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
            tempC, presPa, humRH = self.health.last_readings['atmospheric'] or (20, 101325, 50)

        temp_sensor_ok = False
        try:
            tempC_tempSensor = self.temp_sensor.readTempC()
            self.health.update_sensor_time('temp_sensor')
            temp_sensor_ok = True
            self.health.last_readings['temp_sensor'] = tempC_tempSensor

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

            # Check operational status. Warm-up after power-on is normal, not a fault.
            sensor_status = self.air_quality_sensor.operation
            self.log_ens160_status(sensor_status)
            self.health.update_sensor_time('air_quality')

            if sensor_status == CONFIG['ENS160']['STATUS']['OK']:
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

                self.health.last_readings['air_quality'] = (aqi, tvoc, eco2)
        except Exception as e:
            # Don't let a status read before the failure mark this reading as good
            sensor_status = CONFIG['ENS160']['STATUS']['ERROR']
            self.health.increment_error('air_quality')
            logger.error(f"Air quality sensor error: {e}")
            if self.health.last_readings['air_quality']:
                aqi, tvoc, eco2 = self.health.last_readings['air_quality']

        return {
            "tempC": tempC_tempSensor,
            "pres_hPa": presPa / 100,
            "humRH": humRH,
            "aqi": aqi.value,
            "aqi_rating": CONFIG['ENS160']['AQI_RATINGS'].get(aqi.value, 'Unknown'),
            "tvoc": tvoc,
            "eco2": eco2.value,
            "eco2_rating": eco2.rating,
            "sensor_status": sensor_status,
            "atmospheric_ok": atmospheric_ok,
            "temp_ok": temp_sensor_ok,  # False when tempC is the BME280 fallback
            "timestamp_ms": time.time_ns() // 1_000_000
        }

    def sample_temp_history(self, sensor_data: Dict[str, Any], current_time: float):
        """Record temperature for the graph on every page, not just while it is shown"""
        if not sensor_data['temp_ok']:
            return
        if current_time - self.last_graph_sample >= CONFIG['DISPLAY']['GRAPH_SAMPLE_INTERVAL_SEC']:
            self.temp_history.append(sensor_data['tempC'])
            self.last_graph_sample = current_time

    def draw_temp_graph(self, display, top: int, bottom: int):
        """Plot sampled temperature history, newest on the right, auto-scaled"""
        values = list(self.temp_history)
        if not values:
            return

        low, high = min(values), max(values)
        # Keep at least 1C of span so sensor noise doesn't fill the whole height
        if high - low < 1.0:
            mid = (high + low) / 2
            low, high = mid - 0.5, mid + 0.5
        scale = (bottom - top) / (high - low)

        x = WIDTH - len(values)
        prev_y = None
        for value in values:
            y = bottom - round((value - low) * scale)
            if prev_y is None:
                display.pixel(x, y, 1)
            else:
                display.line(x - 1, prev_y, x, y, 1)
            prev_y = y
            x += 1

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
        # Debug level: at one reading per second this would otherwise flood the journal
        logger.debug(
            f"Temp: {sensor_data['tempC']:.2f} °C, Press: {sensor_data['pres_hPa']:.1f} hPa, "
            f"Humid: {sensor_data['humRH']:.1f} %RH, AQI: {sensor_data['aqi']}, "
            f"TVOC: {sensor_data['tvoc']} ppb, eCO2: {sensor_data['eco2']} ppm, "
            f"Status: {sensor_data['sensor_status']}"
        )

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
                    status_text = sensor_data['sensor_status'][:CHARS_PER_LINE]
                    display.text(status_text, 0, 52, 1)
                else:
                    display.text("Air Quality:", 0, 42, 1)
                    rating_text = sensor_data['aqi_rating'][:CHARS_PER_LINE]
                    display.text(rating_text, 0, 52, 1)

            elif page == 1:
                # Air quality details
                display.text(CONFIG['DISPLAY']['PAGE_TITLES'][page], 0, 0, 1)
                if sensor_data['sensor_status'] == CONFIG['ENS160']['STATUS']['OK']:
                    display.text(f"AQI: {sensor_data['aqi']}/5", 0, 15, 1)
                    display.text(f"TVOC:{sensor_data['tvoc']}ppb", 0, 25, 1)
                    eco2_val = sensor_data['eco2']
                    if eco2_val > 9999:
                        display.text(f"eCO2:{eco2_val//1000}k", 0, 35, 1)
                    else:
                        display.text(f"eCO2:{eco2_val}ppm", 0, 35, 1)
                else:
                    display.text("Sensor not ready", 0, 25, 1)
                    status_text = sensor_data['sensor_status'][:CHARS_PER_LINE]
                    display.text(status_text, 0, 35, 1)

            elif page == 2:
                # Temperature history graph
                display.text(CONFIG['DISPLAY']['PAGE_TITLES'][page], 0, 0, 1)
                temp_text = f"{sensor_data['tempC']:.1f}C"
                display.text(temp_text, WIDTH - len(temp_text) * 8, 0, 1)

                if self.temp_history:
                    self.draw_temp_graph(display, top=12, bottom=52)
                    display.text(f"L:{min(self.temp_history):.1f}", 0, 56, 1)
                    display.text(f"H:{max(self.temp_history):.1f}", 64, 56, 1)
                else:
                    display.text("Collecting...", 0, 30, 1)

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

                score_text = f"Level: {env_score}"[:CHARS_PER_LINE]
                display.text(score_text, 0, 14, 1)

                # Always show at least basic status even if no recommendations
                if not recommendations:
                    if sensor_data['sensor_status'] != CONFIG['ENS160']['STATUS']['OK']:
                        messages = ["Sensor warm-up"]
                    elif sensor_data['aqi'] == 1:
                        messages = ["Excellent air"]
                    elif sensor_data['aqi'] == 2:
                        messages = ["Air quality good", "Keep ventilating"]
                    else:
                        messages = [sensor_data['aqi_rating']]
                else:
                    messages = recommendations

                y = 26
                for message in messages:
                    # Word-wrap to the 16 character display width
                    for line in textwrap.wrap(message, CHARS_PER_LINE)[:2]:
                        display.text(line, 0, y, 1)
                        y += 9
                    y += 2

            if self.co2_alarm.active:
                # Banner over the title row on every page while the alarm is active
                display.fill_rect(0, 0, WIDTH - 1, 9, 1)
                display.text("! CO2 HIGH !", 16, 1, 0)
            display.show()

        except Exception as e:
            logger.error(f"Display update error on page {page}: {e}")
            try:
                display.fill(0)
                display.show()
            except Exception:
                pass

    def run(self):
        page_update_time = time.time()
        startup_message_shown = False

        while self.running:
            try:
                current_time = time.time()
                sensor_data = self.read_sensors()
                self.update_console(sensor_data)
                self.sample_temp_history(sensor_data, current_time)
                self.check_co2_alarm(sensor_data, current_time, time.localtime(current_time).tm_hour)

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

                # Sleep for the rest of the interval so readings stay evenly spaced
                elapsed_ms = int((time.time() - current_time) * 1000)
                sleep_ms(max(0, CONFIG['MEASUREMENT_INTERVAL_MS'] - elapsed_ms))
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                sleep_ms(5000)  # Wait before retrying

def main():
    try:
        applied = apply_env_overrides(CONFIG, os.environ)
    except ValueError as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    logger.info(f"Config overrides from environment: {', '.join(applied) or 'none'}")
    logger.info(f"Location: {CONFIG['SENSOR_LOCATION']}, InfluxDB: {CONFIG['INFLUXDB']['URL']}")
    sensor_manager = SensorManager()

    def signal_handler(signum, frame):
        # Only stop the loop here; cleanup runs once the current iteration
        # finishes, rather than interrupting it mid-write
        logger.info(f"Received signal {signum}, shutting down")
        sensor_manager.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    exit_code = 0
    try:
        patch_display_driver()
        sensor_manager.init_influxdb()
        sensor_manager.init_devices()
        logger.info("Starting sensor monitoring...")
        sensor_manager.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        exit_code = 1
    finally:
        sensor_manager.cleanup()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()

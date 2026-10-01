import sys
import types

import pytest

# The app imports PiicoDev hardware drivers when it loads. They only work on a
# Raspberry Pi with the sensors attached, so register stand-ins first.


class _Unavailable:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("PiicoDev driver stub: hardware is not available in tests")


def _stub_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


_stub_module("PiicoDev_SSD1306", create_PiicoDev_SSD1306=_Unavailable, WIDTH=128, HEIGHT=64)
_stub_module("PiicoDev_ENS160", PiicoDev_ENS160=_Unavailable)
_stub_module("PiicoDev_BME280", PiicoDev_BME280=_Unavailable)
_stub_module("PiicoDev_TMP117", PiicoDev_TMP117=_Unavailable)
_stub_module("PiicoDev_Buzzer", PiicoDev_Buzzer=_Unavailable)
_stub_module("PiicoDev_Unified", sleep_ms=lambda ms: None)

import ens160AirQualitySensor as app  # noqa: E402

from fakes import (FakeBME280, FakeClock, FakeDisplay, FakeENS160,  # noqa: E402
                   FakeTMP117, FakeWriteApi)


@pytest.fixture
def clock(monkeypatch):
    """Controls time.time()/time.time_ns() inside the app module."""
    c = FakeClock()
    monkeypatch.setattr(app, "time", c)
    return c


@pytest.fixture
def manager(clock):
    """A SensorManager wired to fakes, created at clock.now with no upload done yet."""
    m = app.SensorManager()
    m.atmospheric_sensor = FakeBME280()
    m.temp_sensor = FakeTMP117()
    m.air_quality_sensor = FakeENS160()
    m.display = FakeDisplay()
    m.write_api = FakeWriteApi()
    return m


@pytest.fixture
def good_reading():
    """Factory for a reading dict shaped like SensorManager.read_sensors() output."""
    def make(**overrides):
        reading = {
            "tempC": 21.0,
            "pres_hPa": 1013.25,
            "humRH": 45.0,
            "aqi": 2,
            "aqi_rating": "Good",
            "tvoc": 120,
            "eco2": 650,
            "eco2_rating": "good",
            "sensor_status": "operating ok",
            "atmospheric_ok": True,
            "temp_ok": True,
            "timestamp_ms": 1_700_000_000_000,
        }
        reading.update(overrides)
        return reading
    return make

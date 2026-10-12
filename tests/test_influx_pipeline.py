import json

import pytest

import ens160AirQualitySensor as app
from fakes import FakeInfluxClient


def test_no_point_before_window_ends(manager, good_reading, clock):
    for t in range(60):
        clock.now = 10_000 + t
        manager.write_to_influx(good_reading())
    assert len(manager.data_cache) == 0
    assert manager.write_api.attempts == 0
    assert len(manager.point_window) == 60


def test_window_is_averaged(manager, good_reading, clock):
    manager.last_influx_send = clock.now
    manager.write_to_influx(good_reading(tempC=20.0, eco2=600, tvoc=100, timestamp_ms=1))
    clock.now += 30
    manager.write_to_influx(good_reading(tempC=22.0, eco2=700, tvoc=200, timestamp_ms=2))
    clock.now += 30
    manager.write_to_influx(good_reading(sensor_status="warm-up"))
    assert len(manager.data_cache) == 1
    point = manager.data_cache[0]
    assert point["tempC"] == 21.0
    assert point["eco2"] == 650
    assert point["tvoc"] == 150
    assert point["aqi"] == 2
    assert point["aqi_rating"] == "Good"
    assert point["eco2_rating"] == "good"
    assert point["timestamp_ms"] == 2
    assert point["sensor_status"] == "operating ok"
    assert type(point["eco2"]) is int


@pytest.mark.parametrize("value,rating", [
    (399, "invalid"), (400, "excellent"), (600, "excellent"),
    (601, "good"), (801, "fair"), (1001, "poor"), (1501, "bad"),
])
def test_eco2_rating_thresholds(value, rating):
    assert app.SensorManager.eco2_rating(value) == rating


def test_upload_every_send_interval(manager, good_reading, clock):
    manager.last_influx_send = clock.now
    manager.data_cache.extend(good_reading() for _ in range(3))
    clock.now = 10_299
    manager.write_to_influx(good_reading(sensor_status="warm-up"))
    assert manager.write_api.attempts == 0
    clock.now = 10_300
    manager.write_to_influx(good_reading(sensor_status="warm-up"))
    assert manager.write_api.attempts == 1
    assert len(manager.write_api.writes) == 1
    write = manager.write_api.writes[0]
    assert len(write["record"]) == 3
    assert write["bucket"] == "sensorData"
    assert write["org"] == "raider"
    assert len(manager.data_cache) == 0


def test_point_line_protocol(manager, good_reading):
    manager.data_cache.append(good_reading(timestamp_ms=1_700_000_000_123))
    manager.flush_cache()
    line = manager.write_api.writes[0]["record"][0].to_line_protocol()
    assert line.startswith("sensorReading,")
    assert "location=bedroom3" in line
    assert "sensor=PiicoDevSensors" in line
    for field in ("temperature", "humidity", "pressure", "aqi", "tvoc", "eco2",
                  "aqi_rating", "eco2_rating", "sensor_status"):
        assert f"{field}=" in line
    assert line.endswith(" 1700000000123")


def test_failed_upload_waits_full_interval(manager, good_reading, clock):
    manager.write_api.error = RuntimeError("down")
    manager.data_cache.append(good_reading())
    manager.last_influx_send = clock.now
    clock.now = 10_300
    manager.write_to_influx(good_reading(sensor_status="warm-up"))
    assert manager.write_api.attempts == 1
    assert len(manager.data_cache) == 1
    for t in range(301, 600):
        clock.now = 10_000 + t
        manager.write_to_influx(good_reading(sensor_status="warm-up"))
        assert manager.write_api.attempts == 1
    clock.now = 10_600
    manager.write_to_influx(good_reading(sensor_status="warm-up"))
    assert manager.write_api.attempts == 2


def test_cleanup_saves_partial_window(manager, good_reading, clock):
    manager.influx_client = FakeInfluxClient()
    manager.display = None
    manager.point_window = [good_reading()]
    manager.last_influx_send = clock.now
    manager.cleanup()
    assert manager.write_api.attempts == 1
    assert len(manager.write_api.writes[0]["record"]) == 1
    assert manager.influx_client.closed is True
    assert manager.running is False


def test_cache_holds_24h_of_points(manager):
    assert manager.data_cache.maxlen == 1440


def test_latest_reading_file_written(manager, good_reading, clock, monkeypatch, tmp_path):
    path = tmp_path / "latest.json"
    monkeypatch.setitem(app.CONFIG, "LATEST_READING_PATH", str(path))
    manager.write_to_influx(good_reading(tempC=20.0))
    clock.now += 30
    manager.write_to_influx(good_reading(tempC=22.0))
    clock.now += 30
    manager.write_to_influx(good_reading())
    data = json.loads(path.read_text())
    assert data["tempC"] == 21.0
    assert data["location"] == app.CONFIG["SENSOR_LOCATION"]
    assert data["time"] == clock.now
    assert not (tmp_path / "latest.json.tmp").exists()


def test_latest_reading_file_off_by_default(manager, good_reading, clock, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manager.last_influx_send = clock.now
    manager.write_to_influx(good_reading())
    clock.now += 60
    manager.write_to_influx(good_reading())
    assert len(manager.data_cache) == 1
    assert list(tmp_path.iterdir()) == []

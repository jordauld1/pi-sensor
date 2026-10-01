import logging


def test_happy_path(manager):
    reading = manager.read_sensors()
    assert reading == {
        "tempC": 21.0, "pres_hPa": 1013.25, "humRH": 45.0,
        "aqi": 2, "aqi_rating": "Good", "tvoc": 120,
        "eco2": 650, "eco2_rating": "good", "sensor_status": "operating ok",
        "atmospheric_ok": True, "temp_ok": True, "timestamp_ms": 10_000_000,
    }
    assert reading["atmospheric_ok"] is True
    assert reading["temp_ok"] is True
    assert manager.air_quality_sensor.temperature == 21.0
    assert manager.air_quality_sensor.humidity == 45.0


def test_warmup_defaults(manager):
    manager.air_quality_sensor.operation = "warm-up"
    reading = manager.read_sensors()
    assert reading["sensor_status"] == "warm-up"
    assert reading["aqi"] == 1
    assert reading["tvoc"] == 0
    assert reading["eco2"] == 400
    assert manager.health.error_counts["air_quality"] == 0


def test_warmup_logged_once(manager, caplog):
    manager.air_quality_sensor.operation = "warm-up"
    with caplog.at_level(logging.INFO):
        manager.read_sensors()
        manager.read_sensors()
    assert sum(record.getMessage() == "ENS160 status: warm-up" for record in caplog.records) == 1


def test_bme_failure_before_good_read(manager):
    manager.atmospheric_sensor.error = OSError("i2c")
    reading = manager.read_sensors()
    assert reading["atmospheric_ok"] is False
    assert reading["pres_hPa"] == 1013.25
    assert reading["humRH"] == 50
    assert reading["temp_ok"] is True


def test_bme_failure_reuses_last_read(manager):
    manager.read_sensors()
    manager.atmospheric_sensor.error = OSError("i2c")
    reading = manager.read_sensors()
    assert reading["humRH"] == 45.0
    assert reading["atmospheric_ok"] is False


def test_tmp_failure_falls_back_to_bme(manager):
    manager.temp_sensor.error = OSError()
    reading = manager.read_sensors()
    assert reading["tempC"] == 21.5
    assert reading["temp_ok"] is True


def test_ens_failure_reuses_last_read(manager):
    manager.read_sensors()
    manager.air_quality_sensor.error = OSError()
    reading = manager.read_sensors()
    assert reading["sensor_status"] == "error"
    assert reading["eco2"] == 650
    assert manager.health.error_counts["air_quality"] == 1

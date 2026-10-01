import ens160AirQualitySensor as app


def test_new_sensor_healthy():
    assert app.SensorHealth().is_sensor_healthy("atmospheric") is True


def test_error_threshold_and_reset():
    health = app.SensorHealth()
    for _ in range(3):
        health.increment_error("atmospheric")
    assert health.is_sensor_healthy("atmospheric") is False
    health.reset_error("atmospheric")
    assert health.is_sensor_healthy("atmospheric") is True
    assert health.error_counts["atmospheric"] == 0


def test_environmental_reading_ranges():
    health = app.SensorHealth()
    assert health.validate_reading("temperature", 51) is False
    assert health.validate_reading("humidity", 50) is True
    assert health.validate_reading("pressure", 899) is False


def test_air_quality_reading_ranges():
    health = app.SensorHealth()
    assert health.validate_sensor_reading("aqi", 3) is True
    assert health.validate_sensor_reading("aqi", 3.0) is False
    assert health.validate_sensor_reading("eco2", 399) is False

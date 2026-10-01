import copy

import pytest

import ens160AirQualitySensor as app


def test_no_env_leaves_defaults():
    cfg = copy.deepcopy(app.CONFIG)
    assert app.apply_env_overrides(cfg, {}) == []
    assert cfg == app.CONFIG


def test_overrides_applied():
    cfg = copy.deepcopy(app.CONFIG)
    environ = {
        "SENSOR_LOCATION": "kitchen",
        "INFLUXDB_URL": "http://example.test:8086",
        "INFLUXDB_ORG": "o",
        "INFLUXDB_BUCKET": "b",
    }
    applied = app.apply_env_overrides(cfg, environ)
    assert cfg["SENSOR_LOCATION"] == "kitchen"
    assert cfg["INFLUXDB"]["URL"] == "http://example.test:8086"
    assert cfg["INFLUXDB"]["ORG"] == "o"
    assert cfg["INFLUXDB"]["BUCKET"] == "b"
    assert applied == list(environ)
    assert cfg["INFLUXDB"]["SEND_INTERVAL_SEC"] == 300


def test_blank_values_ignored():
    cfg = copy.deepcopy(app.CONFIG)
    assert app.apply_env_overrides(cfg, {"SENSOR_LOCATION": "   "}) == []
    assert cfg["SENSOR_LOCATION"] == app.CONFIG["SENSOR_LOCATION"]


def test_bad_value_raises_without_echoing_it(monkeypatch):
    cfg = copy.deepcopy(app.CONFIG)
    monkeypatch.setitem(app.ENV_OVERRIDES, "TEST_INT", (("MEASUREMENT_INTERVAL_MS",), int))
    with pytest.raises(ValueError) as excinfo:
        app.apply_env_overrides(cfg, {"TEST_INT": "fast"})
    assert "fast" not in str(excinfo.value)


def test_upload_uses_overridden_location(monkeypatch, manager, good_reading):
    monkeypatch.setitem(app.CONFIG, "SENSOR_LOCATION", "kitchen")
    manager.data_cache.append(good_reading())
    manager.flush_cache()
    assert "location=kitchen" in manager.write_api.writes[0]["record"][0].to_line_protocol()

import textwrap

import pytest

import ens160AirQualitySensor as app


def test_good_environment(good_reading):
    assert app.EnvironmentAnalyzer.get_environment_score(good_reading()) == ("Good", [])


def test_most_severe_first(good_reading):
    _, recommendations = app.EnvironmentAnalyzer.get_environment_score(
        good_reading(eco2=2500, humRH=20.0, tempC=16.0))
    assert recommendations == ["Ventilate now!", "Too dry: humidify"]


@pytest.mark.parametrize("eco2, expected", [
    (800, []),
    (801, ["Get fresh air"]),
    (1000, ["Get fresh air"]),
    (1001, ["Open a window"]),
    (1500, ["Open a window"]),
    (1501, ["Ventilate now!"]),
])
def test_eco2_bands(good_reading, eco2, expected):
    _, recommendations = app.EnvironmentAnalyzer.get_environment_score(good_reading(eco2=eco2))
    assert recommendations == expected


@pytest.mark.parametrize("eco2, rating", [(801, "fair"), (1001, "poor"), (1501, "bad")])
def test_eco2_bands_match_eco2_rating(eco2, rating):
    assert app.SensorManager.eco2_rating(eco2) == rating


@pytest.mark.parametrize("aqi, expected", [
    (1, []),
    (2, []),
    (3, ["Find VOC source"]),
    (4, ["Ventilate: VOCs"]),
    (5, ["VOCs high: air out"]),
])
def test_aqi_levels(good_reading, aqi, expected):
    rating = app.CONFIG['ENS160']['AQI_RATINGS'][aqi]
    score, recommendations = app.EnvironmentAnalyzer.get_environment_score(
        good_reading(aqi=aqi, aqi_rating=rating))
    assert score == rating
    assert recommendations == expected


def test_tvoc_alone_no_longer_recommends(good_reading):
    _, recommendations = app.EnvironmentAnalyzer.get_environment_score(good_reading(tvoc=3000))
    assert recommendations == []


@pytest.mark.parametrize("humidity, expected", [
    (29.9, ["Too dry: humidify"]),
    (30.0, []),
    (45.0, []),
    (60.0, []),
    (60.1, ["Too humid: dehumidify"]),
])
def test_humidity_bounds(good_reading, humidity, expected):
    _, recommendations = app.EnvironmentAnalyzer.get_environment_score(good_reading(humRH=humidity))
    assert recommendations == expected


@pytest.mark.parametrize("temperature, expected", [
    (17.9, ["Too cold"]),
    (18.0, []),
    (26.0, []),
    (26.1, ["Too warm"]),
])
def test_temperature_bounds(good_reading, temperature, expected):
    _, recommendations = app.EnvironmentAnalyzer.get_environment_score(good_reading(tempC=temperature))
    assert recommendations == expected


def test_urgent_aqi_not_hidden(good_reading):
    _, recommendations = app.EnvironmentAnalyzer.get_environment_score(
        good_reading(aqi=4, aqi_rating="Poor", eco2=900, tempC=27.0))
    assert recommendations == ["Ventilate: VOCs", "Get fresh air"]


def test_messages_are_ascii_and_wrap_to_two_lines():
    for rules in app.CONFIG['ENVIRONMENT_RATINGS'].values():
        for _, _, message in rules:
            assert message.isascii()
            assert len(textwrap.wrap(message, 16)) <= 2

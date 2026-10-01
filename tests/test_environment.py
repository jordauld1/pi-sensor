import ens160AirQualitySensor as app


def test_good_environment(good_reading):
    assert app.EnvironmentAnalyzer.get_environment_score(good_reading()) == ("Good", [])


def test_recommendation_order(good_reading):
    _, recommendations = app.EnvironmentAnalyzer.get_environment_score(
        good_reading(eco2=2500, tvoc=600, humRH=20.0))
    assert recommendations == ["Ventilate now!", "Check VOC sources"]


def test_comfort_status(good_reading):
    assert app.EnvironmentAnalyzer.get_comfort_status(good_reading()) == "All parameters OK"
    assert app.EnvironmentAnalyzer.get_comfort_status(good_reading(aqi=3)) == "Monitor values"

import copy

import pytest

import ens160AirQualitySensor as app
from fakes import FakeBuzzer


@pytest.fixture
def settings():
    return dict(app.CONFIG['CO2_ALARM'], ENABLED=True, QUIET_HOURS=None)


@pytest.fixture
def alarm(settings):
    return app.Co2Alarm(settings)


def sustain(alarm, good_reading, local_hour=12):
    results = [alarm.update(good_reading(eco2=2500), now, local_hour)
               for now in range(0, 121, 10)]
    return results


def test_at_trigger_never_sounds(alarm, good_reading):
    for now in range(0, 1801, 10):
        assert not alarm.update(good_reading(eco2=1500), now, 12)
    assert not alarm.active


def test_short_spike_does_not_trigger(alarm, good_reading):
    for now in range(0, 111, 10):
        assert not alarm.update(good_reading(eco2=2500), now, 12)
    assert not alarm.active


def test_sustained_high_triggers_once(alarm, good_reading):
    assert sustain(alarm, good_reading) == [False] * 12 + [True]
    assert alarm.active


def test_repeats_after_repeat_interval(alarm, good_reading):
    assert sustain(alarm, good_reading)[-1]
    for now in range(130, 711, 10):
        assert not alarm.update(good_reading(eco2=2500), now, 12)
    assert alarm.update(good_reading(eco2=2500), 720, 12)


def test_hysteresis(alarm, good_reading):
    sustain(alarm, good_reading)
    assert not alarm.update(good_reading(eco2=1200), 130, 12)
    assert alarm.active


def test_clears_and_restarts_sustain(alarm, good_reading):
    sustain(alarm, good_reading)
    assert not alarm.update(good_reading(eco2=1000), 130, 12)
    assert not alarm.active
    assert alarm.high_since is None
    assert alarm.last_sounded is None
    for now in range(140, 251, 10):
        assert not alarm.update(good_reading(eco2=2500), now, 12)
    assert not alarm.active


def test_dip_before_trigger_resets_timer(alarm, good_reading):
    for now in range(0, 101, 10):
        assert not alarm.update(good_reading(eco2=2500), now, 12)
    assert not alarm.update(good_reading(eco2=1400), 110, 12)
    for now in range(120, 231, 10):
        assert not alarm.update(good_reading(eco2=2500), now, 12)
    assert alarm.update(good_reading(eco2=2500), 240, 12)


def test_unusable_readings_ignored(alarm, good_reading):
    assert not alarm.update(good_reading(eco2=2500), 0, 12)
    for status in ('warm-up', 'error'):
        assert not alarm.update(good_reading(eco2=400, sensor_status=status), 10, 12)
        assert alarm.high_since == 0
        assert alarm.last_usable == 0
    for now in range(20, 121, 10):
        alarm.update(good_reading(eco2=2500), now, 12)
    assert alarm.active
    assert not alarm.update(good_reading(eco2=400, sensor_status='error'), 130, 12)
    assert alarm.active


def test_long_gap_restarts_sustain(alarm, good_reading):
    for now in range(0, 61, 10):
        assert not alarm.update(good_reading(eco2=2500), now, 12)
    for now in range(70, 651, 10):
        assert not alarm.update(good_reading(eco2=2500, sensor_status='warm-up'), now, 12)
    for now in range(660, 771, 10):
        assert not alarm.update(good_reading(eco2=2500), now, 12)
    assert alarm.update(good_reading(eco2=2500), 780, 12)


def test_quiet_hours(settings, good_reading):
    alarm = app.Co2Alarm(dict(settings, QUIET_HOURS=(22, 7)))
    assert alarm.in_quiet_hours(22)
    assert alarm.in_quiet_hours(3)
    assert not alarm.in_quiet_hours(7)
    assert not alarm.in_quiet_hours(12)
    daytime = app.Co2Alarm(dict(settings, QUIET_HOURS=(1, 5)))
    assert daytime.in_quiet_hours(1)
    assert not daytime.in_quiet_hours(5)
    assert sustain(alarm, good_reading, local_hour=23) == [False] * 13
    assert alarm.active
    assert alarm.update(good_reading(eco2=2500), 130, 7)


def test_clear_must_be_below_trigger(settings):
    with pytest.raises(ValueError):
        app.Co2Alarm(dict(settings, CLEAR_PPM=1500))
    app.Co2Alarm(dict(settings, ENABLED=False, CLEAR_PPM=1500))


def test_trigger_matches_display_band():
    assert app.CONFIG['CO2_ALARM']['TRIGGER_PPM'] == app.CONFIG['ENVIRONMENT_RATINGS']['ECO2_ABOVE_PPM'][0][0]


def test_check_co2_alarm_beeps(monkeypatch, manager, good_reading):
    monkeypatch.setitem(app.CONFIG['CO2_ALARM'], 'ENABLED', True)
    manager.buzzer = FakeBuzzer()
    manager.co2_alarm = app.Co2Alarm(dict(app.CONFIG['CO2_ALARM'], QUIET_HOURS=None, SUSTAIN_SEC=0))
    manager.check_co2_alarm(good_reading(eco2=2500), 0, 12)
    assert manager.buzzer.tones == [(2000, 300)] * 3


def test_buzzer_failure_stops_pattern(monkeypatch, manager, good_reading):
    monkeypatch.setitem(app.CONFIG['CO2_ALARM'], 'ENABLED', True)
    manager.buzzer = FakeBuzzer()
    manager.buzzer.result = 1
    manager.co2_alarm = app.Co2Alarm(dict(app.CONFIG['CO2_ALARM'], QUIET_HOURS=None, SUSTAIN_SEC=0))
    manager.check_co2_alarm(good_reading(eco2=2500), 0, 12)
    assert manager.buzzer.tones == [(2000, 300)]


def test_disabled_does_nothing(manager, good_reading):
    assert app.CONFIG['CO2_ALARM']['ENABLED'] is False
    manager.buzzer = FakeBuzzer()
    manager.check_co2_alarm(good_reading(eco2=5000), 0, 12)
    assert manager.buzzer.tones == []
    assert not manager.co2_alarm.active


def test_init_buzzer(monkeypatch, manager):
    monkeypatch.setitem(app.CONFIG['CO2_ALARM'], 'ENABLED', True)
    monkeypatch.setattr(app, 'PiicoDev_Buzzer', FakeBuzzer)
    manager.init_buzzer()
    assert manager.buzzer.led is False
    assert manager.buzzer.volume == 1

    def unavailable(**kwargs):
        raise OSError('No buzzer')

    monkeypatch.setattr(app, 'PiicoDev_Buzzer', unavailable)
    manager.init_buzzer()
    assert manager.buzzer is None
    monkeypatch.setitem(app.CONFIG['CO2_ALARM'], 'ENABLED', False)
    manager.init_buzzer()
    assert manager.buzzer is None


def raise_alarm(manager, good_reading, local_hour=12, eco2=2500):
    manager.co2_alarm = app.Co2Alarm(dict(app.CONFIG['CO2_ALARM'], ENABLED=True, QUIET_HOURS=(22, 7)))
    for now in range(0, 721, 10):
        manager.co2_alarm.update(good_reading(eco2=eco2), now, local_hour)
    assert manager.co2_alarm.active


def test_alarm_remembers_episode(alarm, good_reading):
    sustain(alarm, good_reading)
    assert alarm.high_started == 0
    assert alarm.last_eco2 == 2500
    assert not alarm.quiet
    alarm.update(good_reading(eco2=1800), 130, 23)
    assert alarm.last_eco2 == 1800
    assert alarm.quiet is False  # QUIET_HOURS=None in this fixture


def test_alert_takes_over_screen(manager, good_reading):
    raise_alarm(manager, good_reading)
    manager.update_display(manager.display, good_reading(), page=0)
    texts = [t[0] for t in manager.display.texts]
    assert texts == ["CO2 ALARM", "ppm", "High for 12 min", "Open a window", "Clears <=1000ppm"]
    assert any(call[0] == "pixel" for call in manager.display.calls)  # the big eCO2 number
    assert manager.display.shown == 1


def test_alert_flashes(manager, good_reading):
    raise_alarm(manager, good_reading)
    fills = []
    for _ in range(4):
        manager.display.calls.clear()
        manager.update_display(manager.display, good_reading(), page=0)
        fills.append(manager.display.calls[0])
        text_colours = {call[4] for call in manager.display.calls if call[0] == "text"}
        assert text_colours == {1 - fills[-1][1]}
    assert fills == [("fill", 1), ("fill", 0), ("fill", 1), ("fill", 0)]


def test_alert_steady_in_quiet_hours(manager, good_reading):
    raise_alarm(manager, good_reading, local_hour=23)
    for _ in range(3):
        manager.display.calls.clear()
        manager.update_display(manager.display, good_reading(), page=0)
        assert manager.display.calls[0] == ("fill", 0)
    assert ("Quiet hrs: muted", 0, 52) in manager.display.texts


def test_alert_shows_large_values_in_thousands(manager, good_reading):
    raise_alarm(manager, good_reading, eco2=12000)
    manager.update_display(manager.display, good_reading(), page=0)
    xs = [call[1] for call in manager.display.calls if call[0] == "pixel"]
    assert 0 <= min(xs) and max(xs) < app.WIDTH


def test_pages_return_when_alarm_clears(manager, good_reading):
    raise_alarm(manager, good_reading)
    manager.co2_alarm.update(good_reading(eco2=900), 730, 12)
    manager.update_display(manager.display, good_reading(), page=0)
    assert ("Main Stats", 0, 0) in manager.display.texts
    assert ("CO2 ALARM", 28, 0) not in manager.display.texts


def test_env_converters():
    assert app.on_off('1') is True
    assert app.on_off('Off') is False
    pytest.raises(ValueError, app.on_off, 'maybe')
    assert app.quiet_hours('22-7') == (22, 7)
    assert app.quiet_hours('off') is None
    pytest.raises(ValueError, app.quiet_hours, '25-7')
    cfg = copy.deepcopy(app.CONFIG)
    app.apply_env_overrides(cfg, {'CO2_ALARM_ENABLED': 'yes', 'CO2_ALARM_QUIET_HOURS': 'off'})
    assert cfg['CO2_ALARM']['ENABLED'] is True
    assert cfg['CO2_ALARM']['QUIET_HOURS'] is None

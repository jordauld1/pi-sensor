def test_graph_sampling_cadence(manager, good_reading):
    manager.sample_temp_history(good_reading(), 1000)
    manager.sample_temp_history(good_reading(), 1030)
    manager.sample_temp_history(good_reading(), 1060)
    assert list(manager.temp_history) == [21.0, 21.0]
    manager.sample_temp_history(good_reading(temp_ok=False), 2000)
    assert list(manager.temp_history) == [21.0, 21.0]


def test_graph_skips_fallback_temperature(manager):
    manager.temp_sensor.error = OSError()
    reading = manager.read_sensors()
    manager.sample_temp_history(reading, 1000)
    assert len(manager.temp_history) == 0


def test_page2_collecting_without_history(manager, good_reading):
    manager.update_display(manager.display, good_reading(), page=2)
    assert ("Collecting...", 0, 30) in manager.display.texts


def test_page2_graph_and_labels(manager, good_reading):
    manager.temp_history.extend([20.0, 21.5, 23.0])
    manager.update_display(manager.display, good_reading(), page=2)
    assert ("L:20.0", 0, 56) in manager.display.texts
    assert ("H:23.0", 64, 56) in manager.display.texts
    assert sum(call[0] == "line" for call in manager.display.calls) == 2
    assert sum(call[0] == "pixel" for call in manager.display.calls) == 1


def test_page4_word_wraps(manager, good_reading):
    manager.update_display(manager.display, good_reading(humRH=75.0), page=4)
    assert ("Too humid:", 0, 26) in manager.display.texts
    assert ("dehumidify", 0, 35) in manager.display.texts


def test_page1_labels_eco2(manager, good_reading):
    manager.update_display(manager.display, good_reading(), page=1)
    assert ("eCO2:650ppm", 0, 35) in manager.display.texts


def test_page4_moderate_aqi_recommends(manager, good_reading):
    manager.update_display(manager.display, good_reading(aqi=3, aqi_rating="Moderate"), page=4)
    assert ("Find VOC source", 0, 26) in manager.display.texts

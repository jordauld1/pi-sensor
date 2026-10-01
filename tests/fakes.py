class FakeBuzzer:
    """Stands in for PiicoDev_Buzzer. Records tones; set .result=1 to simulate an I2C failure."""
    def __init__(self, volume=None):
        self.volume = volume
        self.tones = []
        self.led = None
        self.result = 0

    def tone(self, freq, dur=0):
        self.tones.append((freq, dur))
        return self.result

    def pwrLED(self, on):
        self.led = on


class FakeBME280:
    """Stands in for PiicoDev_BME280. values() -> (tempC, pressure Pa, humidity %RH)."""
    def __init__(self, values=(21.5, 101325.0, 45.0)):
        self.result = values
        self.error = None

    def values(self):
        if self.error:
            raise self.error
        return self.result


class FakeTMP117:
    """Stands in for PiicoDev_TMP117."""
    def __init__(self, temp=21.0):
        self.temp = temp
        self.error = None

    def readTempC(self):
        if self.error:
            raise self.error
        return self.temp


class Rated:
    """Mimics the ENS160 driver's aqi / eco2 objects (.value and .rating)."""
    def __init__(self, value, rating):
        self.value = value
        self.rating = rating


class FakeENS160:
    """Stands in for PiicoDev_ENS160. Set .error to make reading .aqi raise."""
    def __init__(self):
        self.temperature = None   # set by the app for compensation
        self.humidity = None
        self.operation = "operating ok"
        self._aqi = Rated(2, "Good")
        self.tvoc = 120
        self.eco2 = Rated(650, "good")
        self.error = None

    @property
    def aqi(self):
        if self.error:
            raise self.error
        return self._aqi


class FakeDisplay:
    """Records drawing calls. self.texts holds (string, x, y) drawn since the last fill()."""
    def __init__(self):
        self.calls = []
        self.texts = []
        self.shown = 0

    def fill(self, c=0):
        self.calls.append(("fill", c))
        self.texts = []

    def text(self, s, x, y, c=1):
        self.calls.append(("text", s, x, y, c))
        self.texts.append((s, x, y))

    def show(self):
        self.shown += 1

    def pixel(self, x, y, c):
        self.calls.append(("pixel", x, y, c))

    def line(self, x1, y1, x2, y2, c):
        self.calls.append(("line", x1, y1, x2, y2, c))

    def hline(self, x, y, l, c):
        self.calls.append(("hline", x, y, l, c))

    def vline(self, x, y, h, c):
        self.calls.append(("vline", x, y, h, c))

    def rect(self, x, y, w, h, c):
        self.calls.append(("rect", x, y, w, h, c))

    def fill_rect(self, x, y, w, h, c):
        self.calls.append(("fill_rect", x, y, w, h, c))


class FakeWriteApi:
    """Stands in for influxdb_client's write API. Counts attempts; keeps successful writes."""
    def __init__(self):
        self.writes = []
        self.attempts = 0
        self.error = None

    def write(self, bucket, org, record, **kwargs):
        self.attempts += 1
        if self.error:
            raise self.error
        self.writes.append({"bucket": bucket, "org": org, "record": list(record), **kwargs})


class FakeInfluxClient:
    """Stands in for InfluxDBClient where only close() is needed (cleanup tests)."""
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeClock:
    """Replaces the app module's `time` so tests control time.time() and time.time_ns()."""
    def __init__(self, now=10_000.0):
        self.now = now

    def time(self):
        return self.now

    def time_ns(self):
        return int(round(self.now * 1_000_000_000))

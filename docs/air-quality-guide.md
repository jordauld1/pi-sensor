# Air Quality Reading Guide

How to read the monitor's values, and where the recommendations on the display's Environment page come from.
The thresholds live in `CONFIG['ENVIRONMENT_RATINGS']` in `ens160AirQualitySensor.py`. If you change one there,
change the matching table here.

## What the sensors measure

- **ENS160** is a metal-oxide gas sensor. It reports TVOC (total volatile organic compounds, in ppb, calibrated
  to ethanol) and eCO2 (equivalent CO2, in ppm). Both are calculated on the chip from the gas signal. **eCO2 is an
  estimate, not a CO2 measurement.** Cleaning products, cosmetics, cooking or alcohol can raise it in an empty
  room, and a crowded room with few VOCs can read lower than its real CO2.
- **AQI-UBA** (1 to 5) is the ENS160's own index. It is based only on the TVOC signal, using the German Federal
  Environment Agency (UBA) TVOC guidance.
- **TMP117** measures temperature (accurate to about 0.1 °C). **BME280** measures humidity and pressure.
  The ENS160 has no temperature or humidity sensor of its own and needs both for compensation, so the app passes
  it the TMP117 temperature and BME280 humidity every reading.

## VOCs: AQI-UBA level

| AQI | Rating | UBA assessment and advice | Display shows |
|-----|--------|---------------------------|---------------|
| 1 | Excellent | No objections. Target level. | nothing |
| 2 | Good | No relevant objections. Ventilate normally. | nothing |
| 3 | Moderate | Some objections. Ventilate more, look for sources. | "Find VOC source" (advisory) |
| 4 | Poor | Major objections. Ventilate much more, look for sources. | "Ventilate: VOCs" (act soon) |
| 5 | Unhealthy | Not acceptable. Use the room only if unavoidable. | "VOCs high: air out" (act now) |

UBA notes that TVOC has no direct toxicological basis. Treat it as a sign of ventilation and VOC sources, not as
a health measurement.

## eCO2

| eCO2 (ppm) | ENS160 rating | ENS160 datasheet advice | Display shows |
|------------|---------------|-------------------------|---------------|
| 400-600 | Excellent | Target | nothing |
| 600-800 | Good | Average | nothing |
| 800-1000 | Fair | Optional ventilation | "Get fresh air" (advisory) |
| 1000-1500 | Poor | Ventilation recommended | "Open a window" (act soon) |
| above 1500 | Bad | Ventilation required | "Ventilate now!" (act now) |

These are the same bands stored in InfluxDB as `eco2_rating`. The CO2 alarm, if enabled, uses the top band.

For comparison, UBA's guidance for real CO2 is: below 1000 ppm harmless, 1000-2000 ppm ventilate, above
2000 ppm unacceptable. The ENS160 bands are stricter at the top, which suits a bedroom, where lower CO2 is
linked to better sleep. ASHRAE treats CO2 as an indicator of ventilation rather than a health limit.

## Humidity

| Relative humidity | Display shows |
|-------------------|---------------|
| below 30% | "Too dry: humidify" (act soon) |
| 30-60% | nothing (30-50% is ideal) |
| above 60% | "Too humid: dehumidify" (act soon) |

Source: US EPA, keep indoor humidity "below 60 percent (ideally between 30 and 50 percent)". Above 60% for long
periods encourages mould and dust mites. The ENS160's own readings are also most reliable between 20% and 80%.

## Temperature

| Temperature | Display shows |
|-------------|---------------|
| below 18 °C | "Too cold" (advisory) |
| 18-26 °C | nothing |
| above 26 °C | "Too warm" (advisory) |

The WHO Housing and Health Guidelines (2018) give 18 °C as a safe indoor minimum, higher for older people, young
children and people with chronic illness. 26 °C is about the top of the ASHRAE 55 comfort range in summer
clothing. Many sleep sources suggest a cooler bedroom at night (roughly 16-20 °C); the monitor uses the same
thresholds day and night.

## How the Environment page chooses messages

Each rule has a severity: act now, act soon, or advisory. The page shows the two most severe. When severities are
equal, the order is eCO2, VOCs, humidity, temperature. With nothing to recommend, it shows the air quality rating
("Excellent air" or "Air quality good").

## Getting accurate readings

1. **Placement:** away from direct sunlight, heaters and vents, at roughly breathing height, and away from the
   Raspberry Pi's own heat.
2. **Warm-up:** the ENS160 needs a few minutes after power-on (shown as "warm-up"). After first use it takes
   24-48 hours to settle its baseline, so early readings are less reliable.
3. **Fresh air now and then:** the ENS160 adjusts its baseline automatically and works best when the room is
   aired regularly.

## Sources

- ScioSense, ENS160 Datasheet v1.3 (2023): Table 5 (eCO2), Table 6 (AQI-UBA), section 8.2 (compensation).
- Umweltbundesamt Ad-hoc-AG, Bundesgesundheitsblatt 50 (2007) 990-1005: TVOC guidance levels.
- Umweltbundesamt Ad-hoc-AG, "Gesundheitliche Bewertung von Kohlendioxid in der Innenraumluft" (2008).
- ASHRAE, Position Document on Indoor Carbon Dioxide (2025).
- US EPA, "A Brief Guide to Mold, Moisture and Your Home".
- WHO Housing and Health Guidelines (2018).
- ASHRAE Standard 55, Thermal Environmental Conditions for Human Occupancy.

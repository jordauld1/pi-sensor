# Air Quality Reading Interpretation Guide

Reference guide for understanding the sensor readings from the ENS160-based monitoring system.

## ENS160 Sensor Characteristics

- Metal oxide (MOX) sensor technology
- Built-in temperature and humidity compensation
- Automatic baseline correction
- UBA-compliant air quality ratings

## Air Quality Index (AQI) Response Guide

| AQI | Rating    | Description                              | Action                          |
|-----|-----------|------------------------------------------|---------------------------------|
| 1   | Excellent | Ideal indoor air quality                 | No action needed                |
| 2   | Good      | Normal indoor conditions                 | Continue regular ventilation    |
| 3   | Moderate  | Some air quality deterioration           | Increase ventilation            |
| 4   | Poor      | Significant air quality issues           | Open windows, use air purifier  |
| 5   | Unhealthy | Severe air quality problems              | Maximum ventilation, evacuate if needed |

## TVOC (Total Volatile Organic Compounds)

| Range           | Level    | Action                                           |
|-----------------|----------|--------------------------------------------------|
| 0–500 ppb       | Low      | Normal indoor conditions, no action needed        |
| 500–2,000 ppb   | Moderate | Improve ventilation, check for VOC sources        |
| 2,000–5,000 ppb | High     | Identify and remove sources, air purification     |
| >5,000 ppb      | Very High| Immediate ventilation, evacuate if necessary      |

## eCO2 (Equivalent CO2) Guidelines

| Range           | Quality    | Action                              |
|-----------------|------------|-------------------------------------|
| 400–800 ppm     | Excellent  | Normal outdoor to indoor levels     |
| 800–1,000 ppm   | Good       | Typical occupied indoor space       |
| 1,000–1,500 ppm | Fair       | Increase ventilation recommended    |
| 1,500–2,000 ppm | Poor       | Open windows, check HVAC            |
| >2,000 ppm      | Dangerous  | Immediate ventilation required      |

## Response Actions Matrix

| Condition     | Immediate Action     | Long-term Action     |
|---------------|----------------------|----------------------|
| High TVOC     | Open windows         | Find VOC sources     |
| High eCO2     | Increase ventilation | Check HVAC           |
| Poor AQI      | Air purification     | Environmental audit  |
| High Humidity | Dehumidification     | Check for leaks      |
| Low Humidity  | Use humidifier       | Monitor heating      |

## Best Practices for Accurate Readings

1. **Sensor Placement** — Avoid direct sunlight and airflow, place at breathing height, keep away from walls
2. **Baseline Calibration** — Allow 24–48 hours for initial baseline, ensure regular fresh air exposure
3. **Environmental Conditions** — Maintain stable temperature and humidity, avoid rapid changes
4. **Maintenance** — Regular dust cleaning, periodic baseline recalibration

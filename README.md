# README

This project is a small Python scheduler for a Lutron WiFi smart switch that can follow three operating modes:

- Weekday schedule
- Shabbos schedule
- Yom Tov schedule

It reads a YAML config, resolves the current day mode, and toggles the Lutron switch using an HTTP API.

## What it does

- Uses a weekday schedule by default.
- Detects a Shabbos window based on the configured location and the current day.
- Detects Yom Tov dates from a configured list of ISO dates.
- Uses sunset-based timing for Shabbos and Yom Tov windows.
- Sends ON/OFF commands to a Lutron switch over HTTP.

## Files

- `scheduler.py` — main scheduler logic
- `config.example.yaml` — sample configuration
- `requirements.txt` — Python dependencies

## Quick start

1. Create a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the sample config and edit it:

   ```bash
   cp config.example.yaml config.yaml
   ```

4. Update `config.yaml` with your bridge host, switch id, and schedule values.

5. Run the scheduler once:

   ```bash
   python scheduler.py --config config.yaml --once
   ```

6. To keep it running in a loop:

   ```bash
   python scheduler.py --config config.yaml
   ```

## Notes

- The Lutron HTTP endpoint in this example is a generic pattern. Adjust it to match your bridge or integration API.
- The Yom Tov list is intentionally explicit so it is easy to maintain.
- For exact halachic timing, review the values in `shabbos` and `yom_tov` offsets against your local zmanim.

## Example config values

```yaml
device:
  base_url: "http://192.168.1.10"
  token: "token-or-empty"
  switch_id: 42

schedule:
  weekday:
    on: "06:30"
    off: "22:30"
  shabbos:
    on_offset_minutes: 20
    off_offset_minutes: 45
  yom_tov:
    on_offset_minutes: 15
    off_offset_minutes: 30

calendar:
  yom_tov_dates:
    - "2026-09-22"
    - "2026-09-23"
  location:
    name: "New York"
    latitude: 40.7128
    longitude: -74.0060
    timezone: "America/New_York"
```

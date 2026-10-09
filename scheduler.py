import argparse
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import yaml
from astral import LocationInfo
from astral.sun import sun
from pytz import timezone


@dataclass
class ScheduleSpec:
    mode: str
    on_time: datetime
    off_time: datetime


class LutronSwitchClient:
    """Simple Lutron HTTP client.

    Update the actual API endpoint to match your bridge or home automation integration.
    This example assumes a base URL and a switch id, and sends a JSON payload such as:
    {"state": "on"} or {"state": "off"}
    """

    def __init__(self, base_url: str, switch_id: Any, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.switch_id = str(switch_id)
        self.token = token or ""
        self.headers = {}
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
        self.headers["Content-Type"] = "application/json"

    def set_state(self, state: bool) -> None:
        payload = {"state": "on" if state else "off"}
        url = f"{self.base_url}/api/devices/{self.switch_id}/state"
        response = requests.put(url, headers=self.headers, data=json.dumps(payload), timeout=10)
        response.raise_for_status()


class Scheduler:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.device_config = config.get("device", {})
        self.schedule_config = config.get("schedule", {})
        self.calendar_config = config.get("calendar", {})
        self.location_cfg = self.calendar_config.get("location", {})
        self.location = LocationInfo(
            name=self.location_cfg.get("name", "Home"),
            region="",
            latitude=float(self.location_cfg.get("latitude", 0.0)),
            longitude=float(self.location_cfg.get("longitude", 0.0)),
            timezone=self.location_cfg.get("timezone", "UTC"),
        )
        self.yom_tov_dates = set(self.calendar_config.get("yom_tov_dates", []))

    def get_sunset(self, target_day: date) -> datetime:
        tz = timezone(self.location.timezone)
        sunset_dt = sun(self.location.observer, date=target_day)["sunset"]
        if sunset_dt.tzinfo is None:
            sunset_dt = tz.localize(sunset_dt)
        return sunset_dt.astimezone(tz)

    def resolve_mode(self, now: datetime) -> str:
        if now.date().isoformat() in self.yom_tov_dates:
            return "yom_tov"

        weekday = now.weekday()
        if weekday == 4:
            friday_sunset = self.get_sunset(now.date())
            return "shabbos" if now >= friday_sunset else "weekday"
        if weekday == 5:
            saturday_sunset = self.get_sunset(now.date())
            return "shabbos" if now < saturday_sunset else "weekday"
        return "weekday"

    def get_weekday_times(self, target_day: date) -> tuple[datetime, datetime]:
        daily = self.schedule_config.get("weekday", {})
        on_time = datetime.combine(target_day, self.parse_time(daily.get("on", "06:30")))
        off_time = datetime.combine(target_day, self.parse_time(daily.get("off", "22:30")))
        return on_time, off_time

    def get_shabbos_times(self, target_day: date) -> tuple[datetime, datetime]:
        config = self.schedule_config.get("shabbos", {})
        on_offset = int(config.get("on_offset_minutes", 20))
        off_offset = int(config.get("off_offset_minutes", 45))

        friday_sunset = self.get_sunset(target_day)
        saturday_sunset = self.get_sunset(target_day + timedelta(days=1))

        on_time = friday_sunset + timedelta(minutes=on_offset)
        off_time = saturday_sunset + timedelta(minutes=off_offset)
        return on_time, off_time

    def get_yom_tov_times(self, target_day: date) -> tuple[datetime, datetime]:
        config = self.schedule_config.get("yom_tov", {})
        on_offset = int(config.get("on_offset_minutes", 15))
        off_offset = int(config.get("off_offset_minutes", 30))

        # Yom Tov times usually follow sunset-based schedule. This keeps the logic readable
        # and easy to adjust for local holiday rules.
        sunset = self.get_sunset(target_day)
        next_sunset = self.get_sunset(target_day + timedelta(days=1))

        on_time = sunset + timedelta(minutes=on_offset)
        off_time = next_sunset + timedelta(minutes=off_offset)
        return on_time, off_time

    def resolve_schedule(self, now: datetime) -> ScheduleSpec:
        mode = self.resolve_mode(now)
        target_day = now.date()

        if mode == "weekday":
            on_time, off_time = self.get_weekday_times(target_day)
        elif mode == "shabbos":
            on_time, off_time = self.get_shabbos_times(target_day)
        else:
            on_time, off_time = self.get_yom_tov_times(target_day)

        return ScheduleSpec(mode=mode, on_time=on_time, off_time=off_time)

    @staticmethod
    def parse_time(value: str) -> dt_time:
        hour, minute = [int(part) for part in value.split(":")]
        return dt_time(hour, minute)

    def evaluate(self, now: datetime) -> bool:
        spec = self.resolve_schedule(now)
        should_be_on = spec.on_time <= now <= spec.off_time
        return should_be_on


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file_handle:
        return yaml.safe_load(file_handle) or {}


def run_once(config_path: str) -> None:
    config = load_config(config_path)
    scheduler = Scheduler(config)
    client = LutronSwitchClient(
        base_url=config["device"]["base_url"],
        switch_id=config["device"]["switch_id"],
        token=config["device"].get("token"),
    )

    now = datetime.now()
    should_be_on = scheduler.evaluate(now)
    client.set_state(should_be_on)
    print(
        f"{now.isoformat()} | mode={scheduler.resolve_mode(now)} | state={'ON' if should_be_on else 'OFF'}"
    )


def poll_loop(config_path: str, interval_seconds: int = 60) -> None:
    config = load_config(config_path)
    scheduler = Scheduler(config)
    client = LutronSwitchClient(
        base_url=config["device"]["base_url"],
        switch_id=config["device"]["switch_id"],
        token=config["device"].get("token"),
    )

    while True:
        now = datetime.now()
        should_be_on = scheduler.evaluate(now)
        client.set_state(should_be_on)
        print(
            f"{now.isoformat()} | mode={scheduler.resolve_mode(now)} | state={'ON' if should_be_on else 'OFF'}"
        )
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lutron WiFi switch scheduler")
    parser.add_argument("--config", default="config.yaml", help="Path to the YAML config file")
    parser.add_argument("--once", action="store_true", help="Run one evaluation and exit")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds")
    args = parser.parse_args()

    if args.once:
        run_once(args.config)
        return

    poll_loop(args.config, args.interval)


if __name__ == "__main__":
    main()

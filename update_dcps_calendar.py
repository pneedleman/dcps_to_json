#!/usr/bin/env python3
"""Fetch DCPS school calendar .ics and convert to compact JSON."""

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DCPS_ICS_URL = "https://calendar.google.com/calendar/ical/dcpstech%40dc.gov/public/basic.ics"
OUTPUT_PATH = Path("data/dcps_calendar.json")

# Keywords in SUMMARY that indicate a day off for students
DAY_OFF_KEYWORDS = ["No school", "Break", "Holiday", "closed", "Teacher", "PD"]


def unescape_ics(value: str) -> str:
    """Unescape iCalendar text escape sequences: \\, \\;, \\,."""
    placeholder = "\x00"
    value = value.replace("\\\\", placeholder)  # escaped backslash
    value = value.replace("\\;", ";")
    value = value.replace("\\,", ",")
    value = value.replace("\\n", "\n")
    value = value.replace(placeholder, "\\")
    return value


def parse_ics(ics_text: str) -> list[dict]:
    """Parse iCalendar text and return list of day-off entries."""
    # Unfold continuation lines (CRLF/LF followed by space/tab continues previous line)
    ics_text = re.sub(r"\r?\n[ \t]", "", ics_text)
    events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics_text, re.DOTALL)
    days_off = []

    for event in events:
        summary_match = re.search(r"SUMMARY:(.*?)(?:\r\n|\n)", event)
        start_match = re.search(r"DTSTART;VALUE=DATE:(\d{8})", event)
        end_match = re.search(r"DTEND;VALUE=DATE:(\d{8})", event)

        if not summary_match or not start_match:
            continue

        summary = unescape_ics(summary_match.group(1).strip())

        if not any(keyword in summary for keyword in DAY_OFF_KEYWORDS):
            continue

        start = date(
            int(start_match.group(1)[0:4]),
            int(start_match.group(1)[4:6]),
            int(start_match.group(1)[6:8]),
        )

        if end_match:
            end = date(
                int(end_match.group(1)[0:4]),
                int(end_match.group(1)[4:6]),
                int(end_match.group(1)[6:8]),
            )
        else:
            end = start + timedelta(days=1)

        current = start
        while current < end:
            days_off.append({
                "date": current.isoformat(),
                "name": summary,
            })
            current += timedelta(days=1)

    # Sort and remove duplicates
    seen = set()
    unique_days = []
    for day in sorted(days_off, key=lambda x: x["date"]):
        if day["date"] not in seen:
            seen.add(day["date"])
            unique_days.append(day)

    return unique_days


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        response = requests.get(DCPS_ICS_URL, timeout=60)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to fetch DCPS calendar: {e}", file=sys.stderr)
        return 1

    days_off = parse_ics(response.text)

    calendar_data = {
        "source_url": DCPS_ICS_URL,
        "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "count": len(days_off),
        "days_off": days_off,
    }

    OUTPUT_PATH.write_text(json.dumps(calendar_data, indent=2))
    print(f"Wrote {len(days_off)} day(s) off to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

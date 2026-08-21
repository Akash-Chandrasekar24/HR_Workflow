import re
import structlog
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional

logger = structlog.get_logger(__name__)


class TimeParserService:
    """
    AI & Heuristic Natural Language Email Reply Availability Parser.
    Extracts date, start time, end time, and timezone from employee email replies.
    """

    def parse_availability_text(
        self,
        reply_text: str,
        reference_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Parses natural language employee reply string into ISO datetimes and human readable ranges.
        Example reply_text: "I am available tomorrow August 18th from 3:00 PM to 4:00 PM IST"
        """
        ref_dt = reference_date or datetime.now()
        text = reply_text.strip()
        text_lower = text.lower()

        # 1. Parse Date
        parsed_date = self._extract_date(text_lower, ref_dt)

        # 2. Parse Times (Start & End)
        start_time_str, end_time_str = self._extract_time_range(text_lower)

        # Build ISO Datetime objects
        start_hour, start_min = map(int, start_time_str.split(":"))
        end_hour, end_min = map(int, end_time_str.split(":"))

        start_dt = datetime(parsed_date.year, parsed_date.month, parsed_date.day, start_hour, start_min)
        end_dt = datetime(parsed_date.year, parsed_date.month, parsed_date.day, end_hour, end_min)

        # Format display strings
        display_date = start_dt.strftime("%A, %B %d, %Y")
        display_time_range = f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')} (IST)"

        result = {
            "parsed_date": parsed_date.strftime("%Y-%m-%d"),
            "start_time": start_dt.strftime("%H:%M"),
            "end_time": end_dt.strftime("%H:%M"),
            "start_datetime_iso": start_dt.strftime("%Y-%m-%dT%H:%M:%S+05:30"),
            "end_datetime_iso": end_dt.strftime("%Y-%m-%dT%H:%M:%S+05:30"),
            "display_date": display_date,
            "display_time_range": display_time_range,
            "raw_text": reply_text
        }

        logger.info("Successfully parsed employee availability email reply", display_date=display_date, display_time=display_time_range)
        return result

    def _extract_date(self, text_lower: str, ref_dt: datetime) -> date:
        """Extracts date from text or relative keywords (today/tomorrow)."""
        if "tomorrow" in text_lower:
            return (ref_dt + timedelta(days=1)).date()
        if "today" in text_lower:
            return ref_dt.date()

        # Look for explicit month & day patterns (e.g. "aug 18", "august 18th", "18th august")
        months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
                  "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

        for idx, m in enumerate(months):
            m_num = (idx % 12) + 1
            pattern1 = rf"{m}\s+(\d{{1,2}})(?:st|nd|rd|th)?"
            pattern2 = rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+{m}"

            m1 = re.search(pattern1, text_lower)
            if m1:
                day = int(m1.group(1))
                return date(ref_dt.year, m_num, day)

            m2 = re.search(pattern2, text_lower)
            if m2:
                day = int(m2.group(1))
                return date(ref_dt.year, m_num, day)

        # Default to tomorrow if unspecified
        return (ref_dt + timedelta(days=1)).date()

    def _extract_time_range(self, text_lower: str) -> Tuple[str, str]:
        """Extracts start and end times in HH:MM (24-hour) format."""
        # Search for "X pm to Y pm" or "X:XX pm - Y:XX pm"
        time_pattern = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:to|-|until)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)"
        match = re.search(time_pattern, text_lower)

        if match:
            sh, sm, s_ampm, eh, em, e_ampm = match.groups()
            s_ampm = s_ampm or e_ampm # Inherit PM if start AM/PM omitted (e.g. 3 to 4 pm)

            s_hour = self._to_24h(int(sh), s_ampm)
            s_min = int(sm) if sm else 0

            e_hour = self._to_24h(int(eh), e_ampm)
            e_min = int(em) if em else 0

            return f"{s_hour:02d}:{s_min:02d}", f"{e_hour:02d}:{e_min:02d}"

        # Single time fallback (default 1 hour duration)
        single_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text_lower)
        if single_match:
            sh, sm, ampm = single_match.groups()
            s_hour = self._to_24h(int(sh), ampm)
            s_min = int(sm) if sm else 0
            e_hour = (s_hour + 1) % 24
            return f"{s_hour:02d}:{s_min:02d}", f"{e_hour:02d}:{s_min:02d}"

        # Default fallback: 15:00 to 16:00
        return "15:00", "16:00"

    def _to_24h(self, hour: int, ampm: Optional[str]) -> int:
        """Converts 12-hour format to 24-hour integer."""
        if not ampm:
            return hour
        ampm = ampm.lower()
        if ampm == "pm" and hour < 12:
            return hour + 12
        if ampm == "am" and hour == 12:
            return 0
        return hour

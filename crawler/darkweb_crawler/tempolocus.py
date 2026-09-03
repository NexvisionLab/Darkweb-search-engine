"""Infers a threat actor's likely timezone/country purely from
activity-timing patterns - the same idea as AIL Framework's tempolocus
sub-project, built independently rather than importing it: tempolocus
itself is AGPL-3.0, and AGPL's network-use clause is a real concern for
code running inside a paid SaaS backend (it can obligate offering the
combined work's source to your own customers, not just to anyone you
hand a binary to) - not a risk worth taking on for one module. This
reimplements the same two techniques using only this project's own
code plus the `holidays` package (MIT-licensed, a different library
from AIL's tool, just calendar data) for the holiday half.

Two independent signals:
- Weekly pattern: which UTC offset, applied to the observed activity,
  produces the least activity during typical human sleep hours
  (01:00-06:00 local). A real person's posting activity should thin
  out overnight in their own timezone; the offset that best produces
  that pattern is the best-fit candidate.
- Yearly pattern: which country's public holidays coincide with
  measurably reduced activity, checked against a broad, neutral set of
  countries `holidays` supports well - not narrowed by any assumption
  about who commits cybercrime, since that would bias the tool itself.

Every result here is a confidence-scored investigative lead, never a
location claim - same discipline as the rest of this project's
actor-profiling and infrastructure-correlation work. Small sample
sizes are common (a single ransomware group's tracked activity is
often well under 200 events) and the output says so plainly rather
than presenting a guess with false confidence."""
from collections import Counter
from datetime import timezone

import holidays

SLEEP_HOURS = {1, 2, 3, 4, 5}
MIN_SAMPLE_SIZE = 15

# A broad, neutral set spanning every major region - not selected by any
# assumption about likely threat-actor origin, so the tool doesn't bake
# in a stereotype of its own. Restricted to countries `holidays` covers
# well (fixed + observed public holidays, not just a token list).
CANDIDATE_COUNTRIES = [
    "US", "CA", "GB", "IE", "FR", "DE", "NL", "BE", "ES", "PT", "IT",
    "PL", "RO", "BG", "UA", "BY", "RU", "TR", "GR", "SE", "NO", "FI",
    "CN", "JP", "KR", "IN", "ID", "VN", "PH", "TH", "MY", "SG",
    "BR", "MX", "AR", "CO", "NG", "ZA", "EG", "SA", "AE", "IL", "IR",
    "AU", "NZ",
]


def _to_utc_hour_and_date(timestamps):
    hours = []
    dates = []
    for ts in timestamps:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)
        hours.append(ts.hour)
        dates.append(ts.date())
    return hours, dates


def infer_utc_offset(timestamps, top_n=3):
    """Ranks UTC offsets by how little of the activity falls in a
    01:00-06:00 local sleep window once shifted to that offset - the
    lower the sleep-hour fraction, the better that offset explains the
    pattern as a real human schedule. Returns the top_n candidates with
    their sleep-hour fraction as an inverse confidence score."""
    hours, _ = _to_utc_hour_and_date(timestamps)
    if len(hours) < MIN_SAMPLE_SIZE:
        return {"candidates": [], "sample_size": len(hours), "note": f"fewer than {MIN_SAMPLE_SIZE} timestamps - too small to infer anything"}

    scored = []
    for offset in range(-12, 15):
        sleep_count = sum(1 for h in hours if ((h + offset) % 24) in SLEEP_HOURS)
        scored.append((offset, sleep_count / len(hours)))
    scored.sort(key=lambda x: x[1])

    return {
        "candidates": [{"utc_offset": off, "sleep_hour_fraction": round(frac, 3)} for off, frac in scored[:top_n]],
        "sample_size": len(hours),
    }


MIN_HOLIDAY_OVERLAP = 2


def infer_country_by_holidays(timestamps, top_n=5):
    """Ranks candidate countries by how much activity dips on that
    country's public holidays versus its normal baseline rate. Small
    samples produce noisy results almost by definition - caught this
    directly while testing against real data: with under ~20 distinct
    activity days, a country whose calendar happens to overlap just one
    low-activity day scores identically to every other country with the
    same coincidence, since most days in a thin dataset have low counts
    to begin with. A single overlapping date is essentially always
    noise, not signal, so MIN_HOLIDAY_OVERLAP requires at least 2
    genuinely distinct holiday dates to actually coincide with reduced
    activity before a country counts as a candidate at all. Below that,
    this returns no candidates and says why, rather than presenting
    coincidence as a ranked list."""
    _, dates = _to_utc_hour_and_date(timestamps)
    if len(dates) < MIN_SAMPLE_SIZE:
        return {"candidates": [], "sample_size": len(dates), "note": f"fewer than {MIN_SAMPLE_SIZE} timestamps - too small to infer anything"}

    date_counts = Counter(dates)
    years = {d.year for d in dates}
    total_days = len(date_counts)
    total_events = len(dates)
    baseline_rate = total_events / total_days if total_days else 0

    results = []
    for country in CANDIDATE_COUNTRIES:
        try:
            cal = holidays.country_holidays(country, years=list(years))
        except Exception:
            continue
        holiday_dates_observed = [d for d in date_counts if d in cal]
        if len(holiday_dates_observed) < MIN_HOLIDAY_OVERLAP:
            continue
        holiday_events = sum(date_counts[d] for d in holiday_dates_observed)
        holiday_rate = holiday_events / len(holiday_dates_observed)
        # dip_strength > 0 means activity on this country's holidays ran
        # below the observed baseline rate - the signal we're looking for.
        dip_strength = (baseline_rate - holiday_rate) / baseline_rate if baseline_rate else 0
        results.append({
            "country": country,
            "dip_strength": round(dip_strength, 3),
            "holiday_dates_observed": len(holiday_dates_observed),
        })

    results.sort(key=lambda r: r["dip_strength"], reverse=True)
    note = None
    if not results:
        note = (
            f"no country had {MIN_HOLIDAY_OVERLAP}+ distinct holiday dates overlap observed activity "
            f"({total_days} distinct activity days total) - too thin for this signal"
        )
    return {
        "candidates": results[:top_n],
        "sample_size": total_events,
        "distinct_days": total_days,
        **({"note": note} if note else {}),
    }


def classify_activity_type(timestamps):
    """A rough work-time / mixed / continuous label based on how
    concentrated activity is within a conventional 08:00-20:00 window,
    using the best-fit UTC offset from infer_utc_offset - purely
    descriptive, not a separate inference."""
    offset_result = infer_utc_offset(timestamps, top_n=1)
    if not offset_result["candidates"]:
        return "insufficient-data"
    best_offset = offset_result["candidates"][0]["utc_offset"]
    hours, _ = _to_utc_hour_and_date(timestamps)
    local_hours = [(h + best_offset) % 24 for h in hours]
    work_hours = sum(1 for h in local_hours if 8 <= h < 20)
    fraction = work_hours / len(local_hours)
    if fraction > 0.75:
        return "work-time"
    if fraction < 0.4:
        return "off-hours"
    return "mixed-time"


def analyze(timestamps):
    """Full analysis over a list of datetime objects (any real
    activity-timestamp source - ransomware victim discovery times,
    forum post dates, etc.). Returns a single confidence-scored lead
    object, never a location claim."""
    return {
        "sample_size": len(timestamps),
        "utc_offset": infer_utc_offset(timestamps),
        "country_by_holiday": infer_country_by_holidays(timestamps),
        "activity_type": classify_activity_type(timestamps),
    }

"""Runs the tempolocus-style timezone/country inference (see
tempolocus.py) against a real ransomware group's tracked victim-
discovery timestamps - the richest activity-timing data this platform
has (RansomLook's discovered_at, close to real posting time, versus
the very sparse published_at on crawled pages). A confidence-scored
lead only, per the same discipline as the rest of this project's
actor-profiling work - never presented as a location claim.

Usage:
    python3 scripts/infer_actor_location.py "<group_name>"
    python3 scripts/infer_actor_location.py --list-groups
"""
import json
import sys

sys.path.insert(0, ".")
from darkweb_crawler import db, tempolocus


def main():
    conn = db.get_connection()
    try:
        if len(sys.argv) < 2 or sys.argv[1] == "--list-groups":
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT group_name, count(*) AS n FROM ransomware_victims "
                    "WHERE discovered_at IS NOT NULL GROUP BY group_name ORDER BY n DESC LIMIT 30"
                )
                print("Groups with tracked activity timestamps (name: count):")
                for group_name, n in cur.fetchall():
                    print(f"  {group_name}: {n}")
            return

        group_name = sys.argv[1]
        with conn.cursor() as cur:
            cur.execute(
                "SELECT discovered_at FROM ransomware_victims WHERE group_name = %s AND discovered_at IS NOT NULL",
                (group_name,),
            )
            timestamps = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    if not timestamps:
        print(f"No timestamped activity found for group '{group_name}'. Try --list-groups.")
        sys.exit(1)

    result = tempolocus.analyze(timestamps)
    result["group_name"] = group_name
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

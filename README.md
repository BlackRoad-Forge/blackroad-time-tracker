# blackroad-time-tracker

Personal time tracking and productivity analytics with billable hours and CSV export.

## Usage

```bash
# Create a project
python time_tracker.py project-create myproject --client "Acme" --rate 150 --budget 40

# Start a timer
python time_tracker.py start myproject "Build auth module"

# Stop and log
python time_tracker.py stop --billable

# Log a past entry
python time_tracker.py log myproject "Code review" \
  --start "2025-01-15T09:00" --end "2025-01-15T10:30" --billable

# Today's log
python time_tracker.py today

# Weekly report
python time_tracker.py weekly

# Project stats
python time_tracker.py project-stats myproject

# Billable report
python time_tracker.py billable --start 2025-01-01 --end 2025-01-31

# Export to CSV
python time_tracker.py export-csv --month 2025-01

# Focus streak
python time_tracker.py focus-streaks

# Check active timer
python time_tracker.py status
```

## Storage

SQLite at `~/.blackroad-personal/time_tracker.db`.

## License

Proprietary — BlackRoad OS, Inc.

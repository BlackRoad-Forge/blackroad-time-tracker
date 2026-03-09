"""Tests for time_tracker.py"""
import csv, json, os, sys
from datetime import datetime, timedelta, date
from pathlib import Path
from unittest.mock import MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import time_tracker as tt


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(tt, "DB_PATH", str(tmp_path / "test_tt.db"))
    yield tmp_path


def _log(project="proj", task="task", minutes=60, billable=False):
    db  = tt.get_db()
    now = datetime.now()
    start = (now - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    end   = now.isoformat(timespec="seconds")
    db.execute("""
        INSERT INTO entries(project,task,description,start_time,end_time,duration_min,tags_json,billable)
        VALUES(?,?,?,?,?,?,?,?)
    """, (project, task, "", start, end, minutes, "[]", 1 if billable else 0))
    db.commit()


def test_db_init(tmp_db):
    assert tt.get_db() is not None


def test_start_timer(tmp_db):
    args = MagicMock(project="myproj", task="coding", description="")
    tt.cmd_start(args)
    db  = tt.get_db()
    row = db.execute("SELECT * FROM active_timer WHERE id=1").fetchone()
    assert row is not None
    assert row["project"] == "myproj"


def test_start_twice_warns(tmp_db, capsys):
    args = MagicMock(project="p", task="t", description="")
    tt.cmd_start(args)
    tt.cmd_start(args)
    out = capsys.readouterr().out
    assert "already running" in out.lower() or "stop" in out.lower()


def test_stop_timer(tmp_db):
    db  = tt.get_db()
    start = (datetime.now() - timedelta(minutes=30)).isoformat(timespec="seconds")
    db.execute("INSERT OR REPLACE INTO active_timer(id,project,task,description,start_time) VALUES(1,?,?,?,?)",
               ("p","t","",start))
    db.commit()
    args = MagicMock(tags="", billable=False)
    tt.cmd_stop(args)
    row = db.execute("SELECT * FROM active_timer WHERE id=1").fetchone()
    assert row is None
    entries = db.execute("SELECT * FROM entries").fetchall()
    assert len(entries) == 1
    assert entries[0]["duration_min"] >= 29


def test_log_entry(tmp_db):
    start = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    end   = datetime.now().strftime("%Y-%m-%dT%H:%M")
    args  = MagicMock(project="p", task="t", description="", start=start, end=end, tags="", billable=False)
    tt.cmd_log(args)
    db   = tt.get_db()
    rows = db.execute("SELECT * FROM entries").fetchall()
    assert len(rows) == 1
    assert rows[0]["project"] == "p"


def test_duration_str():
    assert tt.duration_str(90) == "1h 30m"
    assert tt.duration_str(0)  == "0h 00m"


def test_project_create(tmp_db):
    args = MagicMock()
    args.name = "myproj"
    args.client = "Acme"
    args.rate = 150.0
    args.budget = 40.0
    args.color = "#FF0000"
    tt.cmd_project_create(args)
    db  = tt.get_db()
    row = db.execute("SELECT * FROM projects WHERE name='myproj'").fetchone()
    assert row["hourly_rate"] == 150.0


def test_weekly_report(tmp_db, capsys):
    _log(minutes=120)
    args = MagicMock()
    tt.cmd_weekly(args)
    out = capsys.readouterr().out
    assert "proj" in out or "Weekly" in out


def test_export_csv(tmp_db, tmp_path):
    _log(minutes=60, billable=True)
    args = MagicMock(month=date.today().strftime("%Y-%m"))
    os.chdir(tmp_path)
    tt.cmd_export_csv(args)
    fname = tmp_path / f"time_{date.today().strftime('%Y-%m')}.csv"
    assert fname.exists()
    with open(fname) as f:
        reader = csv.reader(f)
        rows   = list(reader)
    assert len(rows) >= 2  # header + 1 entry


def test_focus_streaks_consecutive(tmp_db, capsys):
    for i in range(3):
        _log(minutes=60)
    args = MagicMock()
    tt.cmd_focus_streaks(args)
    out = capsys.readouterr().out
    assert "streak" in out.lower()

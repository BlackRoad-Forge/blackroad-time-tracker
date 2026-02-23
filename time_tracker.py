#!/usr/bin/env python3
"""BlackRoad Time Tracker – personal time tracking and productivity analytics."""

import argparse, csv, json, os, sqlite3, sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Optional, List

GREEN  = "\033[0;32m"; RED    = "\033[0;31m"; YELLOW = "\033[1;33m"
CYAN   = "\033[0;36m"; BOLD   = "\033[1m";    NC     = "\033[0m"
def ok(m):   print(f"{GREEN}✓{NC} {m}")
def err(m):  print(f"{RED}✗{NC} {m}", file=sys.stderr)
def info(m): print(f"{CYAN}ℹ{NC} {m}")
def warn(m): print(f"{YELLOW}⚠{NC} {m}")

DB_PATH = os.path.expanduser("~/.blackroad-personal/time_tracker.db")

@dataclass
class TimeEntry:
    id: int
    project: str
    task: str
    description: str
    start_time: str
    end_time: str
    duration_min: float
    tags: List[str]
    billable: bool

@dataclass
class Project:
    name: str
    client: str
    hourly_rate: float
    budget_hours: float
    color: str

def get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            name         TEXT PRIMARY KEY,
            client       TEXT NOT NULL DEFAULT '',
            hourly_rate  REAL NOT NULL DEFAULT 0,
            budget_hours REAL NOT NULL DEFAULT 0,
            color        TEXT NOT NULL DEFAULT '#2979FF'
        );
        CREATE TABLE IF NOT EXISTS entries (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            project      TEXT NOT NULL DEFAULT '',
            task         TEXT NOT NULL DEFAULT '',
            description  TEXT NOT NULL DEFAULT '',
            start_time   TEXT NOT NULL,
            end_time     TEXT NOT NULL DEFAULT '',
            duration_min REAL NOT NULL DEFAULT 0,
            tags_json    TEXT NOT NULL DEFAULT '[]',
            billable     INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS active_timer (
            id          INTEGER PRIMARY KEY CHECK(id=1),
            project     TEXT NOT NULL,
            task        TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            start_time  TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn

def parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try: return datetime.strptime(s, fmt)
        except ValueError: pass
    raise ValueError(f"Cannot parse datetime: {s}")

def duration_str(minutes: float) -> str:
    h = int(minutes // 60); m = int(minutes % 60)
    return f"{h}h {m:02d}m"

def cmd_start(args):
    db = get_db()
    existing = db.execute("SELECT * FROM active_timer WHERE id=1").fetchone()
    if existing:
        warn(f"Timer already running for [{existing['project']}] {existing['task']}")
        warn("Run `stop` first."); return
    now = datetime.now().isoformat(timespec="seconds")
    db.execute("INSERT OR REPLACE INTO active_timer(id,project,task,description,start_time) VALUES(1,?,?,?,?)",
               (args.project, args.task, args.description or "", now))
    db.commit()
    ok(f"Timer started: [{args.project}] {args.task}  @ {now}")

def cmd_stop(args):
    db  = get_db()
    row = db.execute("SELECT * FROM active_timer WHERE id=1").fetchone()
    if not row:
        warn("No active timer"); return
    end      = datetime.now()
    start    = parse_dt(row["start_time"])
    duration = (end - start).total_seconds() / 60
    tags     = [t.strip() for t in args.tags.split(",")] if args.tags else []
    db.execute("""
        INSERT INTO entries(project,task,description,start_time,end_time,duration_min,tags_json,billable)
        VALUES(?,?,?,?,?,?,?,?)
    """, (row["project"], row["task"], row["description"],
          row["start_time"], end.isoformat(timespec="seconds"),
          duration, json.dumps(tags), 1 if args.billable else 0))
    db.execute("DELETE FROM active_timer WHERE id=1")
    db.commit()
    ok(f"Stopped: [{row['project']}] {row['task']}  duration={duration_str(duration)}")

def cmd_log(args):
    db    = get_db()
    start = parse_dt(args.start)
    end   = parse_dt(args.end)
    dur   = (end - start).total_seconds() / 60
    tags  = [t.strip() for t in args.tags.split(",")] if args.tags else []
    db.execute("""
        INSERT INTO entries(project,task,description,start_time,end_time,duration_min,tags_json,billable)
        VALUES(?,?,?,?,?,?,?,?)
    """, (args.project, args.task, args.description or "",
          start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"),
          dur, json.dumps(tags), 1 if args.billable else 0))
    db.commit()
    ok(f"Logged {duration_str(dur)} for [{args.project}] {args.task}")

def cmd_today(args):
    db    = get_db()
    today = date.today().isoformat()
    rows  = db.execute(
        "SELECT * FROM entries WHERE start_time LIKE ? ORDER BY start_time", (f"{today}%",)
    ).fetchall()
    active = db.execute("SELECT * FROM active_timer WHERE id=1").fetchone()
    total  = sum(r["duration_min"] for r in rows)
    print(f"\n{BOLD}Today's log  {today}{NC}")
    if active:
        elapsed = (datetime.now() - parse_dt(active["start_time"])).total_seconds() / 60
        print(f"  {YELLOW}● RUNNING{NC} [{active['project']}] {active['task']}  +{duration_str(elapsed)}")
    if not rows:
        info("No completed entries today"); return
    for r in rows:
        tags = ", ".join(json.loads(r["tags_json"]))
        bill = f" {GREEN}$${NC}" if r["billable"] else ""
        print(f"  {CYAN}{r['project']:<15}{NC} {r['task']:<20} {duration_str(r['duration_min'])}{bill}")
        if tags: print(f"  {'':15}   {tags}")
    print(f"\n  {BOLD}Total: {duration_str(total)}{NC}\n")

def cmd_weekly(args):
    db    = get_db()
    today = date.today()
    start = today - timedelta(days=today.weekday())
    rows  = db.execute(
        "SELECT project, SUM(duration_min) as mins FROM entries "
        "WHERE start_time >= ? GROUP BY project ORDER BY mins DESC", (start.isoformat(),)
    ).fetchall()
    total = sum(r["mins"] for r in rows)
    print(f"\n{BOLD}Weekly report  {start} → {today}{NC}")
    print(f"  {'PROJECT':<20} {'HOURS':>8}  BAR")
    print("  " + "─" * 50)
    for r in rows:
        bar = "█" * int(r["mins"] / 60)
        print(f"  {CYAN}{r['project']:<20}{NC} {r['mins']/60:>7.1f}h  {bar}")
    print(f"  {'TOTAL':<20} {total/60:>7.1f}h\n")

def cmd_project_stats(args):
    db  = get_db()
    pr  = db.execute("SELECT * FROM projects WHERE name=?", (args.project,)).fetchone()
    rows = db.execute(
        "SELECT * FROM entries WHERE project=? ORDER BY start_time DESC LIMIT 50", (args.project,)
    ).fetchall()
    total      = sum(r["duration_min"] for r in rows) / 60
    billable   = sum(r["duration_min"] for r in rows if r["billable"]) / 60
    rate       = pr["hourly_rate"] if pr else 0
    budget     = pr["budget_hours"] if pr else 0
    print(f"\n{BOLD}Project: {args.project}{NC}")
    if pr:
        print(f"  Client: {pr['client']}  Rate: ${rate}/hr  Budget: {budget}h")
    print(f"  Total hrs  : {total:.1f}h")
    print(f"  Billable   : {billable:.1f}h  (${billable*rate:.2f})")
    if budget:
        pct = total / budget * 100
        bar = "█" * int(pct / 5)
        print(f"  Budget     : {bar} {pct:.0f}%  ({total:.1f}/{budget}h)")

def cmd_billable(args):
    db    = get_db()
    start = args.start or (date.today().replace(day=1)).isoformat()
    end   = args.end   or date.today().isoformat()
    rows  = db.execute("""
        SELECT project, SUM(duration_min) as mins FROM entries
        WHERE billable=1 AND start_time BETWEEN ? AND ?
        GROUP BY project
    """, (start, end)).fetchall()
    total_min = sum(r["mins"] for r in rows)
    print(f"\n{BOLD}Billable report  {start} → {end}{NC}")
    for r in rows:
        pr   = db.execute("SELECT hourly_rate FROM projects WHERE name=?", (r["project"],)).fetchone()
        rate = pr["hourly_rate"] if pr else 0
        amt  = r["mins"] / 60 * rate
        print(f"  {CYAN}{r['project']:<20}{NC}  {r['mins']/60:>6.1f}h  ${amt:>8.2f}")
    print(f"  {'TOTAL':<20}  {total_min/60:>6.1f}h")

def cmd_export_csv(args):
    db    = get_db()
    month = args.month or date.today().strftime("%Y-%m")
    rows  = db.execute(
        "SELECT * FROM entries WHERE start_time LIKE ? ORDER BY start_time", (f"{month}%",)
    ).fetchall()
    fname = f"time_{month}.csv"
    with open(fname, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id","project","task","description","start_time","end_time","duration_min","billable","tags"])
        for r in rows:
            w.writerow([r["id"],r["project"],r["task"],r["description"],
                        r["start_time"],r["end_time"],round(r["duration_min"],2),
                        r["billable"],",".join(json.loads(r["tags_json"]))])
    ok(f"Exported {len(rows)} entries to {fname}")

def cmd_focus_streaks(args):
    db   = get_db()
    rows = db.execute(
        "SELECT DISTINCT date(start_time) as d FROM entries ORDER BY d DESC"
    ).fetchall()
    if not rows:
        info("No entries"); return
    dates  = [date.fromisoformat(r["d"]) for r in rows]
    streak = 1
    for i in range(len(dates)-1):
        if (dates[i] - dates[i+1]).days == 1: streak += 1
        else: break
    ok(f"Focus streak: {streak} consecutive day(s)")
    print(f"  Total logged days: {len(dates)}")

def cmd_project_create(args):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO projects(name,client,hourly_rate,budget_hours,color) VALUES(?,?,?,?,?)",
               (args.name, args.client or "", args.rate or 0, args.budget or 0, args.color or "#2979FF"))
    db.commit()
    ok(f"Project \"{args.name}\" saved")

def cmd_status(args):
    db  = get_db()
    row = db.execute("SELECT * FROM active_timer WHERE id=1").fetchone()
    if not row:
        info("No active timer"); return
    elapsed = (datetime.now() - parse_dt(row["start_time"])).total_seconds() / 60
    print(f"\n{YELLOW}● RUNNING{NC}  [{row['project']}] {row['task']}")
    print(f"  Elapsed: {duration_str(elapsed)}")
    print(f"  Since  : {row['start_time']}\n")

def main():
    parser = argparse.ArgumentParser(prog="br-time", description="BlackRoad Time Tracker")
    sub    = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start"); p.add_argument("project"); p.add_argument("task")
    p.add_argument("--description","-d",default=""); p.set_defaults(func=cmd_start)

    p = sub.add_parser("stop"); p.add_argument("--tags",default="")
    p.add_argument("--billable","-b",action="store_true"); p.set_defaults(func=cmd_stop)

    p = sub.add_parser("log"); p.add_argument("project"); p.add_argument("task")
    p.add_argument("--start",required=True); p.add_argument("--end",required=True)
    p.add_argument("--description",default=""); p.add_argument("--tags",default="")
    p.add_argument("--billable","-b",action="store_true"); p.set_defaults(func=cmd_log)

    sub.add_parser("today").set_defaults(func=cmd_today)
    sub.add_parser("weekly").set_defaults(func=cmd_weekly)

    p = sub.add_parser("project-stats"); p.add_argument("project"); p.set_defaults(func=cmd_project_stats)

    p = sub.add_parser("billable"); p.add_argument("--start",default=None)
    p.add_argument("--end",default=None); p.set_defaults(func=cmd_billable)

    p = sub.add_parser("export-csv"); p.add_argument("--month",default=None); p.set_defaults(func=cmd_export_csv)
    sub.add_parser("focus-streaks").set_defaults(func=cmd_focus_streaks)
    sub.add_parser("status").set_defaults(func=cmd_status)

    p = sub.add_parser("project-create"); p.add_argument("name")
    p.add_argument("--client",default=""); p.add_argument("--rate",type=float,default=0)
    p.add_argument("--budget",type=float,default=0); p.add_argument("--color",default="#2979FF")
    p.set_defaults(func=cmd_project_create)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()

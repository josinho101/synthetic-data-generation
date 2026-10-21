"""SD folders (one per human): numbering, sd_info.json, and the timeline.txt writer.

No third-party imports: isaac/run_exam.py uses this module inside Isaac Sim's Python as well.

    output/sdg/run-<YYYYmmdd-HHMMSS>/SD.00001/
    ├── sd_info.json          human, room(s), exams, status
    └── CHEST/timeline.txt    (CHEST/<room id>/timeline.txt when more than one room)
"""

import datetime
import json
import re
from pathlib import Path


def create_run_dir(output_root, fmt: str = "run-%Y%m%d-%H%M%S") -> Path:
    """New run folder <output_root>/run-<timestamp> (a -2, -3, ... suffix if that second is taken)."""
    root = Path(output_root)
    base = datetime.datetime.now().strftime(fmt)
    run_dir, n = root / base, 1
    while run_dir.exists():
        n += 1
        run_dir = root / f"{base}-{n}"
    run_dir.mkdir(parents=True)
    return run_dir


def next_sd_numbers(output_root, count: int, fmt: str = "SD.{:05d}") -> list:
    """`count` unused SD names after the highest existing number in output_root (a run folder: starts at 1)."""
    prefix = fmt.split("{")[0]
    pattern = re.compile(re.escape(prefix) + r"(\d+)$")
    root = Path(output_root)
    used = [int(m.group(1)) for p in (root.iterdir() if root.exists() else []) if (m := pattern.match(p.name))]
    start = max(used, default=0) + 1
    return [fmt.format(start + i) for i in range(count)]


def timeline_path(sd_dir, exam: str, room_id: str, multi_room: bool) -> Path:
    folder = Path(sd_dir) / exam / (room_id if multi_room else "")
    return folder / "timeline.txt"


def write_json(path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="milliseconds")


class Timeline:
    """Append-only timeline of one visit: `<wall-clock ISO>  t=<sim seconds>s  <event>` per line."""

    def __init__(self, path, header: dict):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w", encoding="utf-8")
        for key, value in header.items():
            self._fh.write(f"# {key}: {value}\n")
        self._fh.flush()

    def event(self, sim_time_s: float, text: str) -> str:
        line = f"{now_iso()}  t={sim_time_s:8.2f}s  {text}"
        self._fh.write(line + "\n")
        self._fh.flush()
        return line

    def close(self, status: str = "ok") -> None:
        if not self._fh.closed:
            self._fh.write(f"# status: {status}\n")
            self._fh.close()

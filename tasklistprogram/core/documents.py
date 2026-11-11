import os
from pathlib import Path
from datetime import datetime, date
import re
import random
import subprocess
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
# Honor the same data-dir override as core.model (see TINYTASKLIST_DATA_DIR).
_ENV_DATA_DIR = os.environ.get("TINYTASKLIST_DATA_DIR")
DATA_DIR = Path(_ENV_DATA_DIR) if _ENV_DATA_DIR else (ROOT_DIR / "data")
TASKS_DIR = DATA_DIR / "task_documents"
JOURNALS_DIR = DATA_DIR / "journals"

TASK_DIVIDER = "\n--- Displayed notes ↑ | Private notes ↓ ---\n"
JOURNAL_DIVIDER = "\n---\n"

def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\n\r\t]+', "_", value or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or fallback

def task_doc_path(task: dict) -> Path:
    group = _safe_name(task.get("group", "").strip(), "Ungrouped")
    title = _safe_name(task.get("title", "").strip(), f"task-{task.get('id', 'unknown')}")
    filename = f"{title}-{task.get('id', 'unknown')}.md"
    return TASKS_DIR / group / filename

def _split_sections(content: str, divider: str) -> tuple[str, str]:
    if divider in content:
        top, bottom = content.split(divider, 1)
        return top.strip(), bottom.strip()
    return content.strip(), ""

def _write_sections(path: Path, top: str, bottom: str, divider: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = f"{top.strip()}{divider}{bottom.strip()}\n"
    path.write_text(body, encoding="utf-8")

def sync_task_notes(task: dict) -> Path:
    """Write task notes to the document file, preserving the bottom section."""
    path = task_doc_path(task)
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    _, bottom = _split_sections(existing, TASK_DIVIDER)
    top = task.get("notes", "").strip()
    _write_sections(path, top, bottom, TASK_DIVIDER)
    task["doc_path"] = str(path)
    return path

def read_task_notes_from_file(task: dict) -> bool:
    """Read display notes from the document file and update the task.
    Returns True if notes were updated, False otherwise."""
    path = task_doc_path(task)
    if not path.exists():
        return False
    
    existing = path.read_text(encoding="utf-8")
    top, bottom = _split_sections(existing, TASK_DIVIDER)
    
    # Only update if the file has content and differs from current notes
    if top.strip():
        current_notes = task.get("notes", "").strip()
        if top.strip() != current_notes:
            task["notes"] = top.strip()
            return True
    return False

def move_task_document_if_needed(task: dict) -> Path:
    desired = task_doc_path(task)
    current = Path(task.get("doc_path")) if task.get("doc_path") else None
    if current and current.exists() and current != desired:
        desired.parent.mkdir(parents=True, exist_ok=True)
        current.replace(desired)
    task["doc_path"] = str(desired)
    return desired

def open_document(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
        return
    subprocess.run(["xdg-open", str(path)], check=False)

def open_directory(path: Path) -> None:
    """Open a directory in the system file explorer."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
        return
    subprocess.run(["xdg-open", str(path)], check=False)

def _journal_path(entry_date: date) -> Path:
    return JOURNALS_DIR / f"{entry_date.year:04d}" / f"{entry_date.month:02d}" / f"{entry_date:%Y-%m-%d}.md"

def _ensure_journal(entry_date: date) -> Path:
    path = _journal_path(entry_date)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_sections(path, "", "", JOURNAL_DIVIDER)
    return path

def ensure_journal_path(entry_date: date | None = None) -> Path:
    entry_date = entry_date or date.today()
    return _ensure_journal(entry_date)

def append_journal_manual(entry: str, entry_time: datetime | None = None) -> Path:
    entry_time = entry_time or datetime.now()
    path = _ensure_journal(entry_time.date())
    content = path.read_text(encoding="utf-8")
    top, bottom = _split_sections(content, JOURNAL_DIVIDER)
    timestamp = entry_time.strftime("%H:%M")
    entry_text = entry.strip()
    if entry_text:
        line = f"- {timestamp} {entry_text}"
        top = f"{top}\n{line}".strip()
    _write_sections(path, top, bottom, JOURNAL_DIVIDER)
    return path

def append_journal_task(title: str, entry_time: datetime | None = None) -> Path:
    entry_time = entry_time or datetime.now()
    path = _ensure_journal(entry_time.date())
    content = path.read_text(encoding="utf-8")
    top, bottom = _split_sections(content, JOURNAL_DIVIDER)
    timestamp = entry_time.strftime("%H:%M")
    safe_title = title.strip() or "Task completed"
    header = "## Completed Tasks"
    line = f"- {timestamp} Completed: {safe_title}"
    if not bottom:
        bottom = header
    elif not bottom.lstrip().startswith(header):
        bottom = f"{header}\n{bottom}".strip()
    bottom = f"{bottom}\n{line}".strip()
    _write_sections(path, top, bottom, JOURNAL_DIVIDER)
    return path

def get_mantras_file_path() -> Path:
    """Get the path to the mantras file, creating it if it doesn't exist."""
    mantras_file = DATA_DIR / "mantras.md"
    if not mantras_file.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Initialize with default mantras
        default_content = """# Your Personal Mantras

<!-- Instructions:
- Add one mantra per line below
- Empty lines are ignored
- Lines starting with # or <!-- are comments and will be ignored
- Edit this file to add, remove, or modify mantras
-->

Protect your sleep.
Keep it simple and start small.
Breathe, then act.
Progress over perfection.
"""
        mantras_file.write_text(default_content, encoding="utf-8")
    return mantras_file

def load_mantras_from_file() -> list[str]:
    """Load mantras from the mantras.md file.
    Returns a list of non-empty, non-comment lines."""
    path = get_mantras_file_path()
    content = path.read_text(encoding="utf-8")
    mantras = []
    in_html_comment = False
    
    for line in content.splitlines():
        stripped = line.strip()
        
        # Handle HTML comment blocks
        if '<!--' in stripped:
            in_html_comment = True
        if '-->' in stripped:
            in_html_comment = False
            continue
        if in_html_comment:
            continue
            
        # Skip empty lines and markdown comments
        if stripped and not stripped.startswith('#'):
            mantras.append(stripped)

    return mantras

def pick_mantra_of_day(today: date | None = None) -> str:
    """Deterministic 'mantra of the day' based on the date's ordinal."""
    mantras = load_mantras_from_file()
    if not mantras:
        return ""
    today = today or date.today()
    return mantras[today.toordinal() % len(mantras)]

def pick_random_mantra(last: str | None = None) -> str:
    """A random mantra, avoiding an immediate repeat of ``last`` when possible."""
    mantras = load_mantras_from_file()
    if not mantras:
        return ""
    if len(mantras) == 1:
        return mantras[0]
    available = [m for m in mantras if m != last] or mantras
    return random.choice(available)

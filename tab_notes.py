#!/usr/bin/env python3
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote


def session_directory():
    socket = str(Path(os.environ["HERDR_SOCKET_PATH"]).resolve())
    session = hashlib.sha256(socket.encode()).hexdigest()[:16]
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return (state / "herdr/tab_notes" / session).resolve()


def pane_note(pane_id):
    return session_directory() / "panes" / quote(pane_id, safe="")


def tab_note(tab_id):
    return session_directory() / "tabs" / (quote(tab_id, safe="") + ".md")


def herdr(*args):
    result = subprocess.run(
        [os.environ.get("HERDR_BIN_PATH", "herdr"), *args],
        check=True, capture_output=True, text=True, timeout=10,
    )
    return json.loads(result.stdout)["result"]


def remember_pane(pane_id, note):
    marker = pane_note(pane_id)
    marker.parent.mkdir(parents=True, exist_ok=True)
    if not marker.is_symlink():
        marker.symlink_to(Path("../tabs") / note.name)


def open_note():
    panes = herdr("pane", "list")["panes"]
    context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "{}"))
    pane_id = context.get("pane_id") or os.environ.get("HERDR_ACTIVE_PANE_ID")
    current = next(pane for pane in panes if pane["pane_id"] == pane_id) if pane_id else next(
        pane for pane in panes if pane.get("focused")
    )
    note = tab_note(current["tab_id"])
    note.parent.mkdir(parents=True, exist_ok=True)
    with note.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        panes = herdr("pane", "list")["panes"]
        for pane in panes:
            marker = pane_note(pane["pane_id"])
            if pane["tab_id"] == current["tab_id"] and marker.is_symlink() and marker.resolve() == note:
                herdr("pane", "zoom", pane["pane_id"], "--on")
                herdr("pane", "zoom", pane["pane_id"], "--off")
                return
        note.touch(exist_ok=True, mode=0o600)
        result = herdr(
            "pane", "split", current["pane_id"], "--direction", "right", "--ratio", "0.75",
            "--cwd", current.get("foreground_cwd") or current["cwd"],
            "--env", "HERDR_VIM_NOTES=1", "--focus",
        )
        pane_id = result["pane"]["pane_id"]
        remember_pane(pane_id, note)
        herdr("pane", "rename", pane_id, "Vim notes")


def edit_note():
    marker = pane_note(os.environ["HERDR_PANE_ID"])
    note = marker.resolve() if marker.is_symlink() else tab_note(os.environ["HERDR_TAB_ID"])
    note.parent.mkdir(parents=True, exist_ok=True)
    note.touch(exist_ok=True, mode=0o600)
    remember_pane(os.environ["HERDR_PANE_ID"], note)
    os.environ.pop("HERDR_VIM_NOTES", None)
    os.environ["HERDR_VIM_NOTES_ACTIVE"] = "1"
    vim_arguments = ["vim", "-N", "-n", "--cmd", "set shortmess+=F",
                     "-S", str(Path(__file__).with_suffix(".vim")), "--", str(note)]
    os.execvp("vim", vim_arguments)


def main():
    os.umask(0o077)
    command = sys.argv[1]
    if command == "should-resume":
        if os.environ.get("HERDR_ENV") != "1" or not os.environ.get("HERDR_PANE_ID") or os.environ.get("HERDR_VIM_NOTES_ACTIVE") == "1":
            return 1
        return 0 if os.environ.get("HERDR_VIM_NOTES") == "1" or pane_note(os.environ["HERDR_PANE_ID"]).is_symlink() else 1
    if command == "open":
        open_note()
    elif command == "edit":
        edit_note()
    else:
        raise ValueError(f"Unknown notes command: {command}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

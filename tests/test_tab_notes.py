import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import struct
import subprocess
import tempfile
import termios
import time
import unittest


PROJECT = Path(__file__).resolve().parents[1]
HERDR_BINARY = os.environ.get("HERDR_TEST_BINARY") or shutil.which("herdr")
ZSH_BINARY = shutil.which("zsh")


@unittest.skipUnless(HERDR_BINARY and ZSH_BINARY and shutil.which("vim"),
                     "Install Herdr, Vim and Zsh (or set HERDR_TEST_BINARY)")
class TabNotesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="herdr-vim-notes-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        user_home = self.root / "home"
        user_home.mkdir()
        (user_home / ".zshenv").write_text("unsetopt GLOBAL_RCS\n")
        (user_home / ".zshrc").write_text(f"source {shlex.quote(str(PROJECT / 'tab_notes.zsh'))}\n")
        config = self.root / "config.toml"
        config.write_text((PROJECT / "example_config.toml").read_text()
                          + f'\n[terminal]\ndefault_shell = {json.dumps(ZSH_BINARY)}\nshell_mode = "non_login"\n')
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        self.environment = {key: value for key, value in os.environ.items() if not key.startswith("HERDR_")}
        self.environment.update(HOME=str(user_home), ZDOTDIR=str(user_home),
                                HERDR_CONFIG_PATH=str(config), XDG_CONFIG_HOME=str(self.root / "config"),
                                XDG_STATE_HOME=str(self.root / "state"), XDG_DATA_HOME=str(self.root / "data"),
                                XDG_RUNTIME_DIR=str(runtime), TERM="xterm-256color", SHELL=ZSH_BINARY)
        self.session = "vim_notes_" + str(os.getpid())
        self.process = None
        self.master = None
        self.addCleanup(self.stop_session)
        self.cli("plugin", "link", str(PROJECT))
        self.start_session()

    def cli(self, *args):
        result = subprocess.run([HERDR_BINARY, "--session", self.session, *args],
                                env=self.environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, (args, result.stdout, result.stderr))
        if args[:2] == ("pane", "read"):
            return result.stdout
        return json.loads(result.stdout)["result"]

    def drain(self, duration=0.1):
        deadline = time.monotonic() + duration
        while (remaining := deadline - time.monotonic()) > 0:
            if not select.select([self.master], [], [], remaining)[0]:
                break
            try:
                if not os.read(self.master, 65536):
                    break
            except OSError:
                break

    def wait_for_vim(self, pane_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.drain()
            processes = self.cli("pane", "process-info", "--pane", pane_id)["process_info"]["foreground_processes"]
            visible = self.cli("pane", "read", pane_id, "--source", "visible")
            if any(process.get("argv", [None])[0] == "vim" for process in processes) and "\n~\n" in visible:
                self.drain()
                return
        self.fail(f"Vim did not become ready in {pane_id}: {processes}; {visible}")

    def start_session(self):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 160, 0, 0))
        self.process = subprocess.Popen([HERDR_BINARY, "--session", self.session],
                                        stdin=slave, stdout=slave, stderr=slave, env=self.environment)
        os.close(slave)
        self.drain(1.0)

    def stop_session(self):
        if self.process is not None:
            subprocess.run([HERDR_BINARY, "session", "stop", self.session, "--json"],
                           env=self.environment, capture_output=True, timeout=10)
            if self.process.poll() is None:
                self.process.terminate()
            self.process.wait(timeout=5)
            os.close(self.master)
            self.process = None

    def notes_panes(self, expected_count):
        deadline = time.monotonic() + 5
        panes = []
        while time.monotonic() < deadline:
            self.drain()
            panes = [pane for pane in self.cli("pane", "list")["panes"] if pane.get("label") == "Vim notes"]
            if len(panes) == expected_count:
                return panes
        self.fail(f"Expected {expected_count} notes panes, got {panes}; logs: {self.cli('plugin', 'log', 'list', '--plugin', 'shcheglovnd.herdr-vim-notes')}")

    def test_shortcut_opens_a_quarter_width_note_per_tab_and_reuses_it_after_rename(self):
        first_tab = self.cli("tab", "list")["tabs"][0]
        os.write(self.master, b"\x01n")
        first_note = self.notes_panes(1)[0]
        layout = self.cli("pane", "layout", "--pane", first_note["pane_id"])["layout"]
        rect = next(pane["rect"] for pane in layout["panes"] if pane["pane_id"] == first_note["pane_id"])
        self.assertAlmostEqual(rect["width"] / layout["area"]["width"], 0.25, delta=0.02)
        self.assertEqual(rect["x"] + rect["width"], layout["area"]["x"] + layout["area"]["width"])
        self.cli("tab", "rename", first_tab["tab_id"], "Renamed tab")
        os.write(self.master, b"\x01n")
        self.assertEqual(self.notes_panes(1)[0]["pane_id"], first_note["pane_id"])
        self.cli("tab", "create", "--workspace", first_tab["workspace_id"], "--focus")
        self.drain(0.2)
        os.write(self.master, b"\x01n")
        notes = self.notes_panes(2)
        self.assertEqual(len({pane["tab_id"] for pane in notes}), 2)
        self.assertEqual(len(list((self.root / "state/herdr/tab_notes").glob("*/tabs/*.md"))), 2)

    def test_quitting_and_reopening_vim_reuses_the_tab_file(self):
        os.write(self.master, b"\x01n")
        first_pane = self.notes_panes(1)[0]
        self.wait_for_vim(first_pane["pane_id"])
        os.write(self.master, b"iKeep this note.\x1b")
        self.drain(0.2)
        os.write(self.master, b":q\r")
        self.notes_panes(0)
        self.drain(0.3)

        os.write(self.master, b"\x01n")
        second_pane = self.notes_panes(1)[0]

        self.assertNotEqual(second_pane["pane_id"], first_pane["pane_id"])
        notes = list((self.root / "state/herdr/tab_notes").glob("*/tabs/*.md"))
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].read_text(), "Keep this note.\n")

    def test_vim_autosaves_and_reopens_the_same_note_after_server_and_home_replacement(self):
        os.write(self.master, b"\x01n")
        note_pane = self.notes_panes(1)[0]
        self.wait_for_vim(note_pane["pane_id"])
        os.write(self.master, b"iSurvive the next restart.\x1b")
        note = next((self.root / "state/herdr/tab_notes").glob("*/tabs/*.md"))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and note.read_text() != "Survive the next restart.\n":
            self.drain()
        self.assertEqual(note.read_text(), "Survive the next restart.\n")
        self.stop_session()
        user_home = Path(self.environment["HOME"])
        shutil.rmtree(user_home)
        user_home.mkdir()
        (user_home / ".zshenv").write_text("unsetopt GLOBAL_RCS\n")
        (user_home / ".zshrc").write_text(f"source {shlex.quote(str(PROJECT / 'tab_notes.zsh'))}\n")

        self.start_session()
        restored = self.notes_panes(1)[0]
        self.assertEqual(restored["pane_id"], note_pane["pane_id"])
        self.assertEqual(restored["tab_id"], note_pane["tab_id"])
        layout = self.cli("pane", "layout", "--pane", restored["pane_id"])["layout"]
        rect = next(pane["rect"] for pane in layout["panes"] if pane["pane_id"] == restored["pane_id"])
        self.assertAlmostEqual(rect["width"] / layout["area"]["width"], 0.25, delta=0.02)
        self.wait_for_vim(restored["pane_id"])
        os.write(self.master, b"A Still editing.\x1b")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and note.read_text() != "Survive the next restart. Still editing.\n":
            self.drain()
        self.assertEqual(note.read_text(), "Survive the next restart. Still editing.\n")
        os.write(self.master, b"\x01n")
        self.assertEqual(self.notes_panes(1)[0]["pane_id"], note_pane["pane_id"])


if __name__ == "__main__":
    unittest.main()

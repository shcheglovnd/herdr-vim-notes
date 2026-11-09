# Herdr Vim Notes

One persistent Markdown note per [Herdr](https://herdr.dev/) tab, edited in Vim.
The shortcut opens a right-hand split with a 3:1 terminal-to-notes ratio, or
focuses the note if it is already open.

- Real Vim with your normal Vim configuration.
- Autosave while editing and when leaving the buffer.
- Separate notes for each tab and Herdr session; tab renames keep the same file.
- Automatic Vim reopening in restored notes panes through a small Zsh hook.
- Python standard library only, with no build step or background daemon.

## Install

Requires Herdr 0.9.5 or newer, Python 3.10 or newer, Vim, and Zsh on the machine
running the Herdr server. Install the plugin on that machine:

```sh
mkdir -p "$HOME/.local/share"
git clone https://github.com/shcheglovnd/herdr-vim-notes.git "$HOME/.local/share/herdr-vim-notes"
herdr plugin link "$HOME/.local/share/herdr-vim-notes" --enabled
```

Add this line to your `~/.zshrc` (or `$ZDOTDIR/.zshrc`):

```zsh
source "$HOME/.local/share/herdr-vim-notes/tab_notes.zsh"
```

Add the binding to your Herdr `config.toml`, replacing an existing binding for
`prefix+n` if necessary:

```toml
[[keys.command]]
key = "prefix+n"
type = "plugin_action"
command = "shcheglovnd.herdr-vim-notes.open-notes"
description = "Open tab notes in Vim"
```

Enable saved pane restoration if it is not already enabled:

```toml
[experimental]
pane_history = true
```

Reload Herdr's configuration. With `prefix = "ctrl+a"`, press **Ctrl+A, N** to
open notes. The [example configuration](example_config.toml) contains that setup.
For remote attachments, install the plugin and shell hook on the server, and
configure the shortcut on the client that supplies your keybindings.

## Use

Press the shortcut again to focus an existing note. Use `:q` to close Vim;
opening notes later returns to the same file. Edits are saved automatically, so
use Vim's undo commands to undo changes already written to disk.

The split reserves 25% of the selected pane's width for notes. Each tab gets one
note even when the tab contains multiple terminal panes.

## Storage and restart recovery

Notes live under `${XDG_STATE_HOME:-$HOME/.local/state}/herdr/tab_notes/` as ordinary
Markdown files. Each session has its own directory, with files in `tabs/` named
using the URL-encoded public tab ID. Persistent symlinks in `panes/` associate a
notes pane with its file. Closing a tab leaves its note file on disk.

Herdr restores the pane layout after a saved-session restart. The Zsh startup
hook recognizes a notes pane and replaces its shell with Vim editing the same
file. It leaves other panes as ordinary shells. Keep this checkout, the shell
startup line, Herdr's saved sessions, and the state directory on persistent
storage when using containers with an ephemeral home directory.

## Development

Run the integration tests with Herdr, Vim, and Zsh installed:

```sh
python3 -m unittest discover -s tests -v
```

Set `HERDR_TEST_BINARY` to test a specific Herdr executable. Tests run real Vim
and Herdr clients in isolated pseudo-terminals and disposable named sessions.
They cover per-tab files, split width, tab renaming, repeated opens, autosave,
quit/reopen, and server restart with home-directory replacement.

## License

[MIT](LICENSE). Development assisted by OpenAI Codex.

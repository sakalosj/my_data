# my_data

Personal OS configuration: linked dotfiles + backup/restore (mac & linux).

```
dotfiles/common   symlinked on every OS (.aliases, .gitconfig, .vimrc, ...)
dotfiles/mac      symlinked on mac (.zshrc, .zprofile); iterm2/ = iTerm2 prefs folder
dotfiles/linux    symlinked on linux (.bashrc); root/ = blocks for /etc (link --root)
dotfiles/remote   copied to remote hosts by the `si` / `smi` aliases
backup/           copied by backup/restore (brew, vscode, keyboard, Shortcuts.app, guake)
```

`sync_env/sync_env.sh` installs `uv` if needed and runs `sync_env.py` (click CLI,
deps resolved by uv). After linking, the `se` alias points to it.

## Fresh machine

```
git clone <this repo> ~/my_data
~/my_data/sync_env/sync_env.sh link       # symlink dotfiles, iTerm2 prefs folder (quit iTerm2 first)
~/my_data/sync_env/sync_env.sh restore    # brew, vscode, keyboard shortcuts, ...
sudo true && se link --root               # linux only: /etc/inputrc, /etc/bash.bashrc
```

## Routine

```
se status                  # link state
se backup                  # system -> repo, then review `git diff` and commit
se restore --only vscode   # single module
se -n <command>            # dry run
```

Linked files are edited in place (changes show up in `git status`).
On `link` conflicts the local file is saved as `<file>.bak.<timestamp>` and you
choose to keep the repo version, take the local one, or merge in vimdiff.

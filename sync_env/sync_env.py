#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["click>=8"]
# ///
"""Link dotfiles into $HOME and back up / restore OS configuration.

Shell, git and vim dotfiles are symlinked (editing them edits the repo).
iTerm2 loads its preferences directly from a repo folder.
Everything else (brew, VS Code, keyboard shortcuts, ...) is copied by
`backup` (system -> repo) and `restore` (repo -> system).
"""

from __future__ import annotations

import datetime
import difflib
import filecmp
import json
import os
import plistlib
import random
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import click

REPO = Path(__file__).resolve().parent.parent
DOTFILES = REPO / "dotfiles"
BACKUP = REPO / "backup"
HOME = Path.home()
OS = {"darwin": "mac", "linux": "linux"}.get(sys.platform)
TS = datetime.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
DRY_RUN = False

# dotfiles/<group>/<repo name> -> ~/<home name>; "common" applies to every OS
LINKS: dict[str, list[tuple[str, str]]] = {
    "common": [
        (".aliases", ".aliases"),
        (".gitconfig", ".gitconfig"),
        (".gitignore_global", ".gitignore_global"),
        (".vimrc", ".vimrc"),
        (".gvimrc", ".gvimrc"),
        (".inputrc", ".inputrc"),
    ],
    "mac": [
        (".zshrc", ".zshrc"),
        (".zprofile", ".zprofile"),
    ],
    "linux": [
        (".bashrc", ".bashrc"),
    ],
}

# Linux: dotfiles/linux/root/<name> is inserted as a marked block into /etc file
ROOT_SNIPPETS = {"/etc/inputrc": "inputrc", "/etc/bash.bashrc": "bash.bashrc"}
BLOCK_BEGIN = "# >>> my_data >>>"
BLOCK_END = "# <<< my_data <<<"


# --------------------------------------------------------------------------- helpers


def rel(path: Path) -> str:
    path = Path(path)
    for base, prefix in ((REPO, ""), (HOME, "~/")):
        try:
            return prefix + str(path.relative_to(base))
        except ValueError:
            pass
    return str(path)


def act(msg: str) -> None:
    click.secho(("[dry-run] " if DRY_RUN else "") + msg, fg="cyan")


def warn(msg: str) -> None:
    click.secho(f"WARN: {msg}", fg="yellow", err=True)


def run(
    cmd: list[str],
    *,
    mutating: bool = True,
    capture: bool = False,
    check: bool = True,
    text: bool = True,
    **kw,
) -> subprocess.CompletedProcess | None:
    """Run a command. Mutating commands are only printed in dry-run mode."""
    if mutating:
        act("$ " + shlex.join(cmd))
        if DRY_RUN:
            return None
    return subprocess.run(cmd, check=check, capture_output=capture, text=text, **kw)


def output(cmd: list[str]) -> str:
    """Run a read-only command and return its stdout."""
    return run(cmd, mutating=False, capture=True).stdout


def app_running(name: str) -> bool:
    return (
        subprocess.run(
            ["pgrep", "-x", name], capture_output=True, check=False
        ).returncode
        == 0
    )


def bak_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.bak.{TS}")


def same_file(a: Path, b: Path) -> bool:
    return a.is_file() and b.is_file() and filecmp.cmp(a, b, shallow=False)


def tree_files(root: Path) -> set[Path]:
    return {
        p.relative_to(root)
        for p in root.rglob("*")
        if p.is_file() and p.name != ".DS_Store"
    }


def same_tree(a: Path, b: Path) -> bool:
    if not (a.is_dir() and b.is_dir()):
        return False
    files = tree_files(a)
    return files == tree_files(b) and all(
        filecmp.cmp(a / f, b / f, shallow=False) for f in files
    )


def write_text(path: Path, text: str) -> None:
    if path.is_file() and path.read_text() == text:
        return
    act(f"write {rel(path)}")
    if not DRY_RUN:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def copy_file(src: Path, dst: Path, keep_backup: bool = False) -> None:
    if not src.is_file() or same_file(src, dst):
        return
    act(f"copy {rel(src)} -> {rel(dst)}")
    if DRY_RUN:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if keep_backup and dst.exists():
        shutil.copy2(dst, bak_path(dst))
    shutil.copy2(src, dst)


def remove(path: Path) -> None:
    if not (path.exists() or path.is_symlink()):
        return
    act(f"remove {rel(path)}")
    if DRY_RUN:
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def mirror_file(src: Path, dst: Path) -> None:
    """Make dst identical to src (removed when src does not exist)."""
    if src.is_file():
        copy_file(src, dst)
    else:
        remove(dst)


def mirror_dir(src: Path, dst: Path) -> None:
    """Make directory dst identical to src (removed when src does not exist)."""
    if not src.is_dir():
        remove(dst)
        return
    if same_tree(src, dst):
        return
    act(f"sync {rel(src)}/ -> {rel(dst)}/")
    if DRY_RUN:
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".DS_Store"))


def merge_dir(src: Path, dst: Path) -> None:
    """Copy all files from src into dst, overwriting, never deleting."""
    if not src.is_dir():
        return
    for f in sorted(tree_files(src)):
        copy_file(src / f, dst / f)


def plist_from_defaults(domain: str) -> dict:
    data = run(
        ["defaults", "export", domain, "-"], mutating=False, capture=True, text=False
    ).stdout
    return plistlib.loads(data)


def plist_xml(data: dict) -> str:
    return plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=True).decode()


def defaults_read(domain: str, key: str) -> str | None:
    res = subprocess.run(
        ["defaults", "read", domain, key], capture_output=True, text=True, check=False
    )
    return res.stdout.strip() if res.returncode == 0 else None


# --------------------------------------------------------------------------- link


def iter_links() -> Iterator[tuple[Path, Path]]:
    for group in ("common", OS):
        for src, dst in LINKS.get(group, []):
            yield DOTFILES / group / src, HOME / dst


def link_state(src: Path, dst: Path) -> str:
    if dst.is_symlink():
        if dst.resolve() == src.resolve():
            return "linked" if src.exists() else "broken"
        return "foreign-link" if dst.exists() else "broken"
    if not dst.exists():
        return "missing"
    if not src.exists():
        return "not-in-repo"
    return "same" if same_file(src, dst) else "conflict"


def make_link(src: Path, dst: Path) -> None:
    act(f"link {rel(dst)} -> {rel(src)}")
    if DRY_RUN:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(src)


def show_diff(src: Path, local: Path) -> None:
    a = src.read_text(errors="replace").splitlines(keepends=True)
    b = local.read_text(errors="replace").splitlines(keepends=True)
    for line in difflib.unified_diff(a, b, f"repo  {rel(src)}", f"local {rel(local)}"):
        color = (
            "green" if line.startswith("+") else "red" if line.startswith("-") else None
        )
        click.secho(line.rstrip("\n"), fg=color)


def link_one(src: Path, dst: Path) -> None:
    if dst.is_symlink() and dst.resolve() == src.resolve() and src.exists():
        click.echo(f"ok   {rel(dst)}")
        return
    if dst.is_dir() and not dst.is_symlink():
        warn(f"{rel(dst)} is a directory, skipping")
        return

    local = dst if dst.exists() else None  # None for missing or broken symlink

    if not src.exists():
        if local is None:
            warn(f"{rel(src)} not in repo and {rel(dst)} not present, skipping")
            return
        # new local file -> move its content into the repo, then link
        act(f"adopt {rel(dst)} -> {rel(src)}")
        if not DRY_RUN:
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local, src)
        make_link(src, dst)
        return

    if local is None or same_file(src, local):
        make_link(src, dst)
        return

    click.secho(f"conflict: {rel(dst)} differs from {rel(src)}", fg="yellow", bold=True)
    show_diff(src, local)
    if DRY_RUN:
        act("would ask: keep [r]epo / take [l]ocal / [m]erge / [s]kip")
        return
    choice = click.prompt(
        "keep [r]epo, take [l]ocal, [m]erge in vimdiff, [s]kip",
        type=click.Choice(["r", "l", "m", "s"]),
        default="s",
    )
    if choice == "s":
        return
    bak = bak_path(dst)
    shutil.copy2(local, bak)
    click.echo(f"saved local copy to {rel(bak)}")
    if choice == "l":
        shutil.copy2(local, src)
    elif choice == "m":
        click.echo("edit the repo file (left), local copy is on the right")
        subprocess.run(["vimdiff", str(src), str(bak)], check=False)
    make_link(src, dst)


OMZ_DIR = HOME / ".oh-my-zsh"
OMZ_INSTALL = (
    "https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh"
)
OMZ_PLUGINS = {"zsh-vi-mode": "https://github.com/jeffreytse/zsh-vi-mode"}


def ensure_oh_my_zsh() -> None:
    if not OMZ_DIR.is_dir():
        run(
            [
                "sh",
                "-c",
                f'curl -fsSL "{OMZ_INSTALL}" | sh -s -- --unattended --keep-zshrc',
            ]
        )
    custom = Path(os.environ.get("ZSH_CUSTOM", OMZ_DIR / "custom"))
    for name, url in OMZ_PLUGINS.items():
        if not (custom / "plugins" / name).is_dir():
            run(["git", "clone", "--depth=1", url, str(custom / "plugins" / name)])


ITERM_APP = Path("/Applications/iTerm.app")
ITERM_DOMAIN = "com.googlecode.iterm2"
ITERM_DIR = DOTFILES / "mac" / "iterm2"


def iterm_state() -> str:
    if not ITERM_APP.exists():
        return "not-installed"
    folder = defaults_read(ITERM_DOMAIN, "PrefsCustomFolder")
    load = defaults_read(ITERM_DOMAIN, "LoadPrefsFromCustomFolder")
    if folder and Path(folder).expanduser() == ITERM_DIR and load == "1":
        return "linked"
    return "not-linked"


def iterm_link() -> None:
    state = iterm_state()
    if state == "not-installed":
        return
    if state == "linked":
        click.echo(f"ok   iTerm2 prefs -> {rel(ITERM_DIR)}")
        return
    if app_running("iTerm2"):
        warn(
            "iTerm2 is running; quit it and re-run `link` from another terminal "
            "to load its prefs from the repo"
        )
        return
    plist = ITERM_DIR / f"{ITERM_DOMAIN}.plist"
    if not plist.exists():
        # first time: seed the repo folder with the current prefs
        write_text(plist, plist_xml(plist_from_defaults(ITERM_DOMAIN)))
    run(
        [
            "defaults",
            "write",
            ITERM_DOMAIN,
            "PrefsCustomFolder",
            "-string",
            str(ITERM_DIR),
        ]
    )
    run(
        [
            "defaults",
            "write",
            ITERM_DOMAIN,
            "LoadPrefsFromCustomFolder",
            "-bool",
            "true",
        ]
    )
    # "Save changes: Automatically"
    run(
        [
            "defaults",
            "write",
            ITERM_DOMAIN,
            "NoSyncNeverRemindPrefsChangesLostForFile",
            "-bool",
            "true",
        ]
    )
    run(
        [
            "defaults",
            "write",
            ITERM_DOMAIN,
            "NoSyncNeverRemindPrefsChangesLostForFile_selection",
            "-int",
            "2",
        ]
    )


def replace_block(text: str, snippet: str) -> str:
    block = f"{BLOCK_BEGIN}\n{snippet.rstrip()}\n{BLOCK_END}\n"
    pattern = re.compile(
        rf"^{re.escape(BLOCK_BEGIN)}\n.*?^{re.escape(BLOCK_END)}\n?",
        re.DOTALL | re.MULTILINE,
    )
    if pattern.search(text):
        return pattern.sub(lambda _: block, text, count=1)
    return text + ("" if text.endswith("\n") or not text else "\n") + "\n" + block


def root_link() -> None:
    for target, name in ROOT_SNIPPETS.items():
        path = Path(target)
        current = path.read_text() if path.exists() else ""
        new = replace_block(current, (DOTFILES / "linux" / "root" / name).read_text())
        if new == current:
            click.echo(f"ok   {target}")
            continue
        if path.exists():
            run(["sudo", "cp", "-p", target, f"{target}.bak.{TS}"])
        act(f"update block in {target}")
        if not DRY_RUN:
            subprocess.run(
                ["sudo", "tee", target],
                input=new,
                text=True,
                stdout=subprocess.DEVNULL,
                check=True,
            )


# --------------------------------------------------------------------------- brew

BREWFILE = BACKUP / "mac" / "Brewfile"


def brew_backup() -> None:
    if not DRY_RUN:
        BREWFILE.parent.mkdir(parents=True, exist_ok=True)
    run(["brew", "bundle", "dump", f"--file={BREWFILE}", "--force", "--no-vscode"])


def brew_restore() -> None:
    run(["brew", "bundle", "install", f"--file={BREWFILE}"])


# --------------------------------------------------------------------------- vscode

VSC_BACKUP = BACKUP / "vscode"
VSC_FILES = ["settings.json", "tasks.json", "mcp.json", "chatLanguageModels.json"]
VSC_DIRS = ["snippets", "prompts"]
VSC_EXCLUDED_PROFILES = {"ansible"}


def vsc_user_dir() -> Path:
    if OS == "mac":
        return HOME / "Library" / "Application Support" / "Code" / "User"
    return HOME / ".config" / "Code" / "User"


def vsc_cli() -> str:
    found = shutil.which("code")
    mac_cli = Path(
        "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
    )
    if not found and OS == "mac" and mac_cli.exists():
        found = str(mac_cli)
    if not found:
        raise click.ClickException("VS Code `code` CLI not found")
    return found


def vsc_running() -> bool:
    return app_running("Code" if OS == "mac" else "code")


def vsc_storage() -> Path:
    return vsc_user_dir() / "globalStorage" / "storage.json"


def vsc_profiles() -> list[dict]:
    storage = vsc_storage()
    if not storage.exists():
        return []
    return json.loads(storage.read_text()).get("userDataProfiles", [])


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.-]", "_", name)


def vsc_list_extensions(profile: str | None) -> list[str]:
    cmd = [vsc_cli(), "--list-extensions"] + (["--profile", profile] if profile else [])
    return sorted(output(cmd).split(), key=str.lower)


def vsc_backup_scope(src: Path, dst: Path) -> None:
    for name in VSC_FILES:
        mirror_file(src / name, dst / name)
    mirror_file(src / "keybindings.json", dst / f"keybindings.{OS}.json")
    for name in VSC_DIRS:
        mirror_dir(src / name, dst / name)


def vsc_restore_scope(src: Path, dst: Path) -> None:
    for name in VSC_FILES:
        copy_file(src / name, dst / name, keep_backup=True)
    copy_file(
        src / f"keybindings.{OS}.json", dst / "keybindings.json", keep_backup=True
    )
    for name in VSC_DIRS:
        merge_dir(src / name, dst / name)


def vscode_backup() -> None:
    user = vsc_user_dir()
    vsc_backup_scope(user, VSC_BACKUP / "default")
    ext_lists = {"default": vsc_list_extensions(None)}

    profiles = [p for p in vsc_profiles() if p["name"] not in VSC_EXCLUDED_PROFILES]
    keep = set()
    for p in profiles:
        name = safe_name(p["name"])
        keep.add(name)
        vsc_backup_scope(
            user / "profiles" / p["location"], VSC_BACKUP / "profiles" / name
        )
        if not p.get("useDefaultFlags", {}).get("extensions"):
            ext_lists[name] = vsc_list_extensions(p["name"])
    for stale in (VSC_BACKUP / "profiles").glob("*"):
        if stale.name not in keep:
            remove(stale)

    write_text(
        VSC_BACKUP / "profiles.json",
        json.dumps(sorted(profiles, key=lambda p: p["name"]), indent=2) + "\n",
    )

    for stale in (VSC_BACKUP / "extensions").glob("*.txt"):
        if stale.stem not in ext_lists:
            remove(stale)
    for name, exts in ext_lists.items():
        write_text(VSC_BACKUP / "extensions" / f"{name}.txt", "\n".join(exts) + "\n")


def vsc_register_profiles(wanted: list[dict]) -> None:
    """Add missing profiles to storage.json (VS Code must be closed)."""
    storage = vsc_storage()
    data = json.loads(storage.read_text()) if storage.exists() else {}
    existing = data.get("userDataProfiles", [])
    names = {p["name"] for p in existing}
    missing = [p for p in wanted if p["name"] not in names]
    if not missing:
        return
    if vsc_running():
        warn(
            "VS Code is running; close it and re-run `restore --only vscode` from another "
            "terminal to create profiles: " + ", ".join(p["name"] for p in missing)
        )
        return
    used = {p["location"] for p in existing}
    for p in missing:
        p = dict(p)
        while p["location"] in used:
            p["location"] = format(random.getrandbits(32), "x")
        used.add(p["location"])
        existing.append(p)
    data["userDataProfiles"] = existing
    act(
        f"register profiles in {rel(storage)}: " + ", ".join(p["name"] for p in missing)
    )
    if not DRY_RUN:
        storage.parent.mkdir(parents=True, exist_ok=True)
        if storage.exists():
            shutil.copy2(storage, bak_path(storage))
        storage.write_text(json.dumps(data, indent=4))


def vsc_install_extensions(profile: str | None, wanted_file: Path) -> None:
    wanted = wanted_file.read_text().split()
    installed = {e.lower() for e in vsc_list_extensions(profile)}
    for ext in wanted:
        if ext.lower() not in installed:
            run(
                [vsc_cli(), "--install-extension", ext]
                + (["--profile", profile] if profile else [])
            )


def vscode_restore() -> None:
    user = vsc_user_dir()
    vsc_restore_scope(VSC_BACKUP / "default", user)

    profiles_file = VSC_BACKUP / "profiles.json"
    wanted = json.loads(profiles_file.read_text()) if profiles_file.exists() else []
    vsc_register_profiles(wanted)
    registered = {p["name"]: p for p in vsc_profiles()}
    for p in wanted:
        if p["name"] in registered:
            vsc_restore_scope(
                VSC_BACKUP / "profiles" / safe_name(p["name"]),
                user / "profiles" / registered[p["name"]]["location"],
            )

    ext_dir = VSC_BACKUP / "extensions"
    if (ext_dir / "default.txt").exists():
        vsc_install_extensions(None, ext_dir / "default.txt")
    for p in wanted:
        f = ext_dir / f"{safe_name(p['name'])}.txt"
        if p["name"] in registered and f.exists():
            vsc_install_extensions(p["name"], f)


# --------------------------------------------------------------------------- mac keyboard shortcuts

KEYS_DIR = BACKUP / "mac" / "keyboard"
HOTKEYS_DOMAIN = "com.apple.symbolichotkeys"
HOTKEYS_FILE = KEYS_DIR / "symbolichotkeys.plist"
APP_KEYS_FILE = KEYS_DIR / "app_shortcuts.json"
CUSTOM_MENU = ("com.apple.universalaccess", "com.apple.custommenu.apps")
ACTIVATE_SETTINGS = Path(
    "/System/Library/PrivateFrameworks/SystemAdministration.framework"
    "/Resources/activateSettings"
)


def custom_menu_apps() -> list[str]:
    try:
        return list(plist_from_defaults(CUSTOM_MENU[0]).get(CUSTOM_MENU[1], []))
    except subprocess.CalledProcessError:
        return []


def app_shortcut_domains() -> set[str]:
    domains = {"NSGlobalDomain", *custom_menu_apps()}
    for plist in (HOME / "Library" / "Preferences").glob("*.plist"):
        if plist.name == ".GlobalPreferences.plist":
            continue
        try:
            if b"NSUserKeyEquivalents" in plist.read_bytes():
                domains.add(plist.stem)
        except OSError:
            pass
    return domains


def mac_keys_backup() -> None:
    write_text(HOTKEYS_FILE, plist_xml(plist_from_defaults(HOTKEYS_DOMAIN)))
    shortcuts = {}
    for domain in sorted(app_shortcut_domains()):
        keys = plist_from_defaults(domain).get("NSUserKeyEquivalents")
        if keys:
            shortcuts[domain] = keys
    write_text(
        APP_KEYS_FILE,
        json.dumps(shortcuts, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def mac_keys_restore() -> None:
    if HOTKEYS_FILE.exists():
        run(["defaults", "import", HOTKEYS_DOMAIN, str(HOTKEYS_FILE)])
    if APP_KEYS_FILE.exists():
        listed = custom_menu_apps()
        for domain, keys in json.loads(APP_KEYS_FILE.read_text()).items():
            args = ["defaults", "write", domain, "NSUserKeyEquivalents", "-dict"]
            for title, shortcut in keys.items():
                args += [title, shortcut]
            run(args)
            if domain != "NSGlobalDomain" and domain not in listed:
                # makes the app show up in System Settings > Keyboard > App Shortcuts
                run(
                    ["defaults", "write", *CUSTOM_MENU, "-array-add", domain],
                    check=False,
                )
    if ACTIVATE_SETTINGS.exists():
        run([str(ACTIVATE_SETTINGS), "-u"], check=False)
    click.echo("log out / restart apps if shortcuts are not applied yet")


# --------------------------------------------------------------------------- Shortcuts.app

SC_DB = HOME / "Library" / "Shortcuts" / "Shortcuts.sqlite"
SC_BACKUP = BACKUP / "mac" / "shortcuts_app"


def shortcuts_app_backup() -> None:
    if not SC_DB.exists():
        warn(f"{rel(SC_DB)} not found")
        return
    names = sorted(output(["shortcuts", "list"]).splitlines(), key=str.lower)
    write_text(SC_BACKUP / "shortcuts_list.txt", "\n".join(names) + "\n")
    if DRY_RUN:
        act(f"snapshot {rel(SC_DB)} -> {rel(SC_BACKUP / SC_DB.name)}")
        return
    SC_BACKUP.mkdir(parents=True, exist_ok=True)
    target = SC_BACKUP / SC_DB.name
    tmp = target.with_name(target.name + ".tmp")
    tmp.unlink(missing_ok=True)
    src = sqlite3.connect(SC_DB.as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)  # consistent copy including WAL content
    finally:
        dst.close()
        src.close()
    if same_file(tmp, target):
        tmp.unlink()
    else:
        act(f"snapshot {rel(SC_DB)} -> {rel(target)}")
        os.replace(tmp, target)


def shortcuts_app_restore() -> None:
    snapshot = SC_BACKUP / SC_DB.name
    if not snapshot.exists():
        warn(f"{rel(snapshot)} not found")
        return
    if app_running("Shortcuts"):
        warn(
            "Shortcuts.app is running; quit it and re-run `restore --only shortcuts_app`"
        )
        return
    if not DRY_RUN and not click.confirm(
        "Replace the Shortcuts database? iCloud sync may duplicate or overwrite shortcuts",
        default=False,
    ):
        return
    for suffix in ("", "-wal", "-shm"):
        f = SC_DB.with_name(SC_DB.name + suffix)
        if f.exists():
            act(f"move {rel(f)} -> {rel(bak_path(f))}")
            if not DRY_RUN:
                f.rename(bak_path(f))
    copy_file(snapshot, SC_DB)


# --------------------------------------------------------------------------- guake (linux)

GUAKE_FILE = BACKUP / "linux" / "guake.conf"


def guake_backup() -> None:
    run(["guake", "--save-preferences", str(GUAKE_FILE)])


def guake_restore() -> None:
    run(["guake", "--restore-preferences", str(GUAKE_FILE)])


# --------------------------------------------------------------------------- modules


@dataclass
class Module:
    oses: tuple[str, ...]
    backup: Callable[[], None]
    restore: Callable[[], None]
    help: str


MODULES: dict[str, Module] = {
    "brew": Module(
        ("mac",), brew_backup, brew_restore, "Homebrew Brewfile (no VS Code entries)"
    ),
    "vscode": Module(
        ("mac", "linux"),
        vscode_backup,
        vscode_restore,
        "VS Code settings, keybindings, snippets, prompts, profiles, extensions",
    ),
    "mac_keys": Module(
        ("mac",),
        mac_keys_backup,
        mac_keys_restore,
        "System keyboard shortcuts and app menu shortcuts",
    ),
    "shortcuts_app": Module(
        ("mac",),
        shortcuts_app_backup,
        shortcuts_app_restore,
        "Shortcuts.app database (best effort)",
    ),
    "guake": Module(("linux",), guake_backup, guake_restore, "Guake preferences"),
}


def run_modules(only: tuple[str, ...], action: str) -> None:
    names = only or tuple(MODULES)
    failed = []
    for name in names:
        module = MODULES[name]
        if OS not in module.oses:
            if only:
                warn(f"{name} is not available on {OS}")
            continue
        click.secho(f"== {action} {name}", bold=True)
        try:
            getattr(module, action)()
        except (subprocess.CalledProcessError, OSError, click.ClickException) as exc:
            msg = (
                exc.format_message()
                if isinstance(exc, click.ClickException)
                else str(exc)
            )
            click.secho(f"FAILED {name}: {msg}", fg="red", err=True)
            failed.append(name)
    if failed:
        raise click.ClickException(f"{action} failed for: {', '.join(failed)}")


# --------------------------------------------------------------------------- cli

only_option = click.option(
    "--only",
    multiple=True,
    type=click.Choice(list(MODULES)),
    help="Limit to these modules (repeatable). "
    + "; ".join(f"{k}: {m.help}" for k, m in MODULES.items()),
)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-n", "--dry-run", is_flag=True, help="Only show what would be done.")
def cli(dry_run: bool) -> None:
    """Link dotfiles and back up / restore OS configuration."""
    global DRY_RUN
    DRY_RUN = dry_run
    if OS is None:
        raise click.ClickException(f"unsupported platform: {sys.platform}")


@cli.command()
@click.option(
    "--root", is_flag=True, help="Linux: also install snippets into /etc (sudo)."
)
def link(root: bool) -> None:
    """Symlink dotfiles into $HOME (and point iTerm2 to the repo on mac)."""
    if root and OS != "linux":
        raise click.ClickException("--root is only supported on linux")
    if OS == "mac":
        ensure_oh_my_zsh()
    for src, dst in iter_links():
        link_one(src, dst)
    if OS == "mac":
        iterm_link()
    if root:
        root_link()


@cli.command()
def status() -> None:
    """Show link state and available modules."""
    colors = {"linked": "green", "missing": "yellow", "same": "yellow"}
    click.secho(f"os: {OS}   repo: {REPO}", bold=True)
    for src, dst in iter_links():
        state = link_state(src, dst)
        click.echo(
            f"{click.style(f'{state:<13}', fg=colors.get(state, 'red'))}{rel(dst)}"
        )
    if OS == "mac":
        state = iterm_state()
        click.echo(
            f"{click.style(f'{state:<13}', fg=colors.get(state, 'yellow'))}iTerm2 prefs folder"
        )
        state = "ok" if OMZ_DIR.is_dir() else "missing"
        click.echo(
            f"{click.style(f'{state:<13}', fg='green' if state == 'ok' else 'red')}oh-my-zsh"
        )
    state = "ok" if shutil.which("uv") else "missing"
    click.echo(
        f"{click.style(f'{state:<13}', fg='green' if state == 'ok' else 'red')}uv"
    )
    click.secho("modules:", bold=True)
    for name, m in MODULES.items():
        if OS in m.oses:
            click.echo(f"  {name:<14}{m.help}")


@cli.command()
@only_option
def backup(only: tuple[str, ...]) -> None:
    """Copy configuration from the system into the repo."""
    run_modules(only, "backup")


@cli.command()
@only_option
def restore(only: tuple[str, ...]) -> None:
    """Copy configuration from the repo onto the system."""
    run_modules(only, "restore")


if __name__ == "__main__":
    cli()

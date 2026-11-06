#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["click>=8"]
# ///
"""Manage docker compose services from services/<name>/ locally or on a remote host.

Every services/<name>/ directory with a compose.yaml becomes a command group
(`svc <name> up|down|logs|...`). With `-H user@host` the command runs on the
remote host over ssh; `deploy` rsyncs the service directory there first.

Per-target secrets (certs, init output, ...) live in the gitignored
services/<name>/secrets/<local|host>/ directory.
"""

from __future__ import annotations

import functools
import ipaddress
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import click

SERVICES = Path(__file__).resolve().parent
REPO = SERVICES.parent
DRY_RUN = False
HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]*$")
REMOTE_DIR_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
CONTEXT = {"help_option_names": ["-h", "--help"]}


# --------------------------------------------------------------------------- helpers


def rel(path: Path) -> str:
    try:
        return str(Path(path).relative_to(REPO))
    except ValueError:
        return str(path)


def act(msg: str) -> None:
    click.secho(("[dry-run] " if DRY_RUN else "") + msg, fg="cyan", err=True)


def run(
    cmd: list[str],
    *,
    mutating: bool = True,
    capture: bool = False,
    check: bool = True,
    **kw,
) -> subprocess.CompletedProcess | None:
    """Run a command. Mutating commands are only printed in dry-run mode."""
    act("$ " + shlex.join(cmd))
    if mutating and DRY_RUN:
        return None
    return subprocess.run(cmd, check=check, capture_output=capture, text=True, **kw)


@dataclass(frozen=True)
class Target:
    host: str | None  # without user
    user: str | None
    remote_dir: str

    @property
    def name(self) -> str:
        """Key for per-target secrets (independent of the ssh user)."""
        return self.host or "local"

    @property
    def dest(self) -> str:
        """ssh / rsync destination."""
        return f"{self.user}@{self.host}" if self.user else self.host

    def path(self, svc: str) -> str:
        return posixpath.join(self.remote_dir, svc)

    def secrets(self, svc: str) -> Path:
        return SERVICES / svc / "secrets" / self.name


def ssh(host: str, remote_cmd: str, *, tty: bool = False) -> list[str]:
    return ["ssh", *(["-t"] if tty else []), "--", host, remote_cmd]


def target_options(f: Callable) -> Callable:
    """Add -H/--host, -u/--user and --remote-dir; pass a validated `target` kwarg."""

    @click.option(
        "-H",
        "--host",
        help="Remote host ([user@]host or ~/.ssh/config alias). Local docker if omitted.",
    )
    @click.option(
        "-u",
        "--user",
        envvar="SVC_SSH_USER",
        show_envvar=True,
        help="ssh user, e.g. root (user@ in --host wins). Default: ~/.ssh/config / current user.",
    )
    @click.option(
        "--remote-dir",
        default="services",
        show_default=True,
        help="Base dir on the remote host (relative paths are relative to remote $HOME).",
    )
    @functools.wraps(f)
    def wrapper(*args, host: str | None, user: str | None, remote_dir: str, **kw):
        if host is not None:
            if "@" in host:
                user, host = host.rsplit("@", 1)
            if not HOST_RE.match(host):
                raise click.BadParameter(f"invalid host {host!r}", param_hint="--host")
            if user and not USER_RE.match(user):
                raise click.BadParameter(f"invalid user {user!r}", param_hint="--user")
        if not REMOTE_DIR_RE.match(remote_dir) or ".." in remote_dir.split("/"):
            raise click.BadParameter(
                f"invalid remote dir {remote_dir!r}", param_hint="--remote-dir"
            )
        return f(*args, target=Target(host, user or None, remote_dir), **kw)

    return wrapper


# --------------------------------------------------------------------------- service hooks


@dataclass
class Hooks:
    """Service-specific behaviour plugged into the generic commands."""

    # extra env for local `docker compose` runs
    local_env: Callable[[Target], dict[str, str]] = lambda t: {}
    # validation before up/restart (deploy=False) and deploy (deploy=True)
    check: Callable[[Target, bool], None] = lambda t, deploy: None
    # extra (local dir, remote subdir) pairs rsynced on deploy
    sync: Callable[[Target], list[tuple[Path, str]]] = lambda t: []
    # called by deploy after `up -d` when files from `sync` changed
    reload: Callable[[Target], None] = lambda t: None
    # extra commands added to the service group
    commands: list[click.Command] = field(default_factory=list)


HOOKS: dict[str, Hooks] = {}


def hooks(svc: str) -> Hooks:
    return HOOKS.get(svc, Hooks())


def services() -> list[str]:
    return sorted(p.name for p in SERVICES.iterdir() if (p / "compose.yaml").is_file())


def compose(
    svc: str,
    target: Target,
    args: list[str],
    *,
    tty: bool = False,
    **kw,
) -> subprocess.CompletedProcess | None:
    """Run `docker compose <args>` for a service, locally or over ssh."""
    cmd = ["docker", "compose", *args]
    if target.host is None:
        env = {**os.environ, **hooks(svc).local_env(target)}
        return run(cmd, cwd=SERVICES / svc, env=env, **kw)
    remote = f"cd {shlex.quote(target.path(svc))} && {shlex.join(cmd)}"
    return run(ssh(target.dest, remote, tty=tty), **kw)


# --------------------------------------------------------------------------- generic commands


def make_group(svc: str) -> click.Group:
    @click.group(svc, context_settings=CONTEXT, help=f"Manage the {svc} service.")
    def group() -> None:
        pass

    @group.command()
    @target_options
    def up(target: Target) -> None:
        """Create and start containers (detached)."""
        hooks(svc).check(target, False)
        compose(svc, target, ["up", "-d"])

    @group.command()
    @click.option(
        "-v", "--volumes", is_flag=True, help="Also remove volumes (DATA LOSS)."
    )
    @target_options
    def down(target: Target, volumes: bool) -> None:
        """Stop and remove containers."""
        if volumes:
            click.confirm(
                f"Remove {svc} volumes on {target.name}? All data will be lost",
                abort=True,
            )
        compose(svc, target, ["down", *(["--volumes"] if volumes else [])])

    @group.command()
    @target_options
    def restart(target: Target) -> None:
        """Restart containers."""
        hooks(svc).check(target, False)
        compose(svc, target, ["restart"])

    @group.command()
    @target_options
    def ps(target: Target) -> None:
        """List containers."""
        compose(svc, target, ["ps"], mutating=False)

    @group.command()
    @target_options
    def pull(target: Target) -> None:
        """Pull images."""
        compose(svc, target, ["pull"])

    @group.command()
    @click.option("-f", "--follow", is_flag=True, help="Follow log output.")
    @click.option("--tail", default="100", show_default=True, help="Lines to show.")
    @target_options
    def logs(target: Target, follow: bool, tail: str) -> None:
        """Show container logs."""
        args = ["logs", "--tail", tail, *(["--follow"] if follow else [])]
        compose(svc, target, args, tty=follow, mutating=False)

    @group.command("exec", context_settings={"ignore_unknown_options": True})
    @click.option(
        "-s", "--service", default=svc, show_default=True, help="Compose service."
    )
    @click.argument("command", nargs=-1, required=True, type=click.UNPROCESSED)
    @target_options
    def exec_cmd(target: Target, service: str, command: tuple[str, ...]) -> None:
        """Run a command in a running container (use -- before the command)."""
        tty = sys.stdin.isatty()
        args = ["exec", *([] if tty else ["-T"]), service, *command]
        compose(svc, target, args, tty=tty)

    @group.command()
    @click.option(
        "-s", "--service", default=svc, show_default=True, help="Compose service."
    )
    @target_options
    def shell(target: Target, service: str) -> None:
        """Open a shell in a running container."""
        compose(svc, target, ["exec", service, "sh"], tty=True)

    @group.command()
    @click.option(
        "--pull/--no-pull", default=True, show_default=True, help="Pull images first."
    )
    @target_options
    def deploy(target: Target, pull: bool) -> None:
        """Rsync the service dir to --host and (re)start it there."""
        if target.host is None:
            raise click.UsageError("deploy requires -H/--host")
        h = hooks(svc)
        h.check(target, True)
        extra = h.sync(target)
        dest = f"{target.dest}:{target.path(svc)}/"
        run(ssh(target.dest, shlex.join(["mkdir", "-p", target.path(svc)])))
        excludes = ["secrets/", ".env", *(f"{sub}/" for _, sub in extra)]
        run(
            [
                "rsync",
                "-az",
                "--delete",
                *(f"--exclude={e}" for e in excludes),
                f"{SERVICES / svc}/",
                dest,
            ]
        )
        changed = False
        for src, sub in extra:
            res = run(
                [
                    "rsync",
                    "-az",
                    "--delete",
                    "--itemize-changes",
                    f"{src}/",
                    f"{dest}{sub}/",
                ],
                capture=True,
            )
            changed |= res is None or bool(res.stdout.strip())
        if pull:
            compose(svc, target, ["pull"])
        compose(svc, target, ["up", "-d", "--remove-orphans"])
        if changed:
            h.reload(target)
        compose(svc, target, ["ps"])

    for cmd in hooks(svc).commands:
        group.add_command(cmd)
    return group


# --------------------------------------------------------------------------- vault


VAULT_CMDS: list[click.Command] = []


def vault_tls(target: Target) -> Path:
    return target.secrets("vault") / "tls"


def vault_check(target: Target, deploy: bool) -> None:
    # remote up/restart use the tls dir synced by deploy
    if target.host is not None and not deploy:
        return
    if not (vault_tls(target) / "vault.key").is_file():
        host = f" -H {target.host}" if target.host else ""
        raise click.ClickException(
            f"no TLS cert in {rel(vault_tls(target))}; run: svc vault certs{host}"
        )


def vault_exec(
    target: Target, args: list[str], **kw
) -> subprocess.CompletedProcess | None:
    return compose("vault", target, ["exec", "-T", "vault", "vault", *args], **kw)


def vault_init_file(target: Target) -> Path:
    return target.secrets("vault") / "init.json"


def vault_command(f: Callable) -> click.Command:
    cmd = click.command(context_settings=CONTEXT)(target_options(f))
    VAULT_CMDS.append(cmd)
    return cmd


@click.option(
    "--san", multiple=True, help="Extra DNS name or IP for the cert (repeatable)."
)
@click.option("--days", default=825, show_default=True, help="Validity in days.")
@click.option("--force", is_flag=True, help="Overwrite an existing cert.")
@vault_command
def certs(target: Target, san: tuple[str, ...], days: int, force: bool) -> None:
    """Generate a self-signed TLS cert for the target."""
    tls = vault_tls(target)
    key, crt = tls / "vault.key", tls / "vault.crt"
    if key.exists() and not force:
        raise click.ClickException(f"{rel(key)} exists (use --force to overwrite)")

    names = ["localhost", "127.0.0.1"]
    if target.host:
        names.append(target.host)
    names += san
    alt = []
    for n in dict.fromkeys(names):
        try:
            alt.append(f"IP:{ipaddress.ip_address(n)}")
        except ValueError:
            if not re.fullmatch(r"[A-Za-z0-9*][A-Za-z0-9.-]*", n):
                raise click.BadParameter(f"invalid SAN {n!r}", param_hint="--san")
            alt.append(f"DNS:{n}")
    cn = target.host or "vault"
    conf = (
        "[req]\nprompt = no\ndistinguished_name = dn\nx509_extensions = v3\n"
        f"[dn]\nCN = {cn}\n"
        f"[v3]\nsubjectAltName = {','.join(alt)}\nextendedKeyUsage = serverAuth\n"
    )

    act(f"generate {rel(crt)} ({', '.join(alt)})")
    if DRY_RUN:
        return
    tls.mkdir(parents=True, exist_ok=True, mode=0o700)
    for d in (tls.parent, tls):
        d.chmod(0o700)
    with tempfile.NamedTemporaryFile("w", suffix=".cnf") as cf:
        cf.write(conf)
        cf.flush()
        old = os.umask(0o077)
        try:
            run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:3072",
                    "-sha256",
                    "-nodes",
                    "-days",
                    str(days),
                    "-config",
                    cf.name,
                    "-keyout",
                    str(key),
                    "-out",
                    str(crt),
                ],
                capture=True,
            )
        finally:
            os.umask(old)
    key.chmod(0o600)
    crt.chmod(0o644)
    click.echo(f"cert: {rel(crt)}  (clients: VAULT_CACERT / curl --cacert)")
    if target.host:
        click.echo(f"next: svc vault deploy -H {target.host}")


@click.option("--shares", default=5, show_default=True, help="Number of unseal keys.")
@click.option(
    "--threshold", default=3, show_default=True, help="Keys needed to unseal."
)
@vault_command
def init(target: Target, shares: int, threshold: int) -> None:
    """Initialize Vault; print and save unseal keys + root token."""
    out = vault_init_file(target)
    if out.exists():
        raise click.ClickException(f"{rel(out)} exists; vault already initialized?")
    res = vault_exec(
        target,
        [
            "operator",
            "init",
            "-format=json",
            f"-key-shares={shares}",
            f"-key-threshold={threshold}",
        ],
        capture=True,
    )
    if res is None:
        return
    data = json.loads(res.stdout)
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    out.parent.chmod(0o700)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")

    click.secho(
        "Vault initialized. Store these safely, they are shown only once:", fg="yellow"
    )
    for i, k in enumerate(data["unseal_keys_b64"], 1):
        click.echo(f"  unseal key {i}: {k}")
    click.echo(f"  root token:   {data['root_token']}")
    click.secho(f"saved to {rel(out)} (mode 600)", fg="green")
    host = f" -H {target.host}" if target.host else ""
    click.echo(f"next: svc vault unseal{host}")


@vault_command
def unseal(target: Target) -> None:
    """Unseal Vault with the keys saved by `init` (passed via stdin)."""
    src = vault_init_file(target)
    if not src.is_file():
        raise click.ClickException(f"{rel(src)} not found; run `svc vault init` first")
    data = json.loads(src.read_text())
    for key in data["unseal_keys_b64"][: data["unseal_threshold"]]:
        if vault_sealed(target) is False:
            break
        # key=- reads the key from stdin, keeping it out of argv / ps
        vault_exec(target, ["write", "sys/unseal", "key=-"], input=key, capture=True)
    if DRY_RUN:
        return
    if vault_sealed(target):
        raise click.ClickException("still sealed after threshold keys")
    click.secho("unsealed", fg="green")


def vault_sealed(target: Target) -> bool:
    res = vault_exec(
        target, ["status", "-format=json"], check=False, capture=True, mutating=False
    )
    if res.returncode not in (0, 2):  # 2 = sealed
        raise click.ClickException(f"vault status failed: {res.stderr.strip()}")
    state = json.loads(res.stdout)
    if state["sealed"]:
        click.echo(f"sealed, progress {state['progress']}/{state['t']}")
    return state["sealed"]


@vault_command
def status(target: Target) -> None:
    """Show Vault seal status."""
    res = vault_exec(target, ["status"], check=False, mutating=False)
    if res is not None and res.returncode not in (0, 2):  # 2 = sealed
        sys.exit(res.returncode)


def vault_reload(target: Target) -> None:
    # The entrypoint copies the cert into tmpfs only at container start; re-copy
    # it and SIGHUP vault so it reloads the listener without sealing.
    script = (
        "cp /vault/tls-src/vault.crt /vault/tls-src/vault.key /vault/tls/"
        " && chown -R vault:vault /vault/tls && chmod 0400 /vault/tls/vault.key"
        " && pkill -HUP -x vault"
    )
    compose("vault", target, ["exec", "-T", "-u", "root", "vault", "sh", "-ec", script])
    click.secho("TLS cert reloaded", fg="green")


@vault_command
def reload(target: Target) -> None:
    """Reload the TLS cert (after `certs --force`) without restart / reseal."""
    if target.host is not None:
        click.echo("note: remote uses the cert synced by the last `deploy`")
    vault_reload(target)


HOOKS["vault"] = Hooks(
    local_env=lambda t: {"VAULT_TLS_DIR": str(vault_tls(t))},
    check=vault_check,
    sync=lambda t: [(vault_tls(t), "tls")],
    reload=vault_reload,
    commands=VAULT_CMDS,
)


# --------------------------------------------------------------------------- cli


@click.group(context_settings=CONTEXT)
@click.option("-n", "--dry-run", is_flag=True, help="Only show what would be done.")
def cli(dry_run: bool) -> None:
    """Docker compose services: local or remote (ssh) operations and deploy."""
    global DRY_RUN
    DRY_RUN = dry_run


@cli.command("list")
def list_cmd() -> None:
    """List available services."""
    for svc in services():
        click.echo(svc)


for _svc in services():
    cli.add_command(make_group(_svc))


def main() -> None:
    try:
        cli(prog_name="svc")
    except subprocess.CalledProcessError as e:
        if e.stderr:
            click.echo(e.stderr, err=True, nl=False)
        click.secho(
            f"command failed ({e.returncode}): {shlex.join(e.cmd)}", fg="red", err=True
        )
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()

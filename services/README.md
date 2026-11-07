# services

One docker compose service per directory (`services/<name>/compose.yaml`),
managed by `svc` = [svc.sh](svc.sh) -> [svc.py](svc.py) (click CLI, deps resolved by uv).

| Service | Docs |
|---|---|
| vault | [vault/README.md](vault/README.md) |

## How it works

- Without `-H`, commands run local `docker compose` in `services/<name>/`.
- With `-H host`, the same command runs over ssh in `~/services/<name>/` on the host.
- `deploy` rsyncs `services/<name>/` to the host (skipping `secrets/` and `.env`),
  then runs `docker compose pull && up -d` there.
- Per-target secrets live in gitignored `services/<name>/secrets/<local|host>/`.
  They're keyed by host name only (not user), so always use the same `-H` name for a host.
- A remote `.env` next to `compose.yaml` is never overwritten by `deploy`; use it for
  host-specific overrides.
- The remote host needs Docker with the compose plugin already installed.
- `svc <name> -h` lists commands; `svc -n ...` is a dry run (prints commands only).

## ssh user

ssh connects as your current user, or whatever `~/.ssh/config` sets for the host.
To use a different user:

```sh
svc vault ps -H jsakalos-dev -u root        # flag
svc vault ps -H root@jsakalos-dev           # user@host (wins over -u)
export SVC_SSH_USER=root                    # default for this shell
```

Or set it permanently in `~/.ssh/config`:

```sh
cat >> ~/.ssh/config <<'EOF'

Host jsakalos-dev
    HostName 172.24.97.70
    User root
EOF
```

## Adding a service

1. Create `services/<name>/compose.yaml`; set `name: <name>` at the top.
2. `svc list` now shows it, and the generic commands work.
3. Optional: register service-specific behaviour in `svc.py` with `HOOKS["<name>"] = Hooks(...)`:
   - `local_env`: extra env for local compose runs
   - `check`: validation before up/restart/deploy
   - `sync`: extra local dirs to rsync on deploy (e.g. per-host secrets)
   - `reload`: called by deploy when those synced files changed
   - `commands`: extra click commands for the service group
4. Gitignore is already set up for `services/*/secrets/` and `services/*/.env`.

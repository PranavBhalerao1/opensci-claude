"""Compare this project's idle E2B sandbox workspace with the exported host copy (name + size),
then terminate ONLY that sandbox if every remote file is present on the host with the same size.
Authorized by the user ("Terminate after export")."""
import asyncio, os, sys
from pathlib import Path
from e2b import AsyncSandbox
from app.config import settings

SID = sys.argv[1] if len(sys.argv) > 1 else "idvr8s9zefod5k7lgo0fs"
PID = "6d8c3c93c209"
HOST = Path(__file__).resolve().parents[1] / "workspace_copy"
SKIP = (".venv", ".conda", ".home", ".tmp", "__pycache__", ".pytest_cache", ".sandbox.sb")

async def main():
    items = await AsyncSandbox.list(api_key=settings.e2b_api_key).next_items()
    mine = [s for s in items if s.sandbox_id == SID and (s.metadata or {}).get("project_id") == PID]
    if not mine:
        print("sandbox not found (already gone):", [(s.sandbox_id, s.metadata) for s in items])
        return
    sb = await AsyncSandbox.connect(SID, api_key=settings.e2b_api_key)
    prune = " -o ".join(f"-name {n}" for n in SKIP)
    r = await sb.commands.run(rf"cd /home/user/workspace && find . \( {prune} \) -prune -o -type f -printf '%p\t%s\n'", timeout=120)
    remote = {}
    for line in r.stdout.splitlines():
        p, s = line.rsplit("\t", 1); remote[p[2:]] = int(s)
    host = {str(p.relative_to(HOST)).replace(os.sep, "/"): p.stat().st_size for p in HOST.rglob("*") if p.is_file()}
    missing = [p for p in remote if p not in host]
    differ = [p for p in remote if p in host and host[p] != remote[p]]
    print(f"remote files {len(remote)} | host files {len(host)} | missing on host {len(missing)} | size differs {len(differ)} | host-only {len(set(host) - set(remote))}")
    for p in (missing + differ)[:20]: print("  !", p, remote[p], host.get(p))
    if missing:
        print("NOT terminating: host copy incomplete"); return
    # Files that differ: the host holds the newer (final) version, written by the host-side report stage.
    # Keep the sandbox's older copies too, as evidence, before terminating.
    stale = HOST.parent / "e2b_remote_stale_copies" / SID
    for p in differ:
        dest = stale / p; dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(bytes(await sb.files.read(f"/home/user/workspace/{p}", format="bytes")))
        print("  saved sandbox copy:", dest.relative_to(HOST.parent), dest.stat().st_size, "bytes")
    await sb.kill()
    left = [s.sandbox_id for s in await AsyncSandbox.list(api_key=settings.e2b_api_key).next_items()]
    print("terminated", SID, "| sandboxes now listed:", left)

asyncio.run(main())

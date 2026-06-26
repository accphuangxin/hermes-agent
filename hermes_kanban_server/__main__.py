"""
hermes-kanban-server — CLI entry point

Subcommands (mirrors hermes-agent-manager):
    run        Run in foreground (default when no subcommand given)
    start      Start as background service (launchd / systemd)
    stop       Stop the background service
    restart    Restart the background service
    status     Show service status
    install    Install as a persistent launchd / systemd service
    uninstall  Remove the service

Examples:
    hermes-kanban-server                          # foreground
    hermes-kanban-server run                      # foreground (explicit)
    hermes-kanban-server install --port 8650      # install + auto-start
    hermes-kanban-server start
    hermes-kanban-server stop
    hermes-kanban-server restart
    hermes-kanban-server status
    hermes-kanban-server uninstall
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

_SERVICE_LABEL  = "ai.hermes.kanban-server"
_SERVICE_NAME   = "hermes-kanban-server"   # systemd unit name
_DEFAULT_HOST   = os.getenv("KANBAN_SERVER_HOST", "0.0.0.0")
_DEFAULT_PORT   = int(os.getenv("KANBAN_SERVER_PORT", "8650"))
_DEFAULT_KEY    = os.getenv("KANBAN_SERVER_API_KEY", "")
_PID_FILE_NAME  = "kanban_server.pid"

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_macos() -> bool:
    return platform.system() == "Darwin"

def _is_linux() -> bool:
    return platform.system() == "Linux"

def _hermes_home() -> Path:
    try:
        # Must use get_default_hermes_root(), NOT get_hermes_home().
        # get_hermes_home() returns the active *profile* directory (e.g.
        # ~/.hermes/profiles/trader), which would anchor kanban.db inside
        # that profile and cause it to "disappear" when a different profile
        # is active. kanban is intentionally shared across profiles.
        from hermes_constants import get_default_hermes_root
        candidate = get_default_hermes_root()
        if not os.access(str(candidate), os.W_OK):
            candidate = Path.home() / ".hermes"
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except Exception:
        fallback = Path.home() / ".hermes"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

def _pid_file() -> Path:
    return _hermes_home() / _PID_FILE_NAME

def _log_dir() -> Path:
    d = _hermes_home() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _python_path() -> str:
    return sys.executable

def _exe_path() -> str:
    """Path to the hermes-kanban-server binary."""
    exe = shutil.which("hermes-kanban-server")
    if exe:
        return exe
    return f"{_python_path()} -m hermes_kanban_server"

def _read_pid() -> int | None:
    try:
        return int(_pid_file().read_text().strip())
    except Exception:
        return None

def _write_pid(pid: int) -> None:
    _pid_file().write_text(str(pid))

def _remove_pid() -> None:
    try:
        _pid_file().unlink(missing_ok=True)
    except Exception:
        pass

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False

def _is_running() -> tuple[bool, int | None]:
    pid = _read_pid()
    if pid and _pid_alive(pid):
        return True, pid
    _remove_pid()
    return False, None

# ── Foreground runner ─────────────────────────────────────────────────────────

async def _run_foreground(host: str, port: int, api_key: str) -> None:
    # Late import to avoid dependency errors when just checking --help
    try:
        from hermes_kanban_server.server import KanbanAPIServer
    except ImportError as e:
        print(f"Error: Missing dependencies. Install with: pip install aiohttp", file=sys.stderr)
        raise

    server = KanbanAPIServer(
        host=host,
        port=port,
        api_key=api_key or None,
    )

    stop_event = asyncio.Event()

    def _handle_signal(*_):
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except (NotImplementedError, OSError):
            pass

    _write_pid(os.getpid())
    try:
        await server.start()
        await stop_event.wait()
    finally:
        await server.stop()
        _remove_pid()

# ── Subcommand handlers ───────────────────────────────────────────────────────

def cmd_run(args: argparse.Namespace) -> None:
    """Run in foreground."""
    _setup_logging(args)
    try:
        asyncio.run(_run_foreground(args.host, args.port, args.api_key))
    except KeyboardInterrupt:
        print("\n👋 Kanban server stopped")

def cmd_status(args: argparse.Namespace) -> None:
    running, pid = _is_running()
    if running:
        print(f"hermes-kanban-server is running  (pid {pid}, port {args.port})")
        _print_stats(args)
    else:
        print("hermes-kanban-server is NOT running")

    if _is_macos() and _launchd_plist_path().exists():
        label = _SERVICE_LABEL
        out = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True, text=True,
        )
        if out.returncode == 0:
            print(f"\nlaunchd service: {label} (installed)")
        else:
            print(f"\nlaunchd service: {label} (installed, not loaded)")
    elif _is_linux():
        out = subprocess.run(
            ["systemctl", "--user", "is-active", _SERVICE_NAME],
            capture_output=True, text=True,
        )
        state = out.stdout.strip() or "unknown"
        print(f"\nsystemd service: {_SERVICE_NAME}.service ({state})")

def _print_stats(args: argparse.Namespace) -> None:
    import urllib.request, json
    url = f"http://{args.host}:{args.port}/v1/stats"
    headers = {}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())

        total_boards = data.get("total_boards", 0)
        total_tasks = data.get("total_tasks", 0)
        status_dist = data.get("status_distribution", {})

        print(f"\nBoards: {total_boards}")
        print(f"Tasks: {total_tasks}")
        if status_dist:
            print("Status distribution:")
            for status, count in status_dist.items():
                print(f"  {status:8s}: {count:3d}")
    except Exception:
        pass  # server might not be up yet

def cmd_start(args: argparse.Namespace) -> None:
    running, pid = _is_running()
    if running:
        print(f"hermes-kanban-server is already running (pid {pid})")
        return

    if _is_macos() and _launchd_plist_path().exists():
        _launchd_start()
    elif _is_linux():
        _systemd_start()
    else:
        _start_background_process(args)

def cmd_stop(args: argparse.Namespace) -> None:
    if _is_macos() and _launchd_plist_path().exists():
        _launchd_stop()
        return
    if _is_linux():
        _systemd_stop()
        return

    running, pid = _is_running()
    if not running:
        print("hermes-kanban-server is not running")
        return
    print(f"Stopping hermes-kanban-server (pid {pid})…")
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        if not _pid_alive(pid):
            break
        time.sleep(0.5)
    _remove_pid()
    print("Stopped.")

def cmd_restart(args: argparse.Namespace) -> None:
    cmd_stop(args)
    time.sleep(1)
    cmd_start(args)

def cmd_install(args: argparse.Namespace) -> None:
    if _is_macos():
        _launchd_install(args)
    elif _is_linux():
        _systemd_install(args)
    else:
        print("Service installation is not supported on this platform.")
        print("Run manually: hermes-kanban-server run")
        sys.exit(1)

def cmd_uninstall(args: argparse.Namespace) -> None:
    if _is_macos():
        _launchd_uninstall()
    elif _is_linux():
        _systemd_uninstall()
    else:
        print("Service uninstall is not supported on this platform.")
        sys.exit(1)

# ── Background process (fallback for platforms without a service manager) ────

def _start_background_process(args: argparse.Namespace) -> None:
    exe = shutil.which("hermes-kanban-server")
    cmd = [exe or sys.executable]
    if not exe:
        cmd += ["-m", "hermes_kanban_server"]
    cmd += [
        "run",
        "--host", args.host,
        "--port", str(args.port),
        "--log-level", getattr(args, "log_level", "INFO"),
    ]
    if args.api_key:
        cmd += ["--api-key", args.api_key]

    log_out = str(_log_dir() / "kanban_server.log")
    log_err = str(_log_dir() / "kanban_server.error.log")
    with open(log_out, "a", encoding="utf-8") as fout, open(log_err, "a", encoding="utf-8") as ferr:
        proc = subprocess.Popen(
            cmd,
            stdout=fout, stderr=ferr,
            start_new_session=True,
        )
    _write_pid(proc.pid)
    print(f"hermes-kanban-server started (pid {proc.pid})")
    print(f"  Logs: {log_out}")
    print(f"  API: http://{args.host}:{args.port}/v1/health")

# ── launchd (macOS) ───────────────────────────────────────────────────────────

def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_SERVICE_LABEL}.plist"

def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"

def _generate_launchd_plist(args: argparse.Namespace) -> str:
    exe = shutil.which("hermes-kanban-server") or ""
    log_dir = str(_log_dir())
    hermes_home = str(_hermes_home())
    venv_bin = str(Path(_python_path()).parent)

    # Build ProgramArguments
    if exe:
        prog_args = [f"<string>{exe}</string>", "<string>run</string>"]
    else:
        prog_args = [
            f"<string>{_python_path()}</string>",
            "<string>-m</string>",
            "<string>hermes_kanban_server</string>",
            "<string>run</string>",
        ]

    prog_args += [
        f"<string>--host</string>",
        f"<string>{args.host}</string>",
        f"<string>--port</string>",
        f"<string>{args.port}</string>",
    ]
    if args.api_key:
        prog_args += [
            "<string>--api-key</string>",
            f"<string>{args.api_key}</string>",
        ]

    prog_args_xml = "\n        ".join(prog_args)

    sane_path = ":".join([venv_bin, "/usr/local/bin", "/usr/bin", "/bin",
                           os.environ.get("PATH", "")])

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_SERVICE_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        {prog_args_xml}
    </array>

    <key>WorkingDirectory</key>
    <string>{hermes_home}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{sane_path}</string>
        <key>HERMES_HOME</key>
        <string>{hermes_home}</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>{log_dir}/kanban_server.log</string>

    <key>StandardErrorPath</key>
    <string>{log_dir}/kanban_server.error.log</string>
</dict>
</plist>
"""

def _launchd_install(args: argparse.Namespace) -> None:
    plist_path = _launchd_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(_generate_launchd_plist(args), encoding="utf-8")
    # 先 unload 清理可能残留的旧注册（忽略错误）
    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        capture_output=True,
    )
    # 用 load -w 注册并启用
    result = subprocess.run(
        ["launchctl", "load", "-w", str(plist_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"launchctl load failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    print(f"✅ Installed launchd service: {_SERVICE_LABEL}")
    print(f"  Plist: {plist_path}")
    print(f"  Logs:  {_log_dir()}/kanban_server.log")
    print(f"  🚀 hermes-kanban-server will start automatically on login.")

def _launchd_uninstall() -> None:
    plist_path = _launchd_plist_path()
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", "-w", str(plist_path)],
            capture_output=True,
        )
        plist_path.unlink()
    _remove_pid()
    print(f"✅ Uninstalled launchd service: {_SERVICE_LABEL}")

def _launchd_start() -> None:
    result = subprocess.run(
        ["launchctl", "start", _SERVICE_LABEL],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"launchctl start failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    print("✅ hermes-kanban-server started via launchd")

def _launchd_stop() -> None:
    subprocess.run(
        ["launchctl", "stop", _SERVICE_LABEL],
        capture_output=True,
    )
    print("✅ hermes-kanban-server stopped via launchd")

# ── systemd (Linux) ───────────────────────────────────────────────────────────

def _systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{_SERVICE_NAME}.service"

def _generate_systemd_unit(args: argparse.Namespace) -> str:
    exe = shutil.which("hermes-kanban-server") or f"{_python_path()} -m hermes_kanban_server"
    hermes_home = str(_hermes_home())
    log_out = str(_log_dir() / "kanban_server.log")

    extra_args = f" --host {args.host} --port {args.port}"
    if args.api_key:
        extra_args += f" --api-key {args.api_key}"

    return f"""[Unit]
Description=Hermes Kanban Server
After=network.target

[Service]
Type=simple
ExecStart={exe} run{extra_args}
WorkingDirectory={hermes_home}
Environment=HERMES_HOME={hermes_home}
StandardOutput=append:{log_out}
StandardError=append:{log_out}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""

def _systemd_install(args: argparse.Namespace) -> None:
    unit_path = _systemd_unit_path()
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(_generate_systemd_unit(args), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", _SERVICE_NAME], check=True)
    subprocess.run(["systemctl", "--user", "start",  _SERVICE_NAME], check=True)
    print(f"✅ Installed systemd user service: {_SERVICE_NAME}")
    print(f"  Unit: {unit_path}")

def _systemd_uninstall() -> None:
    subprocess.run(["systemctl", "--user", "stop",    _SERVICE_NAME], check=False)
    subprocess.run(["systemctl", "--user", "disable", _SERVICE_NAME], check=False)
    unit_path = _systemd_unit_path()
    if unit_path.exists():
        unit_path.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    _remove_pid()
    print(f"✅ Uninstalled systemd service: {_SERVICE_NAME}")

def _systemd_start() -> None:
    subprocess.run(["systemctl", "--user", "start", _SERVICE_NAME], check=True)
    print(f"✅ hermes-kanban-server started via systemd")

def _systemd_stop() -> None:
    subprocess.run(["systemctl", "--user", "stop", _SERVICE_NAME], check=True)
    print("✅ hermes-kanban-server stopped via systemd")

# ── Argument parser ───────────────────────────────────────────────────────────

def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--host",      default=_DEFAULT_HOST,
                   help="API bind host (default: 127.0.0.1)")
    p.add_argument("--port",      type=int, default=_DEFAULT_PORT,
                   help="API port (default: 8650)")
    p.add_argument("--api-key",   dest="api_key", default=_DEFAULT_KEY,
                   help="Bearer token for API authentication")

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hermes-kanban-server",
        description="Hermes Kanban Server — REST API for Kanban board management",
    )
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    _add_common_args(p)

    sub = p.add_subparsers(dest="subcmd")

    # run
    sp = sub.add_parser("run", help="Run in foreground (default)")
    _add_common_args(sp)
    sp.add_argument("--log-level", default="INFO",
                    choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    # install
    sp = sub.add_parser("install", help="Install as launchd/systemd service")
    _add_common_args(sp)

    # uninstall
    sub.add_parser("uninstall", help="Remove launchd/systemd service")

    # start
    sp = sub.add_parser("start", help="Start the background service")
    _add_common_args(sp)

    # stop
    sp = sub.add_parser("stop", help="Stop the background service")
    _add_common_args(sp)

    # restart
    sp = sub.add_parser("restart", help="Restart the background service")
    _add_common_args(sp)

    # status
    sp = sub.add_parser("status", help="Show service status")
    _add_common_args(sp)

    return p

def _setup_logging(args: argparse.Namespace) -> None:
    level = getattr(logging, getattr(args, "log_level", "INFO"), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    _dispatch = {
        None:        cmd_run,
        "run":       cmd_run,
        "install":   cmd_install,
        "uninstall": cmd_uninstall,
        "start":     cmd_start,
        "stop":      cmd_stop,
        "restart":   cmd_restart,
        "status":    cmd_status,
    }

    handler = _dispatch.get(args.subcmd)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)
    sys.exit(0)


if __name__ == "__main__":
    main()

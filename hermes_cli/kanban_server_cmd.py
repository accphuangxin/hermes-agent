"""
CLI commands for Kanban API Server

⚠️ DEPRECATED: This module provides the old 'hermes kanban server' subcommand.
   New code should use the standalone 'hermes-kanban-server' command instead.

   Old style: hermes kanban server run --port 8650
   New style: hermes-kanban-server run --port 8650

   See: docs/kanban-server-quickstart.md
"""

import argparse
import os
import sys
from pathlib import Path


def add_kanban_server_subparser(subparsers):
    """
    Add 'kanban server' subcommand to argument parser.

    Args:
        subparsers: argparse subparsers object
    """
    server_parser = subparsers.add_parser(
        "server",
        help="Manage Kanban API Server",
        description="Start, stop, and manage the Kanban REST API server"
    )

    server_subparsers = server_parser.add_subparsers(dest="server_action", required=True)

    # Run command (foreground)
    run_parser = server_subparsers.add_parser(
        "run",
        help="Run server in foreground"
    )
    run_parser.add_argument(
        "--host",
        default=os.environ.get("KANBAN_SERVER_HOST", "0.0.0.0"),
        help="Bind host (default: 0.0.0.0)"
    )
    run_parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("KANBAN_SERVER_PORT", "8650")),
        help="Bind port (default: 8650)"
    )
    run_parser.add_argument(
        "--api-key",
        default=os.environ.get("KANBAN_SERVER_API_KEY"),
        help="API key for Bearer token authentication"
    )

    # Install command
    install_parser = server_subparsers.add_parser(
        "install",
        help="Install as system service (launchd/systemd)"
    )
    install_parser.add_argument("--host", default="0.0.0.0")
    install_parser.add_argument("--port", type=int, default=8650)
    install_parser.add_argument("--api-key", help="API key")

    # Start command
    server_subparsers.add_parser(
        "start",
        help="Start the background service"
    )

    # Stop command
    server_subparsers.add_parser(
        "stop",
        help="Stop the background service"
    )

    # Restart command
    server_subparsers.add_parser(
        "restart",
        help="Restart the background service"
    )

    # Status command
    server_subparsers.add_parser(
        "status",
        help="Show service status"
    )

    # Uninstall command
    server_subparsers.add_parser(
        "uninstall",
        help="Uninstall the system service"
    )

    server_parser.set_defaults(func=kanban_server_command)


def kanban_server_command(args: argparse.Namespace) -> int:
    """
    Handle kanban server subcommands.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    action = args.server_action

    if action == "run":
        return _cmd_run(args)
    elif action == "install":
        return _cmd_install(args)
    elif action == "start":
        return _cmd_start()
    elif action == "stop":
        return _cmd_stop()
    elif action == "restart":
        return _cmd_restart()
    elif action == "status":
        return _cmd_status()
    elif action == "uninstall":
        return _cmd_uninstall()
    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        return 1


def _cmd_run(args: argparse.Namespace) -> int:
    """Run server in foreground"""
    # Show deprecation warning
    print("⚠️  DEPRECATION WARNING:", file=sys.stderr)
    print("   'hermes kanban server' is deprecated.", file=sys.stderr)
    print("   Please use 'hermes-kanban-server' instead.", file=sys.stderr)
    print("", file=sys.stderr)
    print("   Old: hermes kanban server run", file=sys.stderr)
    print("   New: hermes-kanban-server run", file=sys.stderr)
    print("", file=sys.stderr)

    try:
        from hermes_kanban_server import server

        server.run_server(
            host=args.host,
            port=args.port,
            api_key=args.api_key,
        )
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        return 1


def _cmd_install(args: argparse.Namespace) -> int:
    """Install as system service"""
    import platform
    import subprocess

    system = platform.system()

    if system == "Darwin":
        return _install_launchd(args)
    elif system == "Linux":
        return _install_systemd(args)
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        return 1


def _install_launchd(args: argparse.Namespace) -> int:
    """Install launchd service on macOS"""
    import subprocess

    label = "ai.hermes.kanban-server"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"

    # Ensure LaunchAgents directory exists
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    # Build command args
    cmd_args = [
        sys.executable,
        "-m", "hermes_cli.main",
        "kanban", "server", "run",
        "--host", args.host,
        "--port", str(args.port),
    ]

    if args.api_key:
        cmd_args.extend(["--api-key", args.api_key])

    # Generate plist content
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
"""

    for arg in cmd_args:
        plist_content += f"        <string>{arg}</string>\n"

    plist_content += """    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>""" + str(Path.home() / ".hermes" / "logs" / "kanban-server.log") + """</string>

    <key>StandardErrorPath</key>
    <string>""" + str(Path.home() / ".hermes" / "logs" / "kanban-server.error.log") + """</string>
</dict>
</plist>
"""

    # Ensure log directory exists
    log_dir = Path.home() / ".hermes" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Write plist file
    plist_path.write_text(plist_content, encoding="utf-8")

    print(f"✅ Wrote service file: {plist_path}")

    # Load service
    try:
        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
        print(f"✅ Loaded service: {label}")
        print(f"🚀 Kanban API Server installed and started")
        print(f"")
        print(f"Logs:")
        print(f"  stdout: {log_dir}/kanban-server.log")
        print(f"  stderr: {log_dir}/kanban-server.error.log")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to load service: {e}", file=sys.stderr)
        return 1


def _install_systemd(args: argparse.Namespace) -> int:
    """Install systemd service on Linux"""
    print("systemd installation not yet implemented", file=sys.stderr)
    return 1


def _cmd_start() -> int:
    """Start the service"""
    import platform
    import subprocess

    system = platform.system()

    if system == "Darwin":
        label = "ai.hermes.kanban-server"
        try:
            subprocess.run(["launchctl", "start", label], check=True)
            print(f"✅ Started service: {label}")
            return 0
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to start service: {e}", file=sys.stderr)
            return 1
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        return 1


def _cmd_stop() -> int:
    """Stop the service"""
    import platform
    import subprocess

    system = platform.system()

    if system == "Darwin":
        label = "ai.hermes.kanban-server"
        try:
            subprocess.run(["launchctl", "stop", label], check=True)
            print(f"✅ Stopped service: {label}")
            return 0
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to stop service: {e}", file=sys.stderr)
            return 1
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        return 1


def _cmd_restart() -> int:
    """Restart the service"""
    _cmd_stop()
    return _cmd_start()


def _cmd_status() -> int:
    """Show service status"""
    import platform
    import subprocess

    system = platform.system()

    if system == "Darwin":
        label = "ai.hermes.kanban-server"
        try:
            result = subprocess.run(
                ["launchctl", "list", label],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f"✅ Service is running: {label}")
                print(result.stdout)
                return 0
            else:
                print(f"❌ Service is not running: {label}")
                return 1
        except Exception as e:
            print(f"Error checking status: {e}", file=sys.stderr)
            return 1
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        return 1


def _cmd_uninstall() -> int:
    """Uninstall the service"""
    import platform
    import subprocess

    system = platform.system()

    if system == "Darwin":
        label = "ai.hermes.kanban-server"
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"

        if not plist_path.exists():
            print(f"❌ Service not installed: {plist_path} not found")
            return 1

        # Unload service
        try:
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            print(f"✅ Unloaded service: {label}")
        except Exception:
            pass

        # Remove plist file
        plist_path.unlink()
        print(f"✅ Removed service file: {plist_path}")
        print(f"🗑️  Kanban API Server uninstalled")
        return 0
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        return 1

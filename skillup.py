#!/usr/bin/env python3
"""
Skillup - Multi-Application Desktop Platform

This is the main entry point for the Skillup desktop platform.
It provides a unified framework for running multiple applications.

Usage:
    skillup.py [OPTIONS] [APP OPTIONS]

Options:
    --desktop          Start desktop mode (GUI with app launcher)
    --app:<id>         Run specific app by ID or GUID (e.g., --app:skillverifier)

Examples:
    # Start desktop mode
    python3 skillup.py --desktop

    # Start desktop mode with auto-launch app
    python3 skillup.py --desktop --app:skillverifier

    # Run skillverifier app in CLI mode
    python3 skillup.py --app:skillverifier test.il

    # Run skillverifier with options
    python3 skillup.py --app:skillverifier --define=defs.txt test.il

Environment Variables:
    SKILLUP_CONFIG_HOME         Custom configuration directory path
                                Default: $XDG_CONFIG_HOME/skillup or ~/.config/skillup
                                Example: export SKILLUP_CONFIG_HOME="~/my_skillup_config"

    SKILLUP_DEFAULT_CONFIG      Path to default configuration override file
                                Allows overriding hardcoded default values
                                Uses INI format with sections: [desktop] and [app_id]
                                Priority: User config > SKILLUP_DEFAULT_CONFIG > skillup_default_config.ini > hardcoded defaults

                                Fallback: If not set, looks for skillup_default_config.ini
                                in the skillup.py parent directory (no env var needed)
                                Example: /home/work/code/skillup_default_config.ini
                                Example env var: export SKILLUP_DEFAULT_CONFIG="/etc/skillup/defaults.ini"

                                File format:
                                    [desktop]
                                    general.firefox = /usr/bin/firefox
                                    general.language = ko
                                    general.account_type = sqlite
                                    general.account_db = /shared/skillup/account.db

                                    [550e8400]
                                    verify.files_input = /opt/samples/

Desktop Configuration Keys ([desktop] section):
    general.account_type            Account database backend type.
                                    Default: sqlite
                                    Supported values:
                                        sqlite  - SQLite file (current, NFS-safe via WAL mode)
                                    Future types (not yet implemented):
                                        ldap    - LDAP/Active Directory
                                        rest    - REST API backend
                                    When account_type = sqlite, general.account_db specifies the file path.

    general.account_db              Path to the SQLite account database file.
                                    Used when general.account_type = sqlite.
                                    Default: desktop/data/account.db (relative to skillup root)
                                    Example: /shared/nfs/skillup/account.db
                                    Supports shared NFS paths for multi-user environments.

    App-specific environment variables are documented in each app's help.
"""

import sys


def print_usage():
    """Print usage information"""
    print("skillup.py [OPTIONS] [APP OPTIONS]")
    print()
    print("Options:")
    print("    --desktop          Start desktop mode (GUI with app launcher)")
    print("    --app:<id>         Run specific app (e.g., --app:skillverifier)")
    print()
    print("Examples:")
    print("    python3 skillup.py --desktop                    # Start desktop GUI")
    print("    python3 skillup.py --app:skillverifier test.il  # Run skillverifier app")


def main():
    """
    Main entry point for skillup.py CLI.

    This is an app container that routes to desktop mode or specific apps.
    """
    # Parse command-line arguments to detect desktop mode
    desktop_mode = '--desktop' in sys.argv[1:]
    app_id = None

    # Check for explicit app specification
    for arg in sys.argv[1:]:
        if arg.startswith('--app:'):
            app_id = arg[6:]
            break

    # ========================================================================
    # SHOW USAGE if no arguments provided or no app specified
    # ========================================================================
    if len(sys.argv) == 1 or (not desktop_mode and not app_id):
        print_usage()
        return 0

    # ========================================================================
    # DESKTOP MODE: Start desktop GUI
    # ========================================================================
    if desktop_mode:
        from desktop.desktop import run_desktop
        # Collect app-specific extra args (e.g. --skillform-run=/tmp/a.json)
        app_extra_args = [
            arg for arg in sys.argv[1:]
            if not arg.startswith('--app:') and arg != '--desktop'
        ]
        return run_desktop(auto_launch_app=app_id, app_extra_args=app_extra_args)

    # ========================================================================
    # CLI MODE: Route to specified app
    # ========================================================================
    from lib.appmgr import run_app_cli
    # Pass all arguments except --app: to the app
    app_args = [arg for arg in sys.argv[1:] if not arg.startswith('--app:')]
    return run_app_cli(app_id, app_args)


if __name__ == "__main__":
    sys.exit(main())

"""
bridge.py - SKILL ↔ skillform TCP bridge

Launched by libform.il via ipcBeginProcess.
- Opens a TCP server on an ephemeral port for skillform to connect
- Opens a second TCP server (cmd_port) for SKILL to send commands via nc
- Launches skillup.py with --skillform-caller-port=<N>
- Forwards lines: TCP socket → stdout (to SKILL)
                  cmd_port → TCP socket (commands from SKILL)

Usage:
    python3 bridge.py <form_path> <skillup_py> [python_bin]
"""

import os
import sys
import socket
import subprocess
import threading


def main():
    if len(sys.argv) < 3:
        sys.stderr.write('bridge.py: usage: bridge.py <form_path> <skillup_py> [python_bin]\n')
        sys.exit(1)

    form_path  = sys.argv[1]
    skillup_py = sys.argv[2]
    python_bin = sys.argv[3] if len(sys.argv) > 3 else sys.executable

    # TCP server for skillform to connect (events: skillform → SKILL)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    # TCP server for SKILL to send commands (commands: SKILL → skillform)
    cmd_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cmd_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    cmd_srv.bind(('127.0.0.1', 0))
    cmd_srv.listen(5)
    cmd_port = cmd_srv.getsockname()[1]

    cmd = [python_bin, skillup_py,
           '--desktop', '--app:skillform',
           '--skillform-run=' + form_path,
           '--skillform-caller-port=' + str(port)]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=open('/tmp/skillform.log', 'a'),
    )

    # Wait for skillform to connect (30s timeout)
    srv.settimeout(30)
    try:
        conn, _ = srv.accept()
    except socket.timeout:
        sys.stderr.write('bridge.py: skillform did not connect within 30s\n')
        proc.terminate()
        sys.exit(1)
    finally:
        srv.close()

    conn.settimeout(None)

    # stdout: line-buffered so SKILL receives events promptly
    out = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

    # Send skillup PID and cmd_port to SKILL
    out.write('{"type":"_init","pid":' + str(proc.pid) + ',"cmd_port":' + str(cmd_port) + '}\n')
    out.flush()

    def tcp_to_stdout():
        try:
            for line in conn.makefile('r', encoding='utf-8'):
                out.write(line)
                out.flush()
        except Exception:
            pass

    def cmd_server():
        """Accept command connections from SKILL (via nc) and forward to skillform"""
        cmd_srv.settimeout(None)
        while True:
            try:
                c, _ = cmd_srv.accept()
                try:
                    for line in c.makefile('r', encoding='utf-8'):
                        conn.sendall(line.encode('utf-8'))
                except Exception:
                    pass
                finally:
                    try:
                        c.close()
                    except Exception:
                        pass
            except Exception:
                break

    t1 = threading.Thread(target=tcp_to_stdout, daemon=True)
    t2 = threading.Thread(target=cmd_server,    daemon=True)
    t1.start()
    t2.start()

    proc.wait()
    cmd_srv.close()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""OKX Monitor Dashboard Server — 本地管理面板"""
from __future__ import annotations

import json
import os
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_DIR = BASE
MSG_DIR = BASE / "messages"
PLIST_PREFIX = "com.jinxu.okx-monitor."
PORT = 8765


def get_all_status() -> dict:
    """获取所有 okx-monitor 服务的 launchd 状态"""
    result = subprocess.run(
        ["launchctl", "list"],
        capture_output=True, text=True, timeout=10
    )
    status = {}
    for line in result.stdout.split("\n"):
        if PLIST_PREFIX not in line:
            continue
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        pid_str, exit_str, label = parts[0], parts[1], parts[2]
        try:
            pid = int(pid_str) if pid_str != "-" else 0
        except ValueError:
            pid = 0
        try:
            exit_code = int(exit_str) if exit_str != "-" else 0
        except ValueError:
            exit_code = 0
        short = label.replace(PLIST_PREFIX, "")
        status[short] = {"pid": pid, "exit": exit_code, "label": label}
    return status


def get_log_tail(label: str, lines: int = 80) -> str:
    """读取最近 N 行日志"""
    log_path = LOG_DIR / f"{label}.log"
    if not log_path.exists():
        return "[ 日志文件不存在 ]"
    try:
        result = subprocess.run(
            ["tail", "-n", str(lines), str(log_path)],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout or "[ 日志为空 ]"
    except Exception as e:
        return f"[ 读取失败: {e} ]"


def get_message(label: str) -> dict | None:
    """读取缓存的最新推送内容"""
    msg_path = MSG_DIR / f"{label}.json"
    if not msg_path.exists():
        return None
    try:
        return json.loads(msg_path.read_text("utf-8"))
    except Exception:
        return None


def get_all_messages() -> dict:
    """读取所有脚本的最新推送内容"""
    result = {}
    if not MSG_DIR.exists():
        return result
    for f in MSG_DIR.glob("*.json"):
        label = f.stem
        msg = get_message(label)
        if msg:
            result[label] = msg
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress logs

    def do_GET(self):
        if self.path.startswith("/api/messages"):
            self.send_json(get_all_messages())
        elif self.path.startswith("/api/message/"):
            label = self.path.split("/api/message/")[-1].split("?")[0]
            msg = get_message(label)
            self.send_json(msg or {"error": "no message"})
        elif self.path.startswith("/api/status"):
            self.send_json(get_all_status())
        elif self.path.startswith("/api/log/"):
            label = self.path.split("/api/log/")[-1].split("?")[0]
            self.send_text(get_log_tail(label))
        elif self.path == "/" or self.path == "/dashboard.html":
            self.send_file(BASE / "dashboard.html", "text/html; charset=utf-8")
        else:
            target = BASE / self.path.lstrip("/")
            if target.exists() and target.is_relative_to(BASE):
                self.send_file(target)
            else:
                self.send_error(404)

    def send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type=None):
        data = path.read_bytes()
        self.send_response(200)
        ct = content_type or "application/octet-stream"
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)


def main():
    import signal
    import sys

    server = HTTPServer(("127.0.0.1", PORT), Handler)

    def shutdown(sig, frame):
        print("\n关闭服务...")
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"OKX Monitor Dashboard 已启动")
    print(f"→ 浏览器打开: http://127.0.0.1:{PORT}")
    print(f"→ 按 Ctrl+C 停止")
    print()
    server.serve_forever()


if __name__ == "__main__":
    main()

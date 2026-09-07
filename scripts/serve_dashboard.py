#!/usr/bin/env python3
"""Serve the research dashboard and safely reveal catalog files in Explorer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_submission import (  # noqa: E402
    DATASET_FILENAMES,
    SubmissionValidationError,
    normalize_etf_code,
    prepare_etf_submission,
)
from src.dashboard_runtime import (  # noqa: E402
    DashboardRuntimeError,
    list_submission_packages,
    load_published_portfolio,
    load_published_results,
    load_published_surfaces,
    publish_backtest_result,
    publish_parameter_surface,
    publish_portfolio_result,
    run_parameter_surface,
    run_portfolio_backtest,
    run_submission_backtest,
)

OPEN_ENDPOINT = "/__dashboard/open-in-explorer"
UPLOAD_ENDPOINT = "/__dashboard/submit-etf/upload"
PREPARE_ENDPOINT = "/__dashboard/submit-etf/prepare"
SUBMISSIONS_ENDPOINT = "/__dashboard/submissions"
BACKTEST_ENDPOINT = "/__dashboard/backtest/run"
PUBLISH_ENDPOINT = "/__dashboard/backtest/publish"
PUBLISHED_ENDPOINT = "/__dashboard/backtest/published"
PORTFOLIO_BACKTEST_ENDPOINT = "/__dashboard/portfolio/run"
PORTFOLIO_PUBLISH_ENDPOINT = "/__dashboard/portfolio/publish"
PORTFOLIO_PUBLISHED_ENDPOINT = "/__dashboard/portfolio/published"
SURFACE_BACKTEST_ENDPOINT = "/__dashboard/surface/run"
SURFACE_PUBLISH_ENDPOINT = "/__dashboard/surface/publish"
SURFACE_PUBLISHED_ENDPOINT = "/__dashboard/surface/published"
ALLOWED_TOP_LEVEL = {"data", "outputs"}
ALLOWED_SUFFIXES = {".csv", ".json", ".js", ".md"}
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


def resolve_catalog_file(relative_path: str) -> Path:
    """Return an allowed catalog file without permitting path traversal."""
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("缺少数据文件路径")

    relative = Path(relative_path.replace("/", "\\"))
    if relative.is_absolute() or not relative.parts:
        raise ValueError("只允许交接包内的相对路径")
    if relative.parts[0].lower() not in ALLOWED_TOP_LEVEL:
        raise ValueError("只允许查看 data 或 outputs 目录中的文件")

    target = (PROJECT_ROOT / relative).resolve()
    try:
        target.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("路径超出交接包范围") from exc

    if target.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("不支持该文件类型")
    if not target.is_file():
        raise ValueError("数据文件不存在")
    return target


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    server_version = "ResearchDashboard/1.1"

    def end_headers(self) -> None:
        # Dashboard HTML and JavaScript change during local research iterations;
        # stale iframe resources can otherwise hide newly activated controls.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _allow_local_action(self, expected_action: str) -> bool:
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin", "")
        allowed_origins = {f"http://{host}", f"https://{host}"}
        if origin and origin not in allowed_origins:
            self._send_json(403, {"ok": False, "message": "拒绝跨站调用"})
            return False
        if self.headers.get("X-Dashboard-Action") != expected_action:
            self._send_json(403, {"ok": False, "message": "缺少本地操作标记"})
            return False
        return True

    def _read_json(self, max_bytes: int = 4096) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > max_bytes:
            raise ValueError("请求内容长度不合法")
        value = json.loads(self.rfile.read(content_length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求内容必须是JSON对象")
        return value

    def _handle_open(self) -> None:
        if not self._allow_local_action("open-file"):
            return

        try:
            payload = self._read_json()
            target = resolve_catalog_file(payload.get("path", ""))
            if not getattr(self.server, "dry_run_open", False):
                subprocess.Popen(
                    ["explorer.exe", "/select,", str(target)],
                    close_fds=True,
                )
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            self._send_json(400, {"ok": False, "message": str(exc)})
            return

        self._send_json(200, {"ok": True})

    def _submission_stage(self, session_id: str) -> Path:
        if not SESSION_PATTERN.fullmatch(session_id):
            raise ValueError("上传会话标识不合法")
        stage = (PROJECT_ROOT / "data" / "user_submissions" / "_staging" / session_id).resolve()
        stage.relative_to(PROJECT_ROOT)
        return stage

    def _handle_upload(self) -> None:
        if not self._allow_local_action("upload-etf-data"):
            return
        temp_path: Path | None = None
        try:
            etf_code = normalize_etf_code(self.headers.get("X-ETF-Code", ""))
            session_id = self.headers.get("X-Upload-Session", "")
            dataset = self.headers.get("X-Dataset-Type", "")
            if dataset not in DATASET_FILENAMES:
                raise ValueError("未知的数据类型")
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                raise ValueError("上传文件为空")
            if content_length > MAX_UPLOAD_BYTES:
                raise ValueError("单个上传文件不能超过512 MiB")

            stage = self._submission_stage(session_id)
            stage.mkdir(parents=True, exist_ok=True)
            destination = stage / DATASET_FILENAMES[dataset]
            temp_path = stage / f".{destination.name}.uploading"
            remaining = content_length
            digest = hashlib.sha256()
            with temp_path.open("wb") as handle:
                while remaining:
                    chunk = self.rfile.read(min(UPLOAD_CHUNK_BYTES, remaining))
                    if not chunk:
                        raise ValueError("上传中断，请重新提交")
                    handle.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
            temp_path.replace(destination)
        except (OSError, ValueError, SubmissionValidationError) as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            self._send_json(400, {"ok": False, "message": str(exc)})
            return

        self._send_json(
            200,
            {
                "ok": True,
                "etf_code": etf_code,
                "dataset": dataset,
                "bytes": content_length,
                "sha256": digest.hexdigest(),
            },
        )

    def _handle_prepare(self) -> None:
        if not self._allow_local_action("prepare-etf-data"):
            return
        try:
            payload = self._read_json()
            etf_code = normalize_etf_code(payload.get("etf_code", ""))
            session_id = str(payload.get("session_id", ""))
            stage = self._submission_stage(session_id)
            if not stage.is_dir():
                raise ValueError("找不到本次上传，请重新选择三个文件")
            result = prepare_etf_submission(PROJECT_ROOT, stage, etf_code, session_id)
        except (OSError, ValueError, SubmissionValidationError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "message": str(exc)})
            return
        except Exception as exc:  # keep the local UI responsive while preserving server logs
            self.log_error("ETF submission failed: %s", exc)
            self._send_json(500, {"ok": False, "message": "数据处理失败，请查看服务窗口中的错误信息"})
            return
        self._send_json(200, result)

    def _handle_backtest(self) -> None:
        if not self._allow_local_action("run-backtest"):
            return
        try:
            payload = self._read_json(max_bytes=16384)
            result = run_submission_backtest(PROJECT_ROOT, payload.get("manifest_path"), payload)
        except (DashboardRuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "message": str(exc)})
            return
        except Exception as exc:  # preserve detailed server logs without exposing internals to the browser
            self.log_error("Dynamic backtest failed: %s", exc)
            self._send_json(500, {"ok": False, "message": "回测失败，请查看服务窗口中的错误信息"})
            return
        result["ok"] = True
        self._send_json(200, result)

    def _handle_publish(self) -> None:
        if not self._allow_local_action("publish-backtest"):
            return
        try:
            payload = self._read_json(max_bytes=8192)
            result = publish_backtest_result(PROJECT_ROOT, payload.get("run_manifest_path"))
        except (DashboardRuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "message": str(exc)})
            return
        self._send_json(200, result)

    def _handle_surface_backtest(self) -> None:
        if not self._allow_local_action("run-surface"):
            return
        try:
            payload = self._read_json(max_bytes=32768)
            result = run_parameter_surface(PROJECT_ROOT, payload.get("manifest_path"), payload)
        except (DashboardRuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "message": str(exc)})
            return
        except Exception as exc:
            self.log_error("Dynamic parameter surface failed: %s", exc)
            self._send_json(500, {"ok": False, "message": "参数图谱生成失败，请查看服务窗口中的错误信息"})
            return
        result["ok"] = True
        self._send_json(200, result)

    def _handle_surface_publish(self) -> None:
        if not self._allow_local_action("publish-surface"):
            return
        try:
            payload = self._read_json(max_bytes=8192)
            result = publish_parameter_surface(PROJECT_ROOT, payload.get("surface_manifest_path"))
        except (DashboardRuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "message": str(exc)})
            return
        self._send_json(200, result)

    def _handle_portfolio_backtest(self) -> None:
        if not self._allow_local_action("run-portfolio"):
            return
        try:
            payload = self._read_json(max_bytes=32768)
            result = run_portfolio_backtest(PROJECT_ROOT, payload)
        except (DashboardRuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "message": str(exc)})
            return
        except Exception as exc:
            self.log_error("Dynamic portfolio backtest failed: %s", exc)
            self._send_json(500, {"ok": False, "message": "组合回测失败，请查看服务窗口中的错误信息"})
            return
        result["ok"] = True
        self._send_json(200, result)

    def _handle_portfolio_publish(self) -> None:
        if not self._allow_local_action("publish-portfolio"):
            return
        try:
            payload = self._read_json(max_bytes=8192)
            result = publish_portfolio_result(PROJECT_ROOT, payload.get("run_manifest_path"))
        except (DashboardRuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "message": str(exc)})
            return
        self._send_json(200, result)

    def _handle_runtime_read(self, path: str) -> bool:
        try:
            if path == SUBMISSIONS_ENDPOINT:
                self._send_json(200, {"ok": True, "submissions": list_submission_packages(PROJECT_ROOT)})
                return True
            if path == PUBLISHED_ENDPOINT:
                self._send_json(200, load_published_results(PROJECT_ROOT))
                return True
            if path == PORTFOLIO_PUBLISHED_ENDPOINT:
                self._send_json(200, load_published_portfolio(PROJECT_ROOT))
                return True
            if path == SURFACE_PUBLISHED_ENDPOINT:
                self._send_json(200, load_published_surfaces(PROJECT_ROOT))
                return True
        except (DashboardRuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(500, {"ok": False, "message": str(exc)})
            return True
        return False

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlsplit(self.path).path
        if not self._handle_runtime_read(path):
            super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlsplit(self.path).path
        if path == OPEN_ENDPOINT:
            self._handle_open()
        elif path == UPLOAD_ENDPOINT:
            self._handle_upload()
        elif path == PREPARE_ENDPOINT:
            self._handle_prepare()
        elif path == BACKTEST_ENDPOINT:
            self._handle_backtest()
        elif path == PUBLISH_ENDPOINT:
            self._handle_publish()
        elif path == SURFACE_BACKTEST_ENDPOINT:
            self._handle_surface_backtest()
        elif path == SURFACE_PUBLISH_ENDPOINT:
            self._handle_surface_publish()
        elif path == PORTFOLIO_BACKTEST_ENDPOINT:
            self._handle_portfolio_backtest()
        elif path == PORTFOLIO_PUBLISH_ENDPOINT:
            self._handle_portfolio_publish()
        else:
            self._send_json(404, {"ok": False, "message": "接口不存在"})


def main() -> None:
    parser = argparse.ArgumentParser(description="启动最终交接看板")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dry-run-open", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    handler = partial(DashboardRequestHandler, directory=str(PROJECT_ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    server.dry_run_open = args.dry_run_open
    print(f"统一看板：http://127.0.0.1:{args.port}/dashboard/", flush=True)
    print("按 Ctrl+C 停止服务。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Command adapters for Yonsei Portal, Underwood, LearnUs, and attendance."""

from __future__ import annotations

import json
import hashlib
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from yonsei_bridge.cdp import BridgeError, CdpConnection, ChromeRuntime, bridge_home
else:
    from .cdp import BridgeError, CdpConnection, ChromeRuntime, bridge_home


PORTAL = "https://portal.yonsei.ac.kr/ui/index.html"
UNDERWOOD = "https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/initPageWork.do"
SPACE = "https://space.yonsei.ac.kr/"
ICERT = "https://icert.yonsei.ac.kr/"
LEARNUS = "https://ys.learnus.org/my/"
ATTENDANCE = "https://ysrollbook.yonsei.ac.kr/"


MENU_ROUTES = {
    "scholarships": ("장학", "학생장학신청"),
    "mileage": ("수업", "마일리지신청내역"),
    "classes": ("수업", "수강신청내역"),
    "graduation": ("졸업", "학점취득현황조회"),
    "graduation_audit": ("졸업", "졸업예비사정조회"),
    "teaching": ("교직", "교직이수내역조회"),
    "teaching_diagnosis": ("교직", "교직자가진단"),
    "shuttle": ("셔틀버스", "셔틀버스예약"),
}

SPACE_REQUEST_FIELDS = {
    "date": ("이용일자", "사용일자", "예약일자", "일자"),
    "start_time": ("시작시간", "사용시작", "이용시작"),
    "end_time": ("종료시간", "사용종료", "이용종료"),
    "headcount": ("사용인원", "이용인원", "신청인원", "인원"),
    "purpose": ("사용목적", "이용목적", "신청사유", "목적"),
    "building": ("건물", "건물명"),
    "equipment": ("필요장비", "기자재", "장비"),
    "organizer": ("주최자", "신청자", "단체명"),
    "contact": ("연락처", "휴대전화", "전화번호"),
}

DORM_REQUEST_FIELDS = {
    "campus": ("캠퍼스",),
    "dorm": ("기숙사", "생활관"),
    "date": ("신청일자", "이용일자", "외박일자", "일자"),
    "start_time": ("시작시간", "출발시간"),
    "end_time": ("종료시간", "귀관시간"),
    "reason": ("신청사유", "외박사유", "사유"),
    "facility": ("시설", "장소"),
    "roommate": ("룸메이트", "동거인"),
    "issue": ("고장내용", "신고내용", "내용"),
}

DOCUMENT_LABELS = {
    "enrollment": "재학증명서",
    "transcript": "성적증명서",
    "graduation": "졸업증명서",
    "expected_graduation": "졸업예정증명서",
    "leave": "휴학증명서",
    "completion": "수료증명서",
}


def _redact(text: str) -> str:
    text = re.sub(r"\b\d{8,12}\b", "[redacted]", text)
    text = re.sub(r"학생\([^)]*\)\s*[^\n]*", "학생", text)
    text = re.sub(r"(?m)^[^\n]{1,24}\s+님\s*$", "[student]", text)
    text = re.sub(r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b", "[redacted]", text)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[redacted]", text)
    return text


@dataclass
class PageSnapshot:
    url: str
    title: str
    text: str
    grids: list[dict[str, Any]]
    buttons: list[str]
    inputs: list[dict[str, Any]]
    links: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url.split("?", 1)[0],
            "title": self.title,
            "text": self.text,
            "grids": self.grids,
            "buttons": self.buttons,
            "inputs": self.inputs,
            "links": self.links,
        }


class BrowserPage:
    def __init__(self, connection: CdpConnection) -> None:
        self.connection = connection
        self.connection.command("Page.enable")
        self.connection.command("Runtime.enable")
        self.connection.command("Network.enable")

    def evaluate(
        self,
        expression: str,
        *,
        timeout: float = 15.0,
        context_id: int | None = None,
    ) -> Any:
        params: dict[str, Any] = {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
            "userGesture": True,
        }
        if context_id is not None:
            params["contextId"] = context_id
        result = self.connection.command(
            "Runtime.evaluate",
            params,
            timeout=timeout,
        )
        exception = result.get("exceptionDetails")
        if exception:
            raise BridgeError(str(exception.get("text", "Page evaluation failed.")))
        return result.get("result", {}).get("value")

    def _frame_contexts(self) -> list[int]:
        tree = self.connection.command("Page.getFrameTree").get("frameTree", {})
        frame_ids: list[str] = []

        def collect(node: dict[str, Any]) -> None:
            frame_id = node.get("frame", {}).get("id")
            if frame_id:
                frame_ids.append(str(frame_id))
            for child in node.get("childFrames", []) or []:
                collect(child)

        collect(tree)
        contexts: list[int] = []
        for frame_id in frame_ids:
            try:
                result = self.connection.command(
                    "Page.createIsolatedWorld",
                    {
                        "frameId": frame_id,
                        "worldName": "yonsei-bridge",
                        "grantUniveralAccess": False,
                    },
                )
                contexts.append(int(result["executionContextId"]))
            except (BridgeError, KeyError, TypeError, ValueError):
                continue
        return contexts

    def _evaluate_frames(self, expression: str) -> list[Any]:
        values: list[Any] = []
        contexts = self._frame_contexts()
        if not contexts:
            return [self.evaluate(expression)]
        for context_id in contexts:
            try:
                values.append(self.evaluate(expression, context_id=context_id))
            except BridgeError:
                continue
        return values

    def _evaluate_until_true(self, expression: str) -> bool:
        contexts = self._frame_contexts()
        if not contexts:
            return bool(self.evaluate(expression))
        for context_id in contexts:
            try:
                if self.evaluate(expression, context_id=context_id):
                    return True
            except BridgeError:
                continue
        return False

    def navigate(self, url: str, wait: float = 2.0) -> None:
        target = urlsplit(url)
        if target.scheme != "https" or not (
            target.hostname == "yonsei.ac.kr"
            or (target.hostname or "").endswith(".yonsei.ac.kr")
            or target.hostname == "ys.learnus.org"
        ):
            raise BridgeError("Refused navigation outside an official Yonsei or LearnUs host.")
        self.connection.command("Page.navigate", {"url": url})
        time.sleep(wait)

    def click_text(self, text: str, *, exact: bool = True) -> bool:
        encoded = json.dumps(text, ensure_ascii=False)
        exact_json = json.dumps(exact)
        return self._evaluate_until_true(
            f"""
                (() => {{
                  const wanted = {encoded};
                  const exact = {exact_json};
                  const visible = (el) => {{
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                  }};
                  const docs = [document];
                  for (const frame of document.querySelectorAll('iframe,frame')) {{
                    try {{ if (frame.contentDocument) docs.push(frame.contentDocument); }} catch (_) {{}}
                  }}
                  const nodes = docs.flatMap(doc => [...doc.querySelectorAll(
                    'button,a,label,[role="button"],[role="tab"],.cl-button,.cl-tabfolder-item,.cl-grid-row'
                  )])
                    .filter(el => {{
                      const label = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
                      return (exact ? label === wanted : label.includes(wanted)) && visible(el);
                    }})
                    .sort((a,b) => a.children.length - b.children.length);
                  if (!nodes.length) return false;
                  nodes[0].click();
                  return true;
                }})()
            """
        )

    def fill_label(self, label: str, value: str) -> bool:
        return self._evaluate_until_true(
            f"""
                (() => {{
                  const label = {json.dumps(label, ensure_ascii=False)};
                  const value = {json.dumps(value, ensure_ascii=False)};
                  const docs = [document];
                  for (const frame of document.querySelectorAll('iframe,frame')) {{
                    try {{ if (frame.contentDocument) docs.push(frame.contentDocument); }} catch (_) {{}}
                  }}
                  const inputs = docs.flatMap(doc => [...doc.querySelectorAll('input,textarea,select')]);
                  const norm = s => String(s || '').replace(/\\s+/g, ' ').trim();
                  const el = inputs.find(x => [
                    x.getAttribute('aria-label'), x.getAttribute('placeholder'),
                    x.getAttribute('name'), x.getAttribute('id'), x.title
                  ].some(v => norm(v).includes(label)));
                  if (!el) return false;
                  if (el.tagName === 'SELECT') {{
                    const option = [...el.options].find(o =>
                      norm(o.textContent) === norm(value) || norm(o.value) === norm(value) ||
                      norm(o.textContent).includes(norm(value))
                    );
                    if (!option) return false;
                    el.value = option.value;
                  }} else {{
                  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                  if (setter && el.tagName === 'INPUT') setter.call(el, value); else el.value = value;
                  }}
                  for (const type of ['input','change','blur']) el.dispatchEvent(new Event(type, {{bubbles:true}}));
                  return true;
                }})()
            """
        )

    def click_grid_row(self, contains: list[str]) -> bool:
        encoded = json.dumps(contains, ensure_ascii=False)
        return self._evaluate_until_true(
            f"""
                (() => {{
                  const terms = {encoded};
                  const docs = [document];
                  for (const frame of document.querySelectorAll('iframe,frame')) {{
                    try {{ if (frame.contentDocument) docs.push(frame.contentDocument); }} catch (_) {{}}
                  }}
                  const rows = docs.flatMap(doc => [...doc.querySelectorAll('.cl-grid-row,[role="row"],tbody tr')]);
                  const row = rows.find(el => terms.every(t => (el.innerText || '').includes(t)));
                  if (!row) return false;
                  row.click();
                  return true;
                }})()
            """
        )

    def fill_fields(self, fields: dict[str, Any]) -> dict[str, bool]:
        return {
            str(label): self.fill_label(str(label), str(value))
            for label, value in fields.items()
            if value not in (None, "")
        }

    def fill_student_request(
        self,
        request: dict[str, Any],
        mapping: dict[str, tuple[str, ...]],
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for key, value in request.items():
            if value in (None, "") or key not in mapping:
                continue
            matched = next(
                (label for label in mapping[key] if self.fill_label(label, str(value))),
                None,
            )
            result[key] = {"filled": matched is not None, "matched_label": matched}
        return result

    def snapshot(self, *, text_after: str | None = None) -> PageSnapshot:
        payloads = self._evaluate_frames(
            """
            (() => {
              const unique = (values) => [...new Set(values.filter(Boolean))];
              const lines = (text) => unique(String(text || '').split(/\\r?\\n/).map(x => x.trim()).filter(Boolean));
              const docs = [document];
              for (const frame of document.querySelectorAll('iframe,frame')) {
                try { if (frame.contentDocument) docs.push(frame.contentDocument); } catch (_) {}
              }
              const all = selector => docs.flatMap(doc => [...doc.querySelectorAll(selector)]);
              const cellText = el => String(el.innerText || el.textContent || '')
                .replace(/\\s+/g, ' ').trim();
              const grids = all('.cl-grid,table,[role="grid"]').slice(0,30).map((grid, index) => {
                const headers = unique([...grid.querySelectorAll(
                  '.cl-grid-header .cl-grid-cell,[role="columnheader"],thead th'
                )].map(cellText));
                const rows = [...grid.querySelectorAll('.cl-grid-row,[role="row"],tbody tr')]
                  .filter(row => !row.closest('.cl-grid-header') && !row.matches('[role="columnheader"]'))
                  .slice(0,300)
                  .map(row => {
                    const cells = [...row.querySelectorAll(
                      '.cl-grid-cell,[role="gridcell"],td,th,.cl-output,.cl-text'
                    )].map(cellText).filter(Boolean);
                    return cells.length ? cells : lines(cellText(row));
                  }).filter(row => row.length);
                return {
                  index,
                  headers,
                  rows,
                  lines: lines(grid.innerText).slice(0,500)
                };
              }).filter(grid => grid.lines.length);
              const buttons = unique(all('button,.cl-button,[role="button"],[role="tab"],.cl-tabfolder-item')
                .map(el => (el.innerText || el.textContent || '').trim()));
              const inputs = all('input,textarea,select').slice(0,150).map(el => ({
                tag: el.tagName.toLowerCase(),
                type: el.type || null,
                label: el.getAttribute('aria-label') || null,
                placeholder: el.getAttribute('placeholder') || null,
                name: el.getAttribute('name') || null
              }));
              const links = all('a[href]').slice(0,300).map(el => ({
                label: cellText(el),
                url: el.href
              })).filter(item => item.label && item.url);
              return {
                url: location.href,
                title: document.title,
                text: docs.map(doc => doc.body?.innerText || '').join('\\n'),
                grids,
                buttons,
                inputs,
                links
              };
            })()
            """
        )
        payloads = [payload for payload in payloads if isinstance(payload, dict)]
        payload = payloads[0] if payloads else {}
        if len(payloads) > 1:
            payload = {
                "url": payload.get("url", ""),
                "title": payload.get("title", ""),
                "text": "\n".join(str(item.get("text", "")) for item in payloads),
                "grids": [
                    grid
                    for item in payloads
                    for grid in item.get("grids", [])
                    if isinstance(grid, dict)
                ],
                "buttons": [
                    button
                    for item in payloads
                    for button in item.get("buttons", [])
                ],
                "inputs": [
                    field
                    for item in payloads
                    for field in item.get("inputs", [])
                ],
                "links": [
                    link
                    for item in payloads
                    for link in item.get("links", [])
                ],
            }
        text = _redact(str(payload.get("text", "")))
        if text_after and text_after in text:
            text = text.rsplit(text_after, 1)[-1]
        return PageSnapshot(
            url=str(payload.get("url", "")),
            title=str(payload.get("title", "")),
            text="\n".join(line for line in text.splitlines() if line.strip())[:24000],
            grids=[
                {
                    "index": grid.get("index"),
                    "headers": [_redact(str(value)) for value in grid.get("headers", [])[:100]],
                    "rows": [
                        [_redact(str(value)) for value in row[:100]]
                        for row in grid.get("rows", [])[:300]
                    ],
                    "lines": [_redact(str(value)) for value in grid.get("lines", [])[:500]],
                }
                for grid in payload.get("grids", [])[:30]
                if isinstance(grid, dict)
            ],
            buttons=[str(value) for value in payload.get("buttons", [])[:120]],
            inputs=list(payload.get("inputs", []))[:100],
            links=[
                {
                    "label": _redact(str(item.get("label", ""))),
                    "url": str(item.get("url", "")).split("#", 1)[0],
                }
                for item in payload.get("links", [])[:300]
                if isinstance(item, dict)
                and urlsplit(str(item.get("url", ""))).hostname
                in {"portal.yonsei.ac.kr", "underwood1.yonsei.ac.kr", "space.yonsei.ac.kr",
                    "icert.yonsei.ac.kr", "ys.learnus.org", "ysrollbook.yonsei.ac.kr"}
            ],
        )

    def login_state(self) -> str:
        snapshot = self.snapshot()
        lowered = snapshot.text.casefold()
        if any(marker in lowered for marker in ("로그아웃", "학사행정", "my courses", "대시보드")):
            return "connected"
        if any(marker in lowered for marker in ("portal login", "로그인", "password", "비밀번호")):
            return "login_required"
        return "unknown"


class YonseiBridge:
    """One authenticated managed browser plus command adapters."""

    def __init__(self, runtime: ChromeRuntime | None = None) -> None:
        self.runtime = runtime or ChromeRuntime()
        self.connection: CdpConnection | None = None
        self.page: BrowserPage | None = None
        self.selections: dict[str, dict[str, Any]] = {}

    def _remember_rows(
        self,
        kind: str,
        rows: list[dict[str, Any]],
        *,
        context: str = "",
    ) -> list[dict[str, Any]]:
        remembered: list[dict[str, Any]] = []
        for row in rows:
            raw = f"{kind}|{context}|{row.get('text', '')}"
            selection_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
            terms = [
                str(value)
                for value in row.get("fields", {}).values()
                if str(value).strip()
            ]
            self.selections[selection_id] = {
                "kind": kind,
                "terms": terms,
                "text": row.get("text", ""),
            }
            remembered.append({**row, "selection_id": selection_id})
        return remembered

    def _selection_terms(self, selection_id: str | None, kind: str) -> list[str] | None:
        if not selection_id:
            return None
        selected = self.selections.get(selection_id)
        if not selected or selected.get("kind") != kind:
            raise BridgeError("selection_not_found")
        return list(selected.get("terms", []))

    @staticmethod
    def _rows(snapshot: PageSnapshot) -> list[dict[str, Any]]:
        """Return stable row objects while preserving unlabelled CPR grids."""
        result: list[dict[str, Any]] = []
        for grid_index, grid in enumerate(snapshot.grids):
            headers = [str(value) for value in grid.get("headers", [])]
            for row_index, values in enumerate(grid.get("rows", [])):
                values = [str(value) for value in values]
                if headers and len(headers) == len(values):
                    fields = dict(zip(headers, values))
                else:
                    fields = {f"column_{index + 1}": value for index, value in enumerate(values)}
                result.append(
                    {
                        "grid": grid_index,
                        "row": row_index,
                        "fields": fields,
                        "text": " | ".join(values),
                    }
                )
        return result

    @staticmethod
    def _find_script(filename: str) -> Path:
        runtime_root = Path(__file__).resolve().parents[2]
        search_roots = [runtime_root, runtime_root.parent]
        matches: list[Path] = []
        for root in search_roots:
            if root.is_dir():
                matches.extend(root.glob(f"skills/**/scripts/{filename}"))
                matches.extend(root.glob(f"yonsei-*/skills/**/scripts/{filename}"))
                matches.extend(root.glob(f"learnus-*/skills/**/scripts/{filename}"))
        matches = sorted({path.resolve() for path in matches if path.is_file()})
        if not matches:
            raise BridgeError(f"Bundled helper is missing: {filename}. Reinstall the Yonsei package.")
        return matches[0]

    @staticmethod
    def _reportx_process_status() -> dict[str, Any]:
        cache = bridge_home() / "reportx"
        pid_file = cache / "bridge-agent.pid"
        try:
            pid = int(pid_file.read_text(encoding="utf-8"))
            os.kill(pid, 0)
            return {"running": True, "pid": pid, "cache": str(cache)}
        except (OSError, ValueError):
            return {"running": False, "cache": str(cache)}

    def _start_reportx_agent(self) -> dict[str, Any]:
        current = self._reportx_process_status()
        if current["running"]:
            return current
        script = self._find_script("icert_print.py")
        cache = bridge_home() / "reportx"
        cache.mkdir(parents=True, exist_ok=True)
        log_path = cache / "agent.log"
        log = log_path.open("ab")
        process = subprocess.Popen(
            [
                sys.executable,
                str(script),
                "--dir",
                str(cache),
                "agent",
                "--allow-fetch",
                "--reserve-document-number",
            ],
            cwd=str(script.parent),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        (cache / "bridge-agent.pid").write_text(str(process.pid), encoding="utf-8")
        time.sleep(0.7)
        if process.poll() is not None:
            raise BridgeError(
                "The certificate compatibility agent did not start. "
                f"Review {log_path} and reinstall if a bundled font is missing."
            )
        return {
            "running": True,
            "pid": process.pid,
            "cache": str(cache),
            "log": str(log_path),
            "endpoint": "http://127.0.0.1:65432",
        }

    def connect(self, *, visible: bool = True) -> dict[str, Any]:
        self.runtime.ensure(visible=visible)
        if self.connection is None:
            self.connection = self.runtime.open(
                PORTAL,
                reuse_hosts={
                    "portal.yonsei.ac.kr",
                    "underwood1.yonsei.ac.kr",
                    "ys.learnus.org",
                    "ysrollbook.yonsei.ac.kr",
                },
            )
            self.page = BrowserPage(self.connection)
        assert self.page is not None
        snapshot = self.page.snapshot()
        return {
            "schema": "yonsei-bridge-status/v1",
            "state": self.page.login_state(),
            "service": urlsplit(snapshot.url).hostname,
            "browser_profile": "managed-persistent",
            "credentials_collected": False,
            "next_step": "run-command" if self.page.login_state() == "connected" else "complete-login-in-open-browser",
        }

    def _page(self) -> BrowserPage:
        if self.page is None:
            self.connect()
        assert self.page is not None
        return self.page

    def _underwood(self) -> BrowserPage:
        page = self._page()
        page.navigate(UNDERWOOD, wait=2.5)
        return page

    def _open_menu(self, route: str) -> PageSnapshot:
        if route not in MENU_ROUTES:
            raise BridgeError(f"Unknown Underwood route: {route}.")
        category, item = MENU_ROUTES[route]
        page = self._underwood()
        if page.login_state() != "connected":
            raise BridgeError("login_required")
        if not page.click_text(category):
            raise BridgeError(f"Could not open Underwood category: {category}.")
        time.sleep(0.4)
        if not page.click_text(item):
            raise BridgeError(f"Could not open Underwood menu: {item}.")
        time.sleep(2.5)
        return page.snapshot(text_after=item)

    def status(self) -> dict[str, Any]:
        return self.connect()

    def today(self, *, full: bool = False) -> dict[str, Any]:
        page = self._page()
        page.navigate(PORTAL, wait=2.5)
        dashboard = page.snapshot()
        result: dict[str, Any] = {
            "schema": "yonsei-today-command/v1",
            "dashboard": dashboard.as_dict(),
            "sources": ["portal"],
            "read_only": True,
        }
        if full and page.login_state() == "connected":
            source_results: dict[str, Any] = {}
            for route in ("scholarships", "mileage", "classes", "graduation", "teaching"):
                try:
                    item = self._open_menu(route)
                    source_results[route] = {
                        "snapshot": item.as_dict(),
                        "rows": self._rows(item),
                    }
                except BridgeError as error:
                    source_results[route] = {"state": str(error)}
            result["underwood"] = source_results
            result["sources"].extend(source_results)
            for service in ("learnus", "attendance"):
                try:
                    result[service] = self.learnus_attendance(service=service)
                    result["sources"].append(service)
                except BridgeError as error:
                    result[service] = {"state": str(error)}
        return result

    def academic_applications(
        self,
        *,
        category: str = "장학",
        application: str | None = None,
    ) -> dict[str, Any]:
        if category == "장학" and application in (None, "학생장학신청"):
            snapshot = self._open_menu("scholarships")
            return {
                "schema": "yonsei-academic-applications-command/v1",
                "category": category,
                "application": "학생장학신청",
                "snapshot": snapshot.as_dict(),
                "applications": self._rows(snapshot),
                "submission_performed": False,
            }
        page = self._underwood()
        if not page.click_text(category):
            raise BridgeError(f"Could not open Underwood category: {category}.")
        time.sleep(0.5)
        category_snapshot = page.snapshot()
        if application:
            if not page.click_text(application):
                raise BridgeError(f"Could not open Underwood application: {application}.")
            time.sleep(2.0)
            category_snapshot = page.snapshot(text_after=application)
        return {
            "schema": "yonsei-academic-applications-command/v1",
            "category": category,
            "application": application,
            "snapshot": category_snapshot.as_dict(),
            "menu_items": category_snapshot.buttons,
            "applications": self._rows(category_snapshot),
            "submission_performed": False,
        }

    def mileage(self) -> dict[str, Any]:
        history = self._open_menu("mileage")
        current = self._open_menu("classes")
        return {
            "schema": "yonsei-mileage-history-command/v1",
            "history": {
                "snapshot": history.as_dict(),
                "rows": self._rows(history),
            },
            "current_registration": {
                "snapshot": current.as_dict(),
                "rows": self._rows(current),
            },
            "planning_inputs_ready": bool(self._rows(history) or self._rows(current)),
            "planning_performed": False,
            "registration_performed": False,
        }

    def graduation_teaching(self, *, include_teaching: bool = True) -> dict[str, Any]:
        earned = self._open_menu("graduation")
        audit = self._open_menu("graduation_audit")
        teaching_snapshot = self._open_menu("teaching") if include_teaching else None
        return {
            "schema": "yonsei-graduation-teaching-command/v1",
            "graduation": {
                "earned_credit": earned.as_dict(),
                "earned_credit_rows": self._rows(earned),
                "preliminary_audit": audit.as_dict(),
                "preliminary_audit_rows": self._rows(audit),
            },
            "teaching": (
                {
                    "snapshot": teaching_snapshot.as_dict(),
                    "rows": self._rows(teaching_snapshot),
                }
                if teaching_snapshot is not None
                else None
            ),
            "calculator_input": {
                "official_progress": self._rows(earned),
                "official_audit": self._rows(audit),
                "teaching_progress": self._rows(teaching_snapshot) if teaching_snapshot else [],
            },
            "official_diagnosis_triggered": False,
            "advisory_only": True,
        }

    def shuttle(
        self,
        *,
        origin: str,
        date: str,
        destination: str | None = None,
        preferred_time: str | None = None,
        depart_after: str | None = None,
        depart_before: str | None = None,
        action: str = "search",
        selection_id: str | None = None,
        row_terms: list[str] | None = None,
        reason: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        snapshot = self._open_menu("shuttle")
        page = self._page()
        if action == "cancel":
            if not page.click_text("내역/취소"):
                raise BridgeError("The official shuttle history tab was not available.")
            time.sleep(1.5)
            snapshot = page.snapshot(text_after="셔틀버스예약")
        else:
            page.click_text("예약")
            page.fill_label("출발지역", origin)
            page.fill_label("예약일자", date)
            if destination:
                page.fill_label("도착지역", destination)
            for search_label in ("조회", "검색"):
                if page.click_text(search_label):
                    break
            time.sleep(2.0)
            snapshot = page.snapshot(text_after="셔틀버스예약")
        rows = self._rows(snapshot)
        wanted_terms = [term for term in (destination,) if term]
        if preferred_time:
            wanted_terms.append(preferred_time)
        if wanted_terms:
            rows = [
                row for row in rows
                if all(term in row["text"] for term in wanted_terms)
            ]
        if depart_after:
            rows = [row for row in rows if not re.search(r"\b\d{1,2}:\d{2}\b", row["text"])
                    or re.search(r"\b\d{1,2}:\d{2}\b", row["text"]).group() >= depart_after]
        if depart_before:
            rows = [row for row in rows if not re.search(r"\b\d{1,2}:\d{2}\b", row["text"])
                    or re.search(r"\b\d{1,2}:\d{2}\b", row["text"]).group() <= depart_before]
        rows = self._remember_rows("shuttle", rows, context=f"{date}|{origin}|{destination or ''}")
        if action == "search":
            return {
                "schema": "yonsei-shuttle-command/v1",
                "action": "search",
                "snapshot": snapshot.as_dict(),
                "candidates": rows,
                "reservation_performed": False,
            }
        if action not in {"reserve", "waitlist", "cancel"}:
            raise BridgeError("Shuttle action must be search, reserve, waitlist, or cancel.")
        if not confirmed:
            return {
                "schema": "yonsei-shuttle-command/v1",
                "action": action,
                "state": "confirmation_required",
                "snapshot": snapshot.as_dict(),
                "candidates": rows,
                "reservation_performed": False,
            }
        selected_terms = self._selection_terms(selection_id, "shuttle") or row_terms
        if not selected_terms or not page.click_grid_row(selected_terms):
            raise BridgeError("The exact shuttle row could not be matched.")
        if action in {"reserve", "waitlist"}:
            if not reason:
                raise BridgeError("A reservation reason is required.")
            page.fill_label("사유", reason)
            button = "예약신청" if action == "reserve" else "대기신청"
        else:
            button = "예약취소"
        if not page.click_text(button):
            raise BridgeError(f"The official {button} button was not available.")
        time.sleep(2.0)
        verified = page.snapshot(text_after="셔틀버스예약")
        if action in {"reserve", "waitlist"}:
            page.click_text("내역/취소")
            time.sleep(1.5)
            verified = page.snapshot(text_after="셔틀버스예약")
        return {
            "schema": "yonsei-shuttle-command/v1",
            "action": action,
            "state": "verification_required",
            "official_result": verified.as_dict(),
            "official_rows": self._rows(verified),
            "write_attempted_once": True,
        }

    def space_dorm(
        self,
        *,
        service: str,
        action: str = "status",
        category: str = "기숙사",
        menu: str | None = None,
        request: dict[str, Any] | None = None,
        selection_id: str | None = None,
        fields: dict[str, Any] | None = None,
        row_terms: list[str] | None = None,
        submit_button: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        if service == "space":
            page = self._page()
            page.navigate(SPACE, wait=2.5)
            snapshot = page.snapshot()
        elif service == "dorm":
            page = self._underwood()
            if not page.click_text(category):
                raise BridgeError(f"Could not open Underwood category: {category}.")
            time.sleep(0.5)
            if menu:
                if not page.click_text(menu):
                    raise BridgeError(f"Could not open dorm menu: {menu}.")
                time.sleep(2.0)
            snapshot = page.snapshot(text_after=menu)
        else:
            raise BridgeError("service must be space or dorm.")
        request = request or {}
        mapping = SPACE_REQUEST_FIELDS if service == "space" else DORM_REQUEST_FIELDS
        if action == "status":
            search_keys = {
                "date",
                "start_time",
                "end_time",
                "headcount",
                "building",
                "equipment",
                "campus",
                "dorm",
                "facility",
            }
            search_request = {
                key: value for key, value in request.items() if key in search_keys
            }
            student_filled = page.fill_student_request(search_request, mapping)
            for label in ("조회", "검색"):
                if page.click_text(label):
                    time.sleep(1.5)
                    break
            snapshot = page.snapshot(text_after=menu)
            rows = self._remember_rows(service, self._rows(snapshot))
            return {
                "schema": "yonsei-space-dorm-command/v1",
                "service": service,
                "snapshot": snapshot.as_dict(),
                "rows": rows,
                "accepted_input": {
                    key: value.get("filled", False)
                    for key, value in student_filled.items()
                },
                "action_performed": False,
            }
        selected_terms = self._selection_terms(selection_id, service) or row_terms
        if not selected_terms:
            selected_terms = [
                str(request[key])
                for key in ("space_name", "building", "dorm", "facility")
                if request.get(key)
            ]
        if selected_terms and not page.click_grid_row(selected_terms):
            raise BridgeError("The exact reviewed space or dorm row could not be matched.")
        if selected_terms:
            time.sleep(0.5)
        student_filled = page.fill_student_request(request, mapping)
        advanced_filled = page.fill_fields(fields or {})
        failed_student_fields = [
            key for key, value in student_filled.items() if not value.get("filled")
        ]
        failed_advanced_fields = [
            key for key, value in advanced_filled.items() if not value
        ]
        if failed_student_fields or failed_advanced_fields:
            return {
                "schema": "yonsei-space-dorm-command/v1",
                "service": service,
                "action": action,
                "state": "field_mapping_required",
                "unmatched_fields": failed_student_fields + failed_advanced_fields,
                "snapshot": page.snapshot(text_after=menu).as_dict(),
                "action_performed": False,
            }
        prepared = page.snapshot(text_after=menu)
        if not confirmed:
            return {
                "schema": "yonsei-space-dorm-command/v1",
                "service": service,
                "action": action,
                "state": "confirmation_required",
                "review": {
                    key: value
                    for key, value in request.items()
                    if value not in (None, "")
                },
                "snapshot": prepared.as_dict(),
                "action_performed": False,
            }
        button = submit_button or {
            "apply": "신청",
            "reserve": "예약",
            "submit": "제출",
            "cancel": "취소",
        }.get(action, action)
        if not page.click_text(button):
            raise BridgeError(f"The exact official action button was not available: {button}.")
        time.sleep(2.0)
        verified = page.snapshot(text_after=menu)
        return {
            "schema": "yonsei-space-dorm-command/v1",
            "service": service,
            "action": action,
            "state": "official_result_returned",
            "official_result": verified.as_dict(),
            "official_rows": self._rows(verified),
            "action_performed": True,
            "write_attempted_once": True,
        }

    def documents(
        self,
        *,
        document_type: str,
        action: str = "open",
        output_format: str = "pdf",
        language: str | None = None,
        copies: int | None = None,
        purpose: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        page = self._page()
        if document_type in {"certificate", "enrollment", "transcript"}:
            page.navigate(ICERT, wait=2.5)
        elif document_type in {"education_practicum", "teaching"}:
            snapshot = self.academic_applications(category="교직", application="교육실습참가확인서출력")
            runtime = (
                self._start_reportx_agent()
                if action == "issue" and confirmed and platform.system() in {"Darwin", "Linux"}
                else {
                    "mode": "official-reportx" if platform.system() == "Windows" else "open-only"
                }
            )
            return {
                "schema": "yonsei-document-command/v1",
                "document_type": document_type,
                "state": (
                    "confirmation_required"
                    if action == "issue" and not confirmed
                    else "official_document_route_ready"
                ),
                "snapshot": snapshot["snapshot"],
                "runtime": runtime,
                "issuance_performed": False,
                "font_verification_required": action == "issue",
            }
        else:
            page.navigate(PORTAL, wait=2.5)
        visible_document = DOCUMENT_LABELS.get(document_type)
        if visible_document:
            page.click_text(visible_document, exact=False)
        if language:
            normalized_language = {
                "ko": "국문",
                "korean": "국문",
                "en": "영문",
                "english": "영문",
            }.get(language.casefold(), language)
            if not page.fill_label("언어", normalized_language):
                page.click_text(normalized_language, exact=False)
        if copies is not None:
            page.fill_label("매수", str(copies))
        if purpose:
            page.fill_label("용도", purpose)
        snapshot = page.snapshot()
        if action == "issue" and not confirmed:
            return {
                "schema": "yonsei-document-command/v1",
                "document_type": document_type,
                "state": "confirmation_required",
                "review": {
                    "document_type": document_type,
                    "language": language,
                    "copies": copies,
                    "purpose": purpose,
                    "output_format": output_format,
                },
                "snapshot": snapshot.as_dict(),
                "issuance_performed": False,
                "font_verification_required": True,
            }
        system = platform.system()
        runtime: dict[str, Any]
        if action == "issue" and system in {"Darwin", "Linux"}:
            runtime = self._start_reportx_agent()
            state = "reportx_agent_ready"
        elif action == "issue" and system == "Windows":
            runtime = {"mode": "official-reportx", "running": None}
            state = "official_reportx_ready"
        else:
            runtime = {"mode": "open-only"}
            state = "official_page_ready"
        return {
            "schema": "yonsei-document-command/v1",
            "document_type": document_type,
            "state": state,
            "review": {
                "document_type": document_type,
                "language": language,
                "copies": copies,
                "purpose": purpose,
                "output_format": output_format,
            },
            "snapshot": snapshot.as_dict(),
            "runtime": runtime,
            "output_format": output_format,
            "issuance_performed": False,
            "next_step": (
                "choose-the-document-in-the-open-official-page"
                if action == "issue"
                else "review-the-official-document-route"
            ),
            "font_verification_required": action == "issue",
        }

    def learnus_attendance(self, *, service: str) -> dict[str, Any]:
        page = self._page()
        if service == "learnus":
            page.navigate(LEARNUS, wait=3.0)
        elif service == "attendance":
            page.navigate(ATTENDANCE, wait=3.0)
        else:
            raise BridgeError("service must be learnus or attendance.")
        snapshot = page.snapshot()
        rows = self._rows(snapshot)
        courses = [
            link for link in snapshot.links
            if service == "learnus" and "/course/view.php" in link["url"]
        ]
        return {
            "schema": "yonsei-learning-attendance-command/v1",
            "service": service,
            "state": page.login_state(),
            "snapshot": snapshot.as_dict(),
            "courses": courses,
            "rows": rows,
            "read_only": True,
            "attendance_check_in_performed": False,
        }

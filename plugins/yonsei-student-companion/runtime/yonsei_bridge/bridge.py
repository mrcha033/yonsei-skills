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
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from yonsei_bridge.cdp import BridgeError, CdpConnection, ChromeRuntime
else:
    from .cdp import BridgeError, CdpConnection, ChromeRuntime


PORTAL = "https://portal.yonsei.ac.kr/ui/index.html"
UNDERWOOD = "https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/initPageWork.do"
COURSE_CATALOG = (
    "https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/"
    "initExtPageWork.do?link=handbList&locale=ko"
)
SPACE = "https://space.yonsei.ac.kr/"
LEARNUS = "https://ys.learnus.org/my/"
ATTENDANCE = "https://ysrollbook.yonsei.ac.kr/"


def certificate_cache() -> Path:
    """Return the one cache shared with the bundled certificate runtime."""

    return Path.home() / ".cache" / "yonsei-certificate-assistant"


MENU_ROUTES = {
    "scholarships": ("장학", "학생장학신청"),
    "handbook": ("수업", "수강편람"),
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


def _normalized_value(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _requested_value_matches(requested: Any, actual: Any) -> bool:
    wanted = _normalized_value(requested)
    observed = _normalized_value(actual)
    if not wanted or not observed:
        return False
    wanted_digits = re.sub(r"\D", "", wanted)
    observed_digits = re.sub(r"\D", "", observed)
    if len(wanted_digits) == 8 and len(observed_digits) == 8:
        return wanted_digits == observed_digits
    if re.fullmatch(r"\d{1,2}:\d{2}", wanted) and re.fullmatch(
        r"\d{1,2}:\d{2}", observed
    ):
        wanted_hour, wanted_minute = (int(part) for part in wanted.split(":"))
        observed_hour, observed_minute = (int(part) for part in observed.split(":"))
        return (wanted_hour, wanted_minute) == (observed_hour, observed_minute)
    return wanted == observed or wanted in observed or observed in wanted


def _redact(text: str) -> str:
    text = re.sub(r"\b\d{8,12}\b", "[redacted]", text)
    text = re.sub(r"학생\([^)]*\)\s*[^\n]*", "학생", text)
    text = re.sub(r"(?m)^[^\n]{1,24}\s+님\s*$", "[student]", text)
    text = re.sub(
        r"(?m)^[^\n]{1,24}\s+님이\s+로그인(?:\s+하셨습니다\.?)?",
        "[student] 로그인",
        text,
    )
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
                    'button,a,label,[role="button"],[role="tab"],[role="option"],'
                    + '.cl-button,.cl-tabfolder-item,.cl-combobox-item,.cl-grid-row'
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

    def click_href_fragment(self, fragment: str) -> bool:
        """Click one official link whose literal href contains a safe fragment."""
        return self._evaluate_until_true(
            f"""
                (() => {{
                  const fragment = {json.dumps(fragment, ensure_ascii=False)};
                  const link = [...document.querySelectorAll('a[href]')]
                    .find(el => (el.getAttribute('href') || '').includes(fragment));
                  if (!link) return false;
                  link.click();
                  return true;
                }})()
            """
        )

    def _click_point(self, x: float, y: float) -> None:
        for event_type in ("mousePressed", "mouseReleased"):
            self.connection.command(
                "Input.dispatchMouseEvent",
                {
                    "type": event_type,
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                },
            )

    def select_after_label(self, label: str, value: str, *, index: int = 0) -> bool:
        """Choose a CPR combobox adjacent to a visible student-facing label."""
        geometry_expression = f"""
            (() => {{
              const wanted = {json.dumps(label, ensure_ascii=False)};
              const index = {index};
              const topPoint = rect => {{
                let x = rect.x + rect.width / 2;
                let y = rect.y + rect.height / 2;
                let current = window;
                try {{
                  while (current.frameElement) {{
                    const frameRect = current.frameElement.getBoundingClientRect();
                    x += frameRect.x;
                    y += frameRect.y;
                    current = current.parent;
                  }}
                }} catch (_) {{}}
                return {{x, y}};
              }};
              const labels = [...document.querySelectorAll('.label_search,.cl-output')]
                .filter(el => (el.innerText || el.textContent || '').trim() === wanted);
              for (const label of labels) {{
                const container = label.nextElementSibling;
                if (!container) continue;
                const combos = [
                  ...(container.matches('.cl-combobox') ? [container] : []),
                  ...container.querySelectorAll('.cl-combobox')
                ];
                const combo = combos[index];
                const button = combo?.querySelector('.cl-combobox-button');
                if (!button) continue;
                const rect = button.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {{
                  return topPoint(rect);
                }}
              }}
              return null;
            }})()
        """
        geometry = next(
            (
                value
                for value in self._evaluate_frames(geometry_expression)
                if isinstance(value, dict) and "x" in value and "y" in value
            ),
            None,
        )
        if geometry is None:
            return False
        self._click_point(float(geometry["x"]), float(geometry["y"]))
        time.sleep(0.2)
        option_expression = f"""
            (() => {{
              const wanted = {json.dumps(value, ensure_ascii=False)};
              const norm = text => String(text || '').replace(/\\s+/g, ' ').trim();
              const topPoint = rect => {{
                let x = rect.x + rect.width / 2;
                let y = rect.y + rect.height / 2;
                let current = window;
                try {{
                  while (current.frameElement) {{
                    const frameRect = current.frameElement.getBoundingClientRect();
                    x += frameRect.x;
                    y += frameRect.y;
                    current = current.parent;
                  }}
                }} catch (_) {{}}
                return {{x, y}};
              }};
              const visible = el => {{
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden'
                  && rect.width > 0 && rect.height > 0;
              }};
              const options = [...document.querySelectorAll(
                '[role="option"],.cl-combobox-item'
              )].filter(visible);
              const option = options.find(el => norm(el.innerText) === norm(wanted))
                || options.find(el => norm(el.innerText).includes(norm(wanted)))
                || options.find(el => norm(wanted).includes(norm(el.innerText)));
              if (!option) return null;
              const rect = option.getBoundingClientRect();
              return topPoint(rect);
            }})()
        """
        option = next(
            (
                value
                for value in self._evaluate_frames(option_expression)
                if isinstance(value, dict) and "x" in value and "y" in value
            ),
            None,
        )
        if option is None:
            return False
        self._click_point(float(option["x"]), float(option["y"]))
        time.sleep(0.4)
        return True

    def type_after_label(self, label: str, value: str, *, index: int = 0) -> bool:
        """Type into an input adjacent to a visible label using real input events."""
        focus_expression = f"""
            (() => {{
              const wanted = {json.dumps(label, ensure_ascii=False)};
              const index = {index};
              const label = [...document.querySelectorAll('.label_search,.cl-output')]
                .find(el => (el.innerText || el.textContent || '').trim() === wanted);
              const input = label?.nextElementSibling?.querySelectorAll('input,textarea')[index];
              if (!input) return false;
              input.focus();
              if (typeof input.select === 'function') input.select();
              return true;
            }})()
        """
        if not self._evaluate_until_true(focus_expression):
            return False
        self.connection.command("Input.insertText", {"text": value})
        self._evaluate_until_true(
            f"""
                (() => {{
                  const wanted = {json.dumps(label, ensure_ascii=False)};
                  const index = {index};
                  const label = [...document.querySelectorAll('.label_search,.cl-output')]
                    .find(el => (el.innerText || el.textContent || '').trim() === wanted);
                  const input = label?.nextElementSibling?.querySelectorAll('input,textarea')[index];
                  if (!input) return false;
                  for (const type of ['input','keyup','change','blur']) {{
                    input.dispatchEvent(new Event(type, {{bubbles: true}}));
                  }}
                  input.blur();
                  return true;
                }})()
            """
        )
        return True

    def values_after_labels(self, labels: list[str]) -> dict[str, list[str]]:
        encoded = json.dumps(labels, ensure_ascii=False)
        payloads = self._evaluate_frames(
            f"""
                (() => {{
                  const labels = {encoded};
                  const result = {{}};
                  for (const wanted of labels) {{
                    const label = [...document.querySelectorAll('.label_search,.cl-output')]
                      .find(el => (el.innerText || el.textContent || '').trim() === wanted);
                    if (!label?.nextElementSibling) continue;
                    result[wanted] = [...label.nextElementSibling.querySelectorAll('input,textarea')]
                      .map(input => input.value).filter(Boolean);
                  }}
                  return result;
                }})()
            """
        )
        for payload in payloads:
            if isinstance(payload, dict) and payload:
                return {
                    str(key): [str(item) for item in values]
                    for key, values in payload.items()
                    if isinstance(values, list)
                }
        return {}

    def field_value_matches(self, label: str, requested: Any) -> bool:
        """Verify that a requested value survived the page component's own state."""
        payloads = self._evaluate_frames(
            f"""
                (() => {{
                  const wanted = {json.dumps(label, ensure_ascii=False)};
                  const norm = value => String(value || '').replace(/\\s+/g, ' ').trim();
                  const result = [];
                  const add = element => {{
                    if (!element) return;
                    if (element.tagName === 'SELECT') {{
                      result.push(element.value);
                      for (const option of element.selectedOptions || []) {{
                        result.push(option.textContent);
                      }}
                    }} else {{
                      result.push(element.value);
                    }}
                  }};
                  for (const element of document.querySelectorAll('input,textarea,select')) {{
                    const labels = [
                      element.getAttribute('aria-label'), element.getAttribute('placeholder'),
                      element.getAttribute('name'), element.getAttribute('id'), element.title
                    ];
                    if (labels.some(value => norm(value).includes(wanted))) add(element);
                  }}
                  for (const visibleLabel of document.querySelectorAll('.label_search,.cl-output')) {{
                    const text = norm(visibleLabel.innerText || visibleLabel.textContent);
                    if (text !== wanted && !text.includes(wanted)) continue;
                    for (const element of visibleLabel.nextElementSibling?.querySelectorAll(
                      'input,textarea,select'
                    ) || []) add(element);
                  }}
                  return [...new Set(result.map(norm).filter(Boolean))];
                }})()
            """
        )
        values = [
            value
            for payload in payloads
            if isinstance(payload, list)
            for value in payload
        ]
        return any(_requested_value_matches(requested, value) for value in values)

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

    def select_radio(self, name: str, value: str) -> bool:
        """Select one exact radio option and verify the browser-owned state."""
        return self._evaluate_until_true(
            f"""
                (() => {{
                  const name = {json.dumps(name, ensure_ascii=False)};
                  const value = {json.dumps(value, ensure_ascii=False)};
                  const radio = [...document.querySelectorAll('input[type="radio"]')]
                    .find(el => el.name === name && el.value === value);
                  if (!radio || radio.disabled) return false;
                  radio.click();
                  radio.dispatchEvent(new Event('change', {{bubbles: true}}));
                  return radio.checked === true;
                }})()
            """
        )

    def select_radio_in_row(
        self,
        *,
        name: str,
        contains: list[str],
        skip: int = 0,
    ) -> bool:
        """Select the first matching official table row without reading values."""
        return self._evaluate_until_true(
            f"""
                (() => {{
                  const name = {json.dumps(name, ensure_ascii=False)};
                  const terms = {json.dumps(contains, ensure_ascii=False)};
                  const skip = {int(skip)};
                  const normalize = value => String(value || '')
                    .replace(/\\s+/g, ' ').trim();
                  const radios = [...document.querySelectorAll('input[type="radio"]')]
                    .filter(el => el.name === name && !el.disabled);
                  const matches = radios.filter(el => {{
                    const row = normalize(el.closest('tr')?.innerText);
                    return terms.every(term => row.includes(normalize(term)));
                  }});
                  const radio = matches[skip];
                  if (!radio) return false;
                  radio.click();
                  radio.dispatchEvent(new Event('change', {{bubbles: true}}));
                  return radio.checked === true;
                }})()
            """
        )

    def certificate_basket_rows(
        self,
        *,
        document_label: str,
        language_label: str,
        copies: int,
    ) -> list[dict[str, Any]]:
        """Return only exact, currently printable certificate basket rows."""

        payloads = self._evaluate_frames(
            f"""
                (() => {{
                  const documentLabel = {json.dumps(document_label, ensure_ascii=False)};
                  const languageLabel = {json.dumps(language_label, ensure_ascii=False)};
                  const copies = {int(copies)};
                  const normalize = value => String(value || '')
                    .replace(/\\s+/g, ' ').trim();
                  const identityFor = (radio, row) => {{
                    const actions = [...row.querySelectorAll('a[href]')]
                      .map(link => link.getAttribute('href') || '')
                      .filter(href => /detail_del|goPrint|Basket|Request/i.test(href))
                      .sort();
                    return JSON.stringify({{
                      id: radio.id || '',
                      name: radio.name || '',
                      value: radio.value || '',
                      onclick: radio.getAttribute('onclick') || '',
                      actions,
                      text: normalize(row.innerText || row.textContent),
                    }});
                  }};
                  return [...document.querySelectorAll('input[type="radio"][name="RB"]')]
                    .map((radio, index) => {{
                      const row = radio.closest('tr');
                      if (!row || radio.disabled) return null;
                      const text = normalize(row.innerText || row.textContent);
                      if (!text.includes(documentLabel) || !text.includes(languageLabel)) return null;
                      if (text.includes('출력불가')) return null;
                      const count = text.match(/(\\d+)\\s*매(?:\\s*\\/\\s*(\\d+)\\s*매)?/);
                      const requested = count ? Number(count[1]) : null;
                      if (requested !== null && requested !== copies) return null;
                      return {{
                        portal_key: identityFor(radio, row),
                        requested_copies: requested,
                        output_available: text.includes('출력가능') || !text.includes('출력불가'),
                      }};
                    }})
                    .filter(Boolean);
                }})()
            """
        )
        rows = [
            row
            for payload in payloads
            if isinstance(payload, list)
            for row in payload
            if isinstance(row, dict)
            and isinstance(row.get("portal_key"), str)
            and row.get("portal_key")
        ]
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            raw_key = str(row.pop("portal_key"))
            portal_id = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            row["portal_id"] = portal_id
            # The raw DOM locator is used only in this in-process selection.
            # Never persist it or include it in a command result.
            row["_portal_key"] = raw_key
            unique[portal_id] = row
        return list(unique.values())

    def select_certificate_basket_row(
        self,
        *,
        portal_key: str,
        document_label: str,
        language_label: str,
    ) -> bool:
        """Select one stable basket row and reject a non-unique identity."""

        return self._evaluate_until_true(
            f"""
                (() => {{
                  const wanted = {json.dumps(portal_key, ensure_ascii=False)};
                  const documentLabel = {json.dumps(document_label, ensure_ascii=False)};
                  const languageLabel = {json.dumps(language_label, ensure_ascii=False)};
                  const normalize = value => String(value || '')
                    .replace(/\\s+/g, ' ').trim();
                  const identityFor = (radio, row) => {{
                    const actions = [...row.querySelectorAll('a[href]')]
                      .map(link => link.getAttribute('href') || '')
                      .filter(href => /detail_del|goPrint|Basket|Request/i.test(href))
                      .sort();
                    return JSON.stringify({{
                      id: radio.id || '',
                      name: radio.name || '',
                      value: radio.value || '',
                      onclick: radio.getAttribute('onclick') || '',
                      actions,
                      text: normalize(row.innerText || row.textContent),
                    }});
                  }};
                  const matches = [...document.querySelectorAll(
                    'input[type="radio"][name="RB"]'
                  )].filter((radio, index) => {{
                    const row = radio.closest('tr');
                    if (!row || radio.disabled) return false;
                    const text = normalize(row.innerText || row.textContent);
                    return text.includes(documentLabel)
                      && text.includes(languageLabel)
                      && identityFor(radio, row) === wanted;
                  }});
                  if (matches.length !== 1) return false;
                  matches[0].click();
                  matches[0].dispatchEvent(new Event('change', {{bubbles: true}}));
                  return matches[0].checked === true;
                }})()
            """
        )

    def set_certificate_count(
        self,
        *,
        document_label: str,
        language_label: str,
        copies: int,
    ) -> bool:
        """Set one certificate count and clear every other count on YSCT."""
        focused = self._evaluate_until_true(
            f"""
                (() => {{
                  const documentLabel = {json.dumps(document_label, ensure_ascii=False)};
                  const languageLabel = {json.dumps(language_label, ensure_ascii=False)};
                  const copies = {int(copies)};
                  const normalize = value => String(value || '')
                    .replace(/\\s+/g, ' ').trim();
                  const counts = [...document.querySelectorAll(
                    'input[type="text"][name^="min_cnt"]'
                  )];
                  const target = counts.find(input => {{
                    const row = normalize(input.closest('tr')?.innerText);
                    return row.includes(documentLabel) && row.includes(languageLabel);
                  }});
                  if (!target) return false;
                  const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value'
                  )?.set;
                  for (const input of counts) {{
                    if (setter) setter.call(input, '');
                    else input.value = '';
                    for (const type of ['input','change','blur']) {{
                      input.dispatchEvent(new Event(type, {{bubbles: true}}));
                    }}
                  }}
                  target.focus();
                  if (typeof target.select === 'function') target.select();
                  return document.activeElement === target;
                }})()
            """
        )
        if not focused:
            return False
        self.connection.command("Input.insertText", {"text": str(copies)})
        return self._evaluate_until_true(
            f"""
                (() => {{
                  const documentLabel = {json.dumps(document_label, ensure_ascii=False)};
                  const languageLabel = {json.dumps(language_label, ensure_ascii=False)};
                  const copies = {int(copies)};
                  const normalize = value => String(value || '')
                    .replace(/\\s+/g, ' ').trim();
                  const counts = [...document.querySelectorAll(
                    'input[type="text"][name^="min_cnt"]'
                  )];
                  const target = counts.find(input => {{
                    const row = normalize(input.closest('tr')?.innerText);
                    return row.includes(documentLabel) && row.includes(languageLabel);
                  }});
                  if (!target) return false;
                  target.dispatchEvent(new KeyboardEvent(
                    'keyup', {{key: String(copies), bubbles: true}}
                  ));
                  target.dispatchEvent(new Event('input', {{bubbles: true}}));
                  target.dispatchEvent(new Event('change', {{bubbles: true}}));
                  target.blur();
                  return target.value === String(copies)
                    && counts.filter(input => input !== target)
                      .every(input => input.value === '');
                }})()
            """
        )

    def configure_certificate_request(
        self,
        *,
        document_label: str,
        language_label: str,
        copies: int,
        include_rank: bool,
        gpa_conversion: bool,
        gpa_scale: str | None,
    ) -> bool:
        """Configure one certificate row, including transcript-only options.

        The certificate table uses a row-spanned document cell, so an English
        row does not necessarily repeat the document name in ``innerText``.
        Resolve the row from that span and change only controls owned by the
        requested language row.  This avoids the former global first-checkbox
        behavior that could apply a transcript option to the Korean row.
        """

        normalized_scale = str(gpa_scale or "").strip()
        if gpa_conversion and normalized_scale != "4.5":
            raise BridgeError("certificate_gpa_scale_must_be_4.5")
        if not gpa_conversion and normalized_scale:
            raise BridgeError("certificate_gpa_conversion_scale_mismatch")
        focused = self._evaluate_until_true(
            f"""
                (() => {{
                  const documentLabel = {json.dumps(document_label, ensure_ascii=False)};
                  const languageLabel = {json.dumps(language_label, ensure_ascii=False)};
                  const normalize = value => String(value || '')
                    .replace(/\\s+/g, ' ').trim();
                  const rows = [...document.querySelectorAll('table tr')];
                  const startIndex = rows.findIndex(row =>
                    [...row.querySelectorAll('th,td')].some(cell =>
                      normalize(cell.innerText || cell.textContent).includes(documentLabel)
                    ) && row.querySelector('input[type="text"][name^="min_cnt"]')
                  );
                  if (startIndex < 0) return false;
                  const start = rows[startIndex];
                  const owner = [...start.querySelectorAll('th,td')].find(cell =>
                    normalize(cell.innerText || cell.textContent).includes(documentLabel)
                  );
                  const span = Math.max(1, Number(owner?.rowSpan || 1));
                  const ownedRows = rows.slice(startIndex, startIndex + span);
                  const targetRows = ownedRows.filter(row => {{
                    const text = normalize(row.innerText || row.textContent);
                    return text.includes(languageLabel)
                      && row.querySelector('input[type="text"][name^="min_cnt"]');
                  }});
                  if (targetRows.length !== 1) return false;
                  const target = targetRows[0].querySelector(
                    'input[type="text"][name^="min_cnt"]'
                  );
                  if (!target || target.disabled) return false;
                  const counts = [...document.querySelectorAll(
                    'input[type="text"][name^="min_cnt"]'
                  )];
                  const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value'
                  )?.set;
                  for (const input of counts) {{
                    if (setter) setter.call(input, '');
                    else input.value = '';
                    for (const type of ['input','change','blur']) {{
                      input.dispatchEvent(new Event(type, {{bubbles: true}}));
                    }}
                  }}
                  target.focus();
                  if (typeof target.select === 'function') target.select();
                  return document.activeElement === target;
                }})()
            """
        )
        if not focused:
            return False
        self.connection.command("Input.insertText", {"text": str(copies)})
        return self._evaluate_until_true(
            f"""
                (() => {{
                  const documentLabel = {json.dumps(document_label, ensure_ascii=False)};
                  const languageLabel = {json.dumps(language_label, ensure_ascii=False)};
                  const copies = {int(copies)};
                  const includeRank = {json.dumps(bool(include_rank))};
                  const includeConversion = {json.dumps(bool(gpa_conversion))};
                  const normalize = value => String(value || '')
                    .replace(/\\s+/g, ' ').trim();
                  const rows = [...document.querySelectorAll('table tr')];
                  const startIndex = rows.findIndex(row =>
                    [...row.querySelectorAll('th,td')].some(cell =>
                      normalize(cell.innerText || cell.textContent).includes(documentLabel)
                    ) && row.querySelector('input[type="text"][name^="min_cnt"]')
                  );
                  if (startIndex < 0) return false;
                  const start = rows[startIndex];
                  const owner = [...start.querySelectorAll('th,td')].find(cell =>
                    normalize(cell.innerText || cell.textContent).includes(documentLabel)
                  );
                  const span = Math.max(1, Number(owner?.rowSpan || 1));
                  const targetRows = rows.slice(startIndex, startIndex + span)
                    .filter(row => {{
                      const text = normalize(row.innerText || row.textContent);
                      return text.includes(languageLabel)
                        && row.querySelector('input[type="text"][name^="min_cnt"]');
                    }});
                  if (targetRows.length !== 1) return false;
                  const row = targetRows[0];
                  const target = row.querySelector(
                    'input[type="text"][name^="min_cnt"]'
                  );
                  const labelFor = box => normalize(
                    box.getAttribute('aria-label')
                    || box.getAttribute('title')
                    || (box.id && document.querySelector(
                      `label[for="${{CSS.escape(box.id)}}"]`
                    )?.innerText)
                    || box.closest('label')?.innerText
                    || box.parentElement?.innerText
                  );
                  const boxes = [...row.querySelectorAll('input[type="checkbox"]')];
                  const rank = boxes.filter(box => labelFor(box).includes('석차표기'));
                  const conversion = boxes.filter(box =>
                    labelFor(box).includes('4.5 환산 표기 추가')
                  );
                  if (documentLabel === '성적증명서'
                      && (rank.length !== 1 || conversion.length !== 1)) return false;
                  const setChecked = (box, wanted) => {{
                    if (!box || box.disabled) return box ? box.checked === wanted : !wanted;
                    const setter = Object.getOwnPropertyDescriptor(
                      HTMLInputElement.prototype, 'checked'
                    )?.set;
                    if (setter) setter.call(box, wanted);
                    else box.checked = wanted;
                    for (const type of ['input','change','blur']) {{
                      box.dispatchEvent(new Event(type, {{bubbles: true}}));
                    }}
                    return box.checked === wanted;
                  }};
                  target.dispatchEvent(new KeyboardEvent(
                    'keyup', {{key: String(copies), bubbles: true}}
                  ));
                  target.dispatchEvent(new Event('input', {{bubbles: true}}));
                  target.dispatchEvent(new Event('change', {{bubbles: true}}));
                  target.blur();
                  const countIsExact = target.value === String(copies)
                    && [...document.querySelectorAll(
                      'input[type="text"][name^="min_cnt"]'
                    )].filter(input => input !== target)
                      .every(input => input.value === '');
                  return countIsExact
                    && setChecked(rank[0], includeRank)
                    && setChecked(conversion[0], includeConversion);
                }})()
            """
        )

    def select_only_nonempty_option(self, name: str) -> bool:
        """Select a sole official option, otherwise leave the choice to the user."""
        return self._evaluate_until_true(
            f"""
                (() => {{
                  const select = [...document.querySelectorAll('select')]
                    .find(el => el.name === {json.dumps(name, ensure_ascii=False)});
                  if (!select) return false;
                  const options = [...select.options].filter(option => option.value);
                  if (options.length !== 1) return false;
                  select.value = options[0].value;
                  for (const type of ['input','change','blur']) {{
                    select.dispatchEvent(new Event(type, {{bubbles: true}}));
                  }}
                  return select.value === options[0].value;
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
            matched = None
            for label in mapping[key]:
                if not self.fill_label(label, str(value)):
                    continue
                if hasattr(self, "connection") and not self.field_value_matches(label, value):
                    continue
                matched = label
                break
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
        host = urlsplit(snapshot.url).hostname
        password_input = any(
            str(field.get("type", "")).casefold() == "password"
            for field in snapshot.inputs
            if isinstance(field, dict)
        )
        if password_input or (
            host == "infra.yonsei.ac.kr"
            and "로그인" in snapshot.title
        ):
            return "login_required"
        if (
            host in {"portal.yonsei.ac.kr", "underwood1.yonsei.ac.kr"}
            and not snapshot.text.strip()
            and not snapshot.buttons
            and not snapshot.inputs
        ):
            return "login_required"
        if any(marker in lowered for marker in ("로그아웃", "학사행정", "my courses", "대시보드")):
            return "connected"
        if any(marker in lowered for marker in ("portal login", "로그인", "password", "비밀번호")):
            return "login_required"
        return "unknown"

    def wait_for_login_state(self, *, timeout: float = 6.0) -> str:
        """Allow SSO frames to settle before classifying the saved session."""
        deadline = time.monotonic() + timeout
        login_required_since: float | None = None
        last_state = "unknown"
        while time.monotonic() < deadline:
            last_state = self.login_state()
            if last_state == "connected":
                return last_state
            if last_state == "login_required":
                if login_required_since is None:
                    login_required_since = time.monotonic()
                elif time.monotonic() - login_required_since >= 1.5:
                    return last_state
            else:
                login_required_since = None
            time.sleep(0.2)
        return last_state


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
        self.selections = {
            selection_id: selected
            for selection_id, selected in self.selections.items()
            if selected.get("kind") != kind
        }
        remembered: list[dict[str, Any]] = []
        for row in rows:
            raw = f"{kind}|{context}|{row.get('text', '')}"
            selection_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
            stable_terms = [
                str(value)
                for label, value in row.get("fields", {}).items()
                if str(value).strip()
                and not any(
                    marker in str(label)
                    for marker in ("잔여", "좌석", "대기", "예약가능", "상태", "인원")
                )
            ]
            terms = stable_terms or [
                str(value)
                for value in row.get("fields", {}).values()
                if str(value).strip()
            ]
            self.selections[selection_id] = {
                "kind": kind,
                "terms": terms,
                "text": row.get("text", ""),
                "context": context,
            }
            remembered.append({**row, "selection_id": selection_id})
        return remembered

    def _selection(
        self,
        selection_id: str | None,
        kind: str,
        *,
        context: str | None = None,
        consume: bool = False,
    ) -> dict[str, Any] | None:
        if not selection_id:
            return None
        selected = self.selections.get(selection_id)
        if (
            not selected
            or selected.get("kind") != kind
            or (context is not None and selected.get("context") != context)
        ):
            raise BridgeError("selection_not_found")
        if consume:
            self.selections.pop(selection_id, None)
        return dict(selected)

    def _selection_terms(
        self,
        selection_id: str | None,
        kind: str,
        *,
        context: str | None = None,
        consume: bool = False,
    ) -> list[str] | None:
        selected = self._selection(
            selection_id,
            kind,
            context=context,
            consume=consume,
        )
        return list(selected.get("terms", [])) if selected else None

    @staticmethod
    def _rows_match_terms(
        rows: list[dict[str, Any]],
        terms: list[str],
    ) -> bool:
        normalized_terms = [_normalized_value(term) for term in terms if str(term).strip()]
        return bool(normalized_terms) and any(
            all(term in _normalized_value(row.get("text", "")) for term in normalized_terms)
            for row in rows
        )

    @staticmethod
    def _success_marker(action: str, snapshot: PageSnapshot) -> bool:
        text = _normalized_value(snapshot.text)
        markers = {
            "reserve": ("예약 완료", "예약되었습니다", "정상적으로 예약"),
            "waitlist": ("대기 신청 완료", "대기신청되었습니다", "정상적으로 대기"),
            "apply": ("신청 완료", "신청되었습니다", "정상적으로 신청"),
            "submit": ("제출 완료", "제출되었습니다", "정상적으로 제출"),
            "cancel": ("취소 완료", "취소되었습니다", "정상적으로 취소"),
        }.get(action, ())
        return any(_normalized_value(marker) in text for marker in markers)

    @staticmethod
    def _fill_verified(page: BrowserPage, label: str, value: Any) -> bool:
        if not page.fill_label(label, str(value)):
            return False
        verifier = getattr(page, "field_value_matches", None)
        return bool(verifier(label, value)) if callable(verifier) else True

    @staticmethod
    def _clock_minutes(value: str) -> int:
        match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value)
        if not match:
            raise BridgeError(f"Invalid time: {value}. Use HH:MM.")
        hour, minute = (int(part) for part in match.groups())
        if hour > 23 or minute > 59:
            raise BridgeError(f"Invalid time: {value}. Use HH:MM.")
        return hour * 60 + minute

    @classmethod
    def _row_clock_minutes(cls, row: dict[str, Any]) -> int | None:
        match = re.search(r"\b\d{1,2}:\d{2}\b", str(row.get("text", "")))
        return cls._clock_minutes(match.group()) if match else None

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
    def _certificate_semantics(
        *,
        document_type: str,
        language: str,
        copies: int,
        include_rank: bool,
        gpa_conversion: bool,
        gpa_scale: str | None,
    ) -> dict[str, Any]:
        return {
            "document_type": document_type,
            "language": language,
            "copies": copies,
            "include_rank": include_rank,
            "gpa_conversion": gpa_conversion,
            "gpa_scale": gpa_scale if gpa_conversion else None,
        }

    @staticmethod
    def _certificate_semantic_key(semantics: dict[str, Any]) -> str:
        encoded = json.dumps(
            semantics,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _certificate_ledger_path() -> Path:
        return certificate_cache() / "certificate-selections.json"

    @classmethod
    def _read_certificate_ledger(cls) -> dict[str, Any]:
        path = cls._certificate_ledger_path()
        try:
            if path.is_symlink():
                raise BridgeError("certificate_selection_ledger_unsafe")
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {
                "schema": "yonsei-certificate-selection-ledger/v1",
                "entries": {},
            }
        except (OSError, json.JSONDecodeError) as error:
            raise BridgeError("certificate_selection_ledger_invalid") from error
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != "yonsei-certificate-selection-ledger/v1"
            or not isinstance(payload.get("entries"), dict)
        ):
            raise BridgeError("certificate_selection_ledger_invalid")
        return payload

    @classmethod
    def _write_certificate_ledger(cls, ledger: dict[str, Any]) -> None:
        path = cls._certificate_ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(temporary, flags, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    ledger,
                    handle,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        except Exception:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise

    @classmethod
    def _remember_certificate_row(
        cls,
        semantics: dict[str, Any],
        portal_id: str,
    ) -> None:
        ledger = cls._read_certificate_ledger()
        entries = ledger["entries"]
        key = cls._certificate_semantic_key(semantics)
        entries[key] = {
            "semantics": semantics,
            "portal_id": portal_id,
            "updated_at": int(time.time()),
        }
        if len(entries) > 100:
            ordered = sorted(
                entries.items(),
                key=lambda item: int(item[1].get("updated_at") or 0),
                reverse=True,
            )[:100]
            ledger["entries"] = dict(ordered)
        cls._write_certificate_ledger(ledger)

    @classmethod
    def _known_certificate_row(
        cls,
        semantics: dict[str, Any],
    ) -> str | None:
        entry = cls._read_certificate_ledger()["entries"].get(
            cls._certificate_semantic_key(semantics)
        )
        if not isinstance(entry, dict):
            return None
        portal_id = entry.get("portal_id")
        return portal_id if isinstance(portal_id, str) and portal_id else None

    @classmethod
    def _portal_id_has_other_semantics(
        cls,
        portal_id: str,
        semantics: dict[str, Any],
    ) -> bool:
        wanted = cls._certificate_semantic_key(semantics)
        for key, entry in cls._read_certificate_ledger()["entries"].items():
            if (
                key != wanted
                and isinstance(entry, dict)
                and entry.get("portal_id") == portal_id
            ):
                return True
        return False

    @staticmethod
    def _reportx_request(
        path: str,
        *,
        data: dict[str, Any] | None = None,
        timeout: float = 3.0,
    ) -> dict[str, Any]:
        cache = certificate_cache()
        token_path = cache / "agent.token"
        try:
            token = token_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise BridgeError("certificate_agent_token_missing") from error
        if not token:
            raise BridgeError("certificate_agent_token_missing")
        headers = {
            "User-Agent": "yonsei-student-companion/0.6",
            "X-Agent-Token": token,
        }
        body = None
        method = "GET"
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"
        request = urllib.request.Request(
            f"http://127.0.0.1:65432{path}",
            data=body,
            headers=headers,
            method=method,
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            OSError,
            TimeoutError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ) as error:
            raise BridgeError("certificate_agent_unavailable") from error
        if not isinstance(payload, dict):
            raise BridgeError("certificate_agent_invalid_response")
        return payload

    @classmethod
    def _reportx_process_status(cls) -> dict[str, Any]:
        cache = certificate_cache()
        try:
            health = cls._reportx_request("/health")
            if health.get("ok"):
                status = cls._reportx_request("/status")
                readiness = status.get("readiness", health.get("readiness", {}))
                return {
                    "running": True,
                    "cache": str(cache),
                    "endpoint": "http://127.0.0.1:65432",
                    "health_verified": True,
                    "allow_fetch": status.get("allow_fetch") is True,
                    "allow_document_reservation": (
                        status.get("allow_document_reservation") is True
                    ),
                    "allow_completion_notification": (
                        status.get("allow_completion_notification") is True
                    ),
                    "official_assets_ready": (
                        isinstance(readiness, dict)
                        and readiness.get("official_runtime_assets_verified") is True
                    ),
                    "fonts_ready": (
                        isinstance(readiness, dict)
                        and readiness.get("bundled_font_hashes_verified") is True
                    ),
                    "live_issue_ready": (
                        isinstance(readiness, dict)
                        and readiness.get("live_issue_ready") is True
                    ),
                }
        except BridgeError:
            pass
        pid_file = cache / "bridge-agent.pid"
        try:
            if pid_file.is_file() and not pid_file.is_symlink():
                pid_file.unlink()
        except OSError:
            pass
        return {
            "running": False,
            "health_verified": False,
            "cache": str(cache),
        }

    def _prepare_reportx_assets(self) -> None:
        script = self._find_script("icert_print.py")
        cache = certificate_cache()
        cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--dir",
                str(cache),
                "prepare-assets",
            ],
            cwd=str(script.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            raise BridgeError("certificate_official_assets_unavailable")

    def _start_reportx_agent(self) -> dict[str, Any]:
        current = self._reportx_process_status()
        if current["running"] and current.get("health_verified"):
            if all(
                current.get(key) is True
                for key in (
                    "allow_fetch",
                    "allow_document_reservation",
                    "allow_completion_notification",
                    "official_assets_ready",
                    "fonts_ready",
                    "live_issue_ready",
                )
            ):
                return current
            raise BridgeError(
                "The running certificate listener lacks the confirmed PDF "
                "completion capabilities. Close it, then run the request once."
            )
        if current["running"]:
            raise BridgeError(
                "A certificate listener process exists but its authenticated "
                "health check failed. Close it before starting the PDF printer."
            )
        script = self._find_script("icert_print.py")
        self._prepare_reportx_assets()
        cache = certificate_cache()
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
                "--notify-print-completion",
            ],
            cwd=str(script.parent),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log.close()
        (cache / "bridge-agent.pid").write_text(str(process.pid), encoding="utf-8")
        deadline = time.monotonic() + 8.0
        verified: dict[str, Any] | None = None
        while time.monotonic() < deadline and process.poll() is None:
            try:
                verified = self._reportx_process_status()
            except BridgeError:
                verified = None
            if verified and all(
                verified.get(key) is True
                for key in (
                    "health_verified",
                    "allow_fetch",
                    "allow_document_reservation",
                    "allow_completion_notification",
                    "official_assets_ready",
                    "fonts_ready",
                    "live_issue_ready",
                )
            ):
                break
            time.sleep(0.2)
        if process.poll() is not None:
            raise BridgeError(
                "The certificate compatibility agent did not start. "
                f"Review {log_path} and reinstall if a bundled font is missing."
            )
        if not verified or not all(
            verified.get(key) is True
            for key in (
                "health_verified",
                "allow_fetch",
                "allow_document_reservation",
                "allow_completion_notification",
                "official_assets_ready",
                "fonts_ready",
                "live_issue_ready",
            )
        ):
            raise BridgeError(
                "The certificate compatibility agent started but its assets, "
                "fonts, or live issue capabilities are not ready."
            )
        return {**verified, "pid": process.pid, "log": str(log_path)}

    @classmethod
    def _arm_reportx_agent(cls) -> str:
        armed = cls._reportx_request("/arm", data={})
        arm_id = str(armed.get("arm_id") or "")
        if (
            not armed.get("armed")
            or not re.fullmatch(r"[0-9a-f]{24}", arm_id)
        ):
            raise BridgeError("certificate_agent_arm_failed")
        return arm_id

    @classmethod
    def _wait_reportx_result(
        cls,
        arm_id: str,
        *,
        timeout: float = 55.0,
    ) -> dict[str, Any]:
        success = {
            "server_report_rendered_pdf_unverified",
            "server_pdf_saved_unverified",
            "server_document_reused_unverified",
        }
        deadline = time.monotonic() + timeout
        exact_job_id: str | None = None
        last: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            if exact_job_id is None:
                correlated = cls._reportx_request(
                    "/jobs?correlation_id="
                    + urllib.parse.quote(arm_id, safe="")
                )
                jobs = [
                    job
                    for job in correlated.get("jobs", [])
                    if isinstance(job, dict)
                    and job.get("correlation_id") == arm_id
                    and job.get("id")
                ]
                if len(jobs) > 1:
                    return {
                        "verified": False,
                        "status": "ambiguous_correlated_jobs_do_not_retry",
                        "job_id": None,
                    }
                if not jobs:
                    time.sleep(0.1)
                    continue
                exact_job_id = str(jobs[0]["id"])
            remaining = max(0.0, deadline - time.monotonic())
            wait_seconds = min(30.0, remaining)
            encoded_job_id = urllib.parse.quote(exact_job_id, safe="")
            response = cls._reportx_request(
                f"/jobs/{encoded_job_id}?wait={wait_seconds:.3f}",
                timeout=wait_seconds + 3.0,
            )
            candidate = response.get("job")
            if not isinstance(candidate, dict):
                return {
                    "verified": False,
                    "status": "exact_job_response_invalid_do_not_retry",
                    "job_id": exact_job_id,
                }
            if candidate.get("correlation_id") != arm_id:
                return {
                    "verified": False,
                    "status": "job_correlation_mismatch_do_not_retry",
                    "job_id": exact_job_id,
                }
            last = candidate
            if response.get("terminal") is not True:
                continue
            state = str(last.get("status", ""))
            if state in success:
                return cls._verify_reportx_result(last)
            return {
                "verified": False,
                "status": state or "terminal_failure_do_not_retry",
                "reason_code": last.get("reason_code"),
                "job_id": exact_job_id,
                "document_number_status": last.get(
                    "document_number", {}
                ).get("status"),
            }
        return {
            "verified": False,
            "status": "timeout_unknown_do_not_retry",
            "job_id": exact_job_id,
        }

    @staticmethod
    def _verify_reportx_result(job: dict[str, Any]) -> dict[str, Any]:
        cache = certificate_cache()
        rendered = job.get("rendered_pdf", {})
        artifact = job.get("artifact", {})
        source = (
            rendered
            if rendered.get("path") and rendered.get("sha256")
            else artifact
        )
        filename = Path(str(source.get("path", ""))).name
        expected = str(source.get("sha256", ""))
        candidate = (cache / "output" / filename).resolve()
        output_root = (cache / "output").resolve()
        try:
            candidate.relative_to(output_root)
            body = candidate.read_bytes()
        except (OSError, ValueError):
            return {
                "verified": False,
                "status": "pdf_file_missing",
                "job_id": job.get("id"),
            }
        actual = hashlib.sha256(body).hexdigest()
        is_pdf = body.startswith(b"%PDF-") and b"%%EOF" in body[-4096:]
        fonts = rendered.get("fonts", [])
        allowed_fonts = {
            "d38160cc6767e3f35f81b15c2fd9ca1c7fc11a20fcb9fa7f603c8c1b5d2f4d82",
            "b85573c700a42b1045f4563bb9d08bb21d22b03403db922d41f26e4d5e55cbf9",
        }
        observed_font_hashes = {
            str(item.get("sha256"))
            for item in fonts
            if isinstance(item, dict) and item.get("sha256")
        }
        verified = (
            bool(expected)
            and actual == expected
            and is_pdf
            and bool(observed_font_hashes)
            and observed_font_hashes.issubset(allowed_fonts)
            and int(rendered.get("page_count") or 0) > 0
            and job.get("document_number", {}).get("completion_notified") is True
        )
        return {
            "verified": verified,
            "status": (
                "completed"
                if verified
                else "pdf_or_font_verification_failed"
            ),
            "job_id": job.get("id"),
            "pdf_path": str(candidate),
            "sha256": actual,
            "page_count": rendered.get("page_count"),
            "fonts": fonts,
            "completion_notified": job.get(
                "document_number", {}
            ).get("completion_notified"),
            "official_free_print": True,
            "paid_electronic_certificate": False,
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
        state = self.page.wait_for_login_state()
        snapshot = self.page.snapshot()
        return {
            "schema": "yonsei-bridge-status/v1",
            "state": state,
            "service": urlsplit(snapshot.url).hostname,
            "browser_profile": "managed-persistent",
            "credentials_collected": False,
            "next_step": "run-command" if state == "connected" else "complete-login-in-open-browser",
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
        if page.wait_for_login_state() != "connected":
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
        login_state = page.wait_for_login_state()
        dashboard = page.snapshot()
        result: dict[str, Any] = {
            "schema": "yonsei-today-command/v1",
            "dashboard": dashboard.as_dict(),
            "sources": ["portal"],
            "read_only": True,
        }
        if full and login_state == "connected":
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

    def course_catalog(
        self,
        *,
        year: str | None = None,
        semester: str | None = None,
        campus: str | None = None,
        course_type: str | None = None,
        department: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """Query the authenticated Underwood handbook independently of registration."""
        page = self._page()
        page.navigate(COURSE_CATALOG, wait=2.5)
        if page.wait_for_login_state() == "login_required":
            raise BridgeError("login_required")
        applied: dict[str, bool] = {}
        if year:
            applied["year"] = page.type_after_label("학년도/학기", str(year), index=0)
        if semester:
            applied["semester"] = page.select_after_label(
                "학년도/학기", str(semester), index=0
            )
        if campus:
            applied["campus"] = page.select_after_label("구분", str(campus))
        if course_type:
            applied["course_type"] = page.select_after_label(
                "대학(원)/분류", str(course_type)
            )
        if department:
            applied["department"] = page.select_after_label("개설학과", str(department))
        if keyword:
            applied["keyword"] = page.type_after_label("통합검색", str(keyword))
        filters = page.values_after_labels(
            ["학년도/학기", "구분", "대학(원)/분류", "개설학과", "통합검색"]
        )
        requested = {
            "year": ("학년도/학기", year),
            "semester": ("학년도/학기", semester),
            "campus": ("구분", campus),
            "course_type": ("대학(원)/분류", course_type),
            "department": ("개설학과", department),
            "keyword": ("통합검색", keyword),
        }
        for key, (label, value) in requested.items():
            if value in (None, ""):
                continue
            applied[key] = any(
                _requested_value_matches(value, observed)
                for observed in filters.get(label, [])
            )
        unmatched_filters = [
            key
            for key, (_, value) in requested.items()
            if value not in (None, "") and not applied.get(key, False)
        ]
        if unmatched_filters:
            snapshot = page.snapshot(text_after="수강편람")
            return {
                "schema": "yonsei-course-catalog-command/v1",
                "state": "field_mapping_required",
                "source": "underwood-course-handbook",
                "registration_period_required": False,
                "snapshot": snapshot.as_dict(),
                "filters": filters,
                "requested_filters_applied": applied,
                "unmatched_filters": unmatched_filters,
                "rows": [],
            }
        if not page.click_text("조회"):
            raise BridgeError("The official course-handbook query button was not available.")
        time.sleep(1.8)
        snapshot = page.snapshot(text_after="수강편람")
        rows = [
            row
            for row in self._rows(snapshot)
            if "조회된 내역이 없습니다" not in row.get("text", "")
        ]
        no_results = "조회된 내역이 없습니다" in snapshot.text and not rows
        return {
            "schema": "yonsei-course-catalog-command/v1",
            "state": "no_results" if no_results else "available",
            "source": "underwood-course-handbook",
            "registration_period_required": False,
            "snapshot": snapshot.as_dict(),
            "filters": filters,
            "requested_filters_applied": applied,
            "unmatched_filters": [],
            "rows": rows,
        }

    def mileage(
        self,
        *,
        year: str | None = None,
        semester: str | None = None,
        campus: str | None = None,
        course_type: str | None = None,
        department: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        catalog = self.course_catalog(
            year=year,
            semester=semester,
            campus=campus,
            course_type=course_type,
            department=department,
            keyword=keyword,
        )
        if catalog.get("state") == "field_mapping_required":
            return {
                "schema": "yonsei-mileage-history-command/v1",
                "state": "field_mapping_required",
                "catalog": catalog,
                "history": {"state": "not_queried", "rows": []},
                "current_registration": {"state": "not_queried", "rows": []},
                "planning_inputs_ready": False,
                "planning_performed": False,
                "registration_performed": False,
            }
        try:
            history_snapshot = self._open_menu("mileage")
            history = {
                "state": "available",
                "snapshot": history_snapshot.as_dict(),
                "rows": self._rows(history_snapshot),
            }
        except BridgeError as error:
            history = {"state": str(error), "rows": []}
        try:
            current_snapshot = self._open_menu("classes")
            current_rows = self._rows(current_snapshot)
            current = {
                "state": "available" if current_rows else "no_current_registration_rows",
                "snapshot": current_snapshot.as_dict(),
                "rows": current_rows,
            }
        except BridgeError as error:
            current = {
                "state": (
                    "registration_period_limited_or_unavailable"
                    if str(error) != "login_required"
                    else "login_required"
                ),
                "rows": [],
            }
        return {
            "schema": "yonsei-mileage-history-command/v1",
            "state": "available",
            "catalog": catalog,
            "history": history,
            "current_registration": current,
            "planning_inputs_ready": bool(
                catalog.get("rows") or history.get("rows") or current.get("rows")
            ),
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
        if action not in {"search", "reserve", "waitlist", "cancel"}:
            raise BridgeError("Shuttle action must be search, reserve, waitlist, or cancel.")
        view = "cancel" if action == "cancel" else "booking"
        selection_context = json.dumps(
            {
                "view": view,
                "origin": origin,
                "destination": destination or "",
                "date": date,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        selected = None
        if confirmed:
            selected = self._selection(
                selection_id,
                "shuttle",
                context=selection_context,
                consume=True,
            )
            if selected is None:
                raise BridgeError("selection_not_found")
        snapshot = self._open_menu("shuttle")
        page = self._page()
        history_opened = action == "cancel"
        if action == "cancel":
            if not page.click_text("내역/취소"):
                raise BridgeError("The official shuttle history tab was not available.")
            time.sleep(1.5)
            snapshot = page.snapshot(text_after="셔틀버스예약")
        else:
            if not page.click_text("예약"):
                raise BridgeError("The official shuttle reservation tab was not available.")
            applied = {
                "origin": self._fill_verified(page, "출발지역", origin),
                "date": self._fill_verified(page, "예약일자", date),
            }
            unmatched_fields = [
                field for field, was_applied in applied.items() if not was_applied
            ]
            if unmatched_fields:
                return {
                    "schema": "yonsei-shuttle-command/v1",
                    "action": action,
                    "state": "field_mapping_required",
                    "unmatched_fields": unmatched_fields,
                    "requested_filters_applied": applied,
                    "snapshot": page.snapshot(text_after="셔틀버스예약").as_dict(),
                    "candidates": [],
                    "reservation_performed": False,
                    "retry_allowed": False if confirmed else True,
                }
            for search_label in ("조회", "검색"):
                if page.click_text(search_label):
                    break
            time.sleep(2.0)
            snapshot = page.snapshot(text_after="셔틀버스예약")
        rows = self._rows(snapshot)
        if action == "cancel":
            date_digits = re.sub(r"\D", "", date)
            rows = [
                row
                for row in rows
                if _requested_value_matches(origin, row.get("text", ""))
                and (
                    not date_digits
                    or date_digits in re.sub(r"\D", "", row.get("text", ""))
                )
            ]
        wanted_terms = [term for term in (destination,) if term]
        if wanted_terms:
            rows = [
                row for row in rows
                if all(
                    _requested_value_matches(term, row.get("text", ""))
                    for term in wanted_terms
                )
            ]
        if depart_after:
            after_minutes = self._clock_minutes(depart_after)
            rows = [
                row
                for row in rows
                if self._row_clock_minutes(row) is not None
                and self._row_clock_minutes(row) >= after_minutes
            ]
        if depart_before:
            before_minutes = self._clock_minutes(depart_before)
            rows = [
                row
                for row in rows
                if self._row_clock_minutes(row) is not None
                and self._row_clock_minutes(row) <= before_minutes
            ]
        if preferred_time:
            preferred_minutes = self._clock_minutes(preferred_time)
            rows.sort(
                key=lambda row: (
                    abs((self._row_clock_minutes(row) or 0) - preferred_minutes)
                    if self._row_clock_minutes(row) is not None
                    else 24 * 60,
                    self._row_clock_minutes(row) or 24 * 60,
                )
            )
        if selected is None:
            rows = self._remember_rows(
                "shuttle",
                rows,
                context=selection_context,
            )
        if action == "search":
            return {
                "schema": "yonsei-shuttle-command/v1",
                "action": "search",
                "snapshot": snapshot.as_dict(),
                "candidates": rows,
                "reservation_performed": False,
            }
        if not confirmed:
            return {
                "schema": "yonsei-shuttle-command/v1",
                "action": action,
                "state": "confirmation_required",
                "snapshot": snapshot.as_dict(),
                "candidates": rows,
                "reservation_performed": False,
            }
        assert selected is not None
        selected_terms = list(selected.get("terms", []))
        if (
            not selected_terms
            or not any(row.get("text") == selected.get("text") for row in rows)
            or not page.click_grid_row(selected_terms)
        ):
            raise BridgeError("The exact shuttle row could not be matched.")
        if action in {"reserve", "waitlist"}:
            if not reason:
                raise BridgeError("A reservation reason is required.")
            if not self._fill_verified(page, "사유", reason):
                return {
                    "schema": "yonsei-shuttle-command/v1",
                    "action": action,
                    "state": "field_mapping_required",
                    "unmatched_fields": ["reason"],
                    "snapshot": page.snapshot(text_after="셔틀버스예약").as_dict(),
                    "reservation_performed": False,
                    "write_attempted_once": False,
                    "retry_allowed": False,
                }
            button = "예약신청" if action == "reserve" else "대기신청"
        else:
            button = "예약취소"
        if not page.click_text(button):
            raise BridgeError(f"The official {button} button was not available.")
        time.sleep(2.0)
        verified = page.snapshot(text_after="셔틀버스예약")
        if action in {"reserve", "waitlist"}:
            history_opened = page.click_text("내역/취소")
            if history_opened:
                time.sleep(1.5)
                verified = page.snapshot(text_after="셔틀버스예약")
        official_rows = self._rows(verified)
        selected_present = self._rows_match_terms(official_rows, selected_terms)
        completed = (
            history_opened and selected_present
            if action in {"reserve", "waitlist"}
            else self._success_marker(action, verified) and not selected_present
        )
        return {
            "schema": "yonsei-shuttle-command/v1",
            "action": action,
            "state": "completed" if completed else "verification_required",
            "official_result": verified.as_dict(),
            "official_rows": official_rows,
            "official_result_verified": completed,
            "reservation_performed": completed and action in {"reserve", "waitlist"},
            "write_attempted_once": True,
            "retry_allowed": False,
            "next_step": (
                "done"
                if completed
                else "review-official-history-do-not-retry"
            ),
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
        if service not in {"space", "dorm"}:
            raise BridgeError("service must be space or dorm.")
        if action not in {"status", "search", "apply", "reserve", "submit", "cancel"}:
            raise BridgeError(
                "Space or dorm action must be status, search, apply, reserve, submit, or cancel."
            )
        if fields or row_terms or submit_button:
            raise BridgeError(
                "Legacy selector overrides are not supported. Use a reviewed selection_id."
            )
        selected = None
        if action not in {"status", "search"}:
            selected = self._selection(
                selection_id,
                service,
                consume=confirmed,
            )
            if selected is None:
                raise BridgeError("selection_not_found")
        if service == "space":
            page = self._page()
            page.navigate(SPACE, wait=2.5)
            snapshot = page.snapshot()
        else:
            page = self._underwood()
            login_checker = getattr(page, "login_state", None)
            if callable(login_checker) and login_checker() != "connected":
                raise BridgeError("login_required")
            if not page.click_text(category):
                raise BridgeError(f"Could not open Underwood category: {category}.")
            time.sleep(0.5)
            if menu:
                if not page.click_text(menu):
                    raise BridgeError(f"Could not open dorm menu: {menu}.")
                time.sleep(2.0)
            snapshot = page.snapshot(text_after=menu)
        login_checker = getattr(page, "login_state", None)
        login_state = login_checker() if callable(login_checker) else "connected"
        if login_state == "login_required":
            return {
                "schema": "yonsei-space-dorm-command/v1",
                "service": service,
                "action": action,
                "state": "login_required",
                "snapshot": snapshot.as_dict(),
                "rows": [],
                "action_performed": False,
                "retry_allowed": False if confirmed else True,
            }
        request = request or {}
        mapping = SPACE_REQUEST_FIELDS if service == "space" else DORM_REQUEST_FIELDS
        if action in {"status", "search"}:
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
            accepted_input = {
                key: value.get("filled", False)
                for key, value in student_filled.items()
            }
            unmatched_fields = [
                key for key, accepted in accepted_input.items() if not accepted
            ]
            if unmatched_fields:
                return {
                    "schema": "yonsei-space-dorm-command/v1",
                    "service": service,
                    "action": action,
                    "state": "field_mapping_required",
                    "snapshot": page.snapshot(text_after=menu).as_dict(),
                    "rows": [],
                    "accepted_input": accepted_input,
                    "unmatched_fields": unmatched_fields,
                    "action_performed": False,
                }
            search_clicked = False
            for label in ("조회", "검색"):
                if page.click_text(label):
                    search_clicked = True
                    time.sleep(1.5)
                    break
            if search_request and not search_clicked:
                return {
                    "schema": "yonsei-space-dorm-command/v1",
                    "service": service,
                    "action": action,
                    "state": "page_changed",
                    "snapshot": page.snapshot(text_after=menu).as_dict(),
                    "rows": [],
                    "accepted_input": accepted_input,
                    "unmatched_fields": ["search_button"],
                    "action_performed": False,
                }
            snapshot = page.snapshot(text_after=menu)
            rows = self._remember_rows(
                service,
                self._rows(snapshot),
                context=json.dumps(
                    search_request,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            return {
                "schema": "yonsei-space-dorm-command/v1",
                "service": service,
                "action": action,
                "state": "available" if rows else "no_results",
                "snapshot": snapshot.as_dict(),
                "rows": rows,
                "accepted_input": accepted_input,
                "unmatched_fields": [],
                "action_performed": False,
            }
        assert selected is not None
        selected_terms = list(selected.get("terms", []))
        current_rows = self._rows(snapshot)
        if (
            not selected_terms
            or not any(row.get("text") == selected.get("text") for row in current_rows)
            or not page.click_grid_row(selected_terms)
        ):
            raise BridgeError("The exact reviewed space or dorm row could not be matched.")
        time.sleep(0.5)
        student_filled = page.fill_student_request(request, mapping)
        failed_student_fields = [
            key for key, value in student_filled.items() if not value.get("filled")
        ]
        if failed_student_fields:
            return {
                "schema": "yonsei-space-dorm-command/v1",
                "service": service,
                "action": action,
                "state": "field_mapping_required",
                "unmatched_fields": failed_student_fields,
                "snapshot": page.snapshot(text_after=menu).as_dict(),
                "action_performed": False,
                "write_attempted_once": False,
                "retry_allowed": False if confirmed else True,
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
        button = {
            "apply": "신청",
            "reserve": "예약",
            "submit": "제출",
            "cancel": "취소",
        }[action]
        if not page.click_text(button):
            raise BridgeError(f"The exact official action button was not available: {button}.")
        time.sleep(2.0)
        submitted = page.snapshot(text_after=menu)
        verified = submitted
        history_opened = False
        for history_label in (
            "신청내역",
            "예약내역",
            "나의 예약",
            "이용내역",
            "내역조회",
        ):
            if page.click_text(history_label):
                history_opened = True
                time.sleep(1.5)
                verified = page.snapshot(text_after=menu)
                break
        official_rows = self._rows(verified)
        selected_present = self._rows_match_terms(official_rows, selected_terms)
        completed = (
            history_opened and selected_present
            if action in {"apply", "reserve", "submit"}
            else (
                history_opened
                and self._success_marker(action, submitted)
                and not selected_present
            )
        )
        return {
            "schema": "yonsei-space-dorm-command/v1",
            "service": service,
            "action": action,
            "state": "completed" if completed else "verification_required",
            "official_result": verified.as_dict(),
            "official_rows": official_rows,
            "official_result_verified": completed,
            "action_performed": completed,
            "write_attempted_once": True,
            "retry_allowed": False,
            "next_step": (
                "done"
                if completed
                else "review-official-history-do-not-retry"
            ),
        }

    @classmethod
    def _select_certificate_for_free_print(
        cls,
        page: BrowserPage,
        *,
        document_type: str,
        document_label: str,
        language_label: str,
        copies: int,
        include_rank: bool,
        gpa_conversion: bool,
        gpa_scale: str | None,
    ) -> dict[str, Any]:
        """Select an exact basket row, creating at most one request if absent."""

        semantics = cls._certificate_semantics(
            document_type=document_type,
            language=language_label,
            copies=copies,
            include_rank=include_rank,
            gpa_conversion=gpa_conversion,
            gpa_scale=gpa_scale,
        )
        requested_new = False
        checked_basket = False
        baseline_ids: set[str] | None = None

        def select_candidate(candidate: dict[str, Any], source: str) -> dict[str, Any]:
            portal_id = str(candidate.get("portal_id") or "")
            raw_key = str(candidate.get("_portal_key") or "")
            if not portal_id or not raw_key or not page.select_certificate_basket_row(
                portal_key=raw_key,
                document_label=document_label,
                language_label=language_label,
            ):
                raise BridgeError("certificate_exact_basket_row_unavailable")
            cls._remember_certificate_row(semantics, portal_id)
            return {
                "selected": True,
                "source": source,
                "document_label": document_label,
                "language_label": language_label,
                "copies": copies,
                "include_rank": include_rank,
                "gpa_conversion": gpa_conversion,
                "gpa_scale": gpa_scale if gpa_conversion else None,
            }

        for _ in range(30):
            snapshot = page.snapshot()
            title = snapshot.title
            text = snapshot.text

            if page.select_radio("agree2", "agr"):
                if not page.select_radio("agree", "disagr"):
                    raise BridgeError("certificate_optional_consent_mapping_changed")
                if not page.click_href_fragment("submitok"):
                    raise BridgeError("certificate_consent_submit_missing")
                time.sleep(2.0)
                continue

            candidates = page.certificate_basket_rows(
                document_label=document_label,
                language_label=language_label,
                copies=copies,
            )
            if candidates:
                if requested_new:
                    new_candidates = [
                        candidate
                        for candidate in candidates
                        if baseline_ids is None
                        or candidate.get("portal_id") not in baseline_ids
                    ]
                    if len(new_candidates) == 1:
                        return select_candidate(new_candidates[0], "new_request")
                    if len(new_candidates) > 1:
                        raise BridgeError("certificate_new_basket_row_ambiguous")
                known_id = cls._known_certificate_row(semantics)
                exact = [
                    candidate
                    for candidate in candidates
                    if candidate.get("portal_id") == known_id
                ]
                if len(exact) == 1:
                    return select_candidate(exact[0], "existing_exact_basket")
                if any(
                    cls._portal_id_has_other_semantics(
                        str(candidate.get("portal_id") or ""),
                        semantics,
                    )
                    for candidate in candidates
                ):
                    raise BridgeError("certificate_basket_option_mismatch_do_not_duplicate")
                if document_type == "transcript":
                    # Rank/conversion are not displayed in the basket.  An
                    # unrecorded transcript cannot be proven equivalent.
                    raise BridgeError("certificate_basket_options_unverifiable_do_not_duplicate")
                if len(candidates) == 1:
                    return select_candidate(
                        candidates[0],
                        "existing_unambiguous_basket",
                    )
                raise BridgeError("certificate_basket_row_ambiguous_do_not_duplicate")

            if "메인" in title and "증명서 무료 출력/전송" in text:
                if not page.click_href_fragment("Service('INTERNET')"):
                    raise BridgeError("certificate_free_print_service_missing")
                time.sleep(2.0)
                continue

            if (
                not checked_basket
                and "증명서 보관함" in text
                and "증명서 선택" not in title
                and "신청증명서함" not in title
            ):
                checked_basket = True
                if not page.click_href_fragment("Basket"):
                    raise BridgeError("certificate_basket_link_missing")
                time.sleep(2.0)
                continue

            if checked_basket and "증명서 보관함" in title:
                if baseline_ids is None:
                    baseline_ids = {
                        str(candidate.get("portal_id"))
                        for candidate in candidates
                        if candidate.get("portal_id")
                    }
                if not page.click_href_fragment("Request"):
                    raise BridgeError("certificate_request_link_missing")
                time.sleep(1.0)
                continue

            if "학위선택" in title:
                if not page.select_only_nonempty_option("sel_hakwi"):
                    raise BridgeError("certificate_degree_selection_required")
                if not page.click_text("다음"):
                    raise BridgeError("certificate_degree_next_missing")
                time.sleep(2.0)
                continue

            if "증명서 선택" in title:
                if not page.configure_certificate_request(
                    document_label=document_label,
                    language_label=language_label,
                    copies=copies,
                    include_rank=include_rank,
                    gpa_conversion=gpa_conversion,
                    gpa_scale=gpa_scale,
                ):
                    raise BridgeError("certificate_type_language_or_options_unavailable")
                time.sleep(0.2)
                if not page.click_text("다음"):
                    raise BridgeError("certificate_selection_next_missing")
                time.sleep(1.0)
                continue

            if "신청증명서함" in title:
                if not page.click_href_fragment("goReq"):
                    if not page.click_href_fragment("Request"):
                        raise BridgeError("certificate_request_submit_missing")
                    time.sleep(1.0)
                    continue
                requested_new = True
                time.sleep(1.5)
                continue

            if "증명서 신청" in text:
                if not page.click_href_fragment("Request"):
                    raise BridgeError("certificate_request_link_missing")
                time.sleep(2.0)
                continue

            raise BridgeError("certificate_page_changed")
        raise BridgeError("certificate_navigation_timeout")

    def documents(
        self,
        *,
        document_type: str,
        action: str = "open",
        output_format: str = "pdf",
        language: str | None = None,
        copies: int | None = None,
        purpose: str | None = None,
        include_rank: bool | None = None,
        gpa_conversion: bool | None = None,
        gpa_scale: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        if action not in {"open", "issue"}:
            raise BridgeError("Document action must be open or issue.")
        if output_format not in {"pdf", "print"}:
            raise BridgeError("Document output format must be pdf or print.")
        if document_type in {"education_practicum", "teaching"}:
            snapshot = self.academic_applications(category="교직", application="교육실습참가확인서출력")
            runtime = (
                self._start_reportx_agent()
                if action == "issue" and confirmed and output_format == "pdf"
                else {
                    "mode": (
                        "official-reportx-physical"
                        if platform.system() == "Windows"
                        and output_format == "print"
                        else "open-only"
                    )
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
        visible_document = DOCUMENT_LABELS.get(document_type)
        if not visible_document:
            raise BridgeError("unsupported_certificate_type")
        if action == "issue":
            missing = [
                name
                for name, value in (("language", language), ("copies", copies))
                if value is None
            ]
            if document_type == "transcript":
                if include_rank is None:
                    missing.append("include_rank")
                if gpa_conversion is None:
                    missing.append("gpa_conversion")
                if gpa_conversion is True and gpa_scale is None:
                    missing.append("gpa_scale")
            if missing:
                raise BridgeError("missing:" + ",".join(missing))
        requested_rank = bool(include_rank)
        requested_conversion = bool(gpa_conversion)
        normalized_scale = str(gpa_scale).strip() if gpa_scale is not None else None
        if document_type != "transcript" and (
            requested_rank or requested_conversion or normalized_scale
        ):
            raise BridgeError("certificate_transcript_options_not_applicable")
        if requested_conversion and normalized_scale != "4.5":
            raise BridgeError("certificate_gpa_scale_must_be_4.5")
        if not requested_conversion and normalized_scale:
            raise BridgeError("certificate_gpa_conversion_scale_mismatch")
        normalized_language = {
            "ko": "국문",
            "korean": "국문",
            "en": "영문",
            "english": "영문",
        }.get((language or "ko").casefold(), language or "국문")
        requested_copies = copies if copies is not None else 1
        if requested_copies != 1:
            raise BridgeError("certificate_single_copy_only")

        if self.page is None:
            connection_status = self.connect()
            assert self.page is not None
            page = self.page
            login_state = str(connection_status.get("state", "unknown"))
        else:
            page = self.page
            page.navigate(PORTAL, wait=2.5)
            login_state = page.wait_for_login_state()
        if login_state != "connected":
            raise BridgeError("login_required")
        previous_targets = self.runtime.target_ids()
        if not page.click_text("인터넷증명서"):
            raise BridgeError("The official internet-certificate portal menu was not available.")
        time.sleep(2.0)
        route_snapshot = page.snapshot()
        if urlsplit(route_snapshot.url).hostname != "icert.yonsei.ac.kr":
            connection = self.runtime.connection_for_host(
                "icert.yonsei.ac.kr",
                previous_target_ids=previous_targets,
            )
            if connection is None:
                raise BridgeError(
                    "The official internet-certificate page did not open from Portal."
                )
            self.connection = connection
            self.page = BrowserPage(connection)
            page = self.page
            route_snapshot = page.snapshot()
        if (
            "원본대조확인" in route_snapshot.title
            or "증명서 원본확인 문서번호" in route_snapshot.text
        ):
            raise BridgeError(
                "The Portal opened certificate original verification instead of issuance."
            )
        snapshot = page.snapshot()
        if action == "issue" and not confirmed:
            return {
                "schema": "yonsei-document-command/v1",
                "document_type": document_type,
                "state": "confirmation_required",
                "review": {
                    "document_type": document_type,
                    "language": normalized_language,
                    "copies": requested_copies,
                    "include_rank": requested_rank,
                    "gpa_conversion": requested_conversion,
                    "gpa_scale": normalized_scale if requested_conversion else None,
                    "output_format": output_format,
                },
                "snapshot": snapshot.as_dict(),
                "issuance_performed": False,
                "font_verification_required": True,
            }
        if action != "issue":
            return {
                "schema": "yonsei-document-command/v1",
                "document_type": document_type,
                "state": "official_page_ready",
                "snapshot": snapshot.as_dict(),
                "output_format": output_format,
                "issuance_performed": False,
                "next_step": "review-the-official-document-route",
            }

        review = {
            "document_type": document_type,
            "language": normalized_language,
            "copies": requested_copies,
            "include_rank": requested_rank,
            "gpa_conversion": requested_conversion,
            "gpa_scale": normalized_scale if requested_conversion else None,
            "output_format": output_format,
        }
        system = platform.system()
        runtime = (
            {"mode": "official-reportx-physical"}
            if output_format == "print" and system == "Windows"
            else self._start_reportx_agent()
        )
        selection = self._select_certificate_for_free_print(
            page,
            document_type=document_type,
            document_label=visible_document,
            language_label=normalized_language,
            copies=requested_copies,
            include_rank=requested_rank,
            gpa_conversion=requested_conversion,
            gpa_scale=normalized_scale,
        )
        if output_format == "print" and system == "Windows":
            return {
                "schema": "yonsei-document-command/v1",
                "document_type": document_type,
                "state": "official_reportx_physical_ready",
                "review": review,
                "selection": selection,
                "runtime": runtime,
                "issuance_performed": False,
                "next_step": "choose-the-named-physical-printer",
                "font_verification_required": False,
            }
        result: dict[str, Any] = {
            "verified": False,
            "status": "no_print_attempt",
        }
        arm_id = self._arm_reportx_agent()
        if not page.click_href_fragment("goPrint"):
            raise BridgeError("certificate_printer_output_missing")
        result = self._wait_reportx_result(arm_id)
        completed = result.get("verified") is True
        return {
            "schema": "yonsei-document-command/v1",
            "document_type": document_type,
            "state": "completed" if completed else "verification_required",
            "review": review,
            "selection": selection,
            "official_result": result,
            "official_result_verified": completed,
            "runtime": runtime,
            "output_format": output_format,
            "issuance_performed": completed,
            "write_attempted_once": True,
            "official_output_clicks": 1,
            "retry_allowed": False,
            "next_step": (
                "done"
                if completed
                else "review-agent-status-and-official-basket-do-not-retry"
            ),
            "font_verification_required": True,
        }

    def learnus_attendance(self, *, service: str) -> dict[str, Any]:
        page = self._page()
        sso_attempted = False
        if service == "learnus":
            page.navigate(LEARNUS, wait=3.0)
            state = page.wait_for_login_state()
            if state != "connected" and page.click_text("Portal Login"):
                sso_attempted = True
                time.sleep(2.0)
                state = page.wait_for_login_state(timeout=8.0)
        elif service == "attendance":
            page.navigate(ATTENDANCE, wait=3.0)
            state = page.wait_for_login_state()
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
            "state": state,
            "snapshot": snapshot.as_dict(),
            "courses": courses,
            "rows": rows,
            "portal_sso_attempted": sso_attempted,
            "read_only": True,
            "attendance_check_in_performed": False,
        }

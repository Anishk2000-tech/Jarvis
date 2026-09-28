"""
email — read, search, send and reply to e-mail by voice, and read the Outlook
calendar.

Two ways in (set up in ⚙ → PLUGIN SETTINGS → E-mail):

  IMAP / SMTP   Gmail, Yahoo, iCloud, Zoho, most providers. Use an APP
                PASSWORD, not your normal password (Gmail: myaccount.google.com
                → Security → 2-Step Verification → App passwords).
  Outlook app   On Windows, if Microsoft Outlook (classic desktop) is installed
                and signed in, choose "outlook_app" — no password needed here,
                and the calendar works too.

Sending always asks for confirmation first (button, or say "confirm").
"""
from __future__ import annotations

import email
import email.utils
import imaplib
import re
import smtplib
import ssl
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage

from core import confirm as confirm_gate

NS = "email"
_PRESETS = {
    "gmail.com": ("imap.gmail.com", "smtp.gmail.com", 465),
    "googlemail.com": ("imap.gmail.com", "smtp.gmail.com", 465),
    "yahoo.com": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com", 465),
    "icloud.com": ("imap.mail.me.com", "smtp.mail.me.com", 587),
    "me.com": ("imap.mail.me.com", "smtp.mail.me.com", 587),
    "zoho.com": ("imap.zoho.com", "smtp.zoho.com", 465),
    "zohomail.in": ("imap.zoho.in", "smtp.zoho.in", 465),
    "rediffmail.com": ("imap.rediffmail.com", "smtp.rediffmail.com", 465),
    "gmx.com": ("imap.gmx.com", "mail.gmx.com", 465),
    "aol.com": ("imap.aol.com", "smtp.aol.com", 465),
}


def _cfg() -> dict:
    try:
        from memory.config_manager import get_plugin_config
        return get_plugin_config(NS)
    except Exception:
        return {}


def _hosts(cfg: dict) -> tuple[str, str, int]:
    addr = str(cfg.get("address") or "")
    dom = addr.split("@")[-1].lower()
    imap_h, smtp_h, port = _PRESETS.get(dom, ("", "", 465))
    imap_h = cfg.get("imap_host") or imap_h
    smtp_h = cfg.get("smtp_host") or smtp_h
    try:
        port = int(cfg.get("smtp_port") or port)
    except (TypeError, ValueError):
        pass
    return imap_h, smtp_h, port


def _dec(v) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return str(v or "")


def _body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                return re.sub(r"<[^>]+>", " ", html)
        return ""
    payload = msg.get_payload(decode=True) or b""
    text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return re.sub(r"<[^>]+>", " ", text) if msg.get_content_type() == "text/html" else text


# ── IMAP / SMTP ──────────────────────────────────────────────────────────────
def _imap(cfg: dict):
    host, _s, _p = _hosts(cfg)
    if not host:
        raise RuntimeError("no IMAP server known for this address — fill in the IMAP host")
    m = imaplib.IMAP4_SSL(host, 993, ssl_context=ssl.create_default_context())
    m.login(cfg["address"], cfg["password"])
    return m


def _fetch(cfg: dict, criteria: str, limit: int) -> list[dict]:
    m = _imap(cfg)
    try:
        m.select("INBOX", readonly=True)
        typ, data = m.search(None, criteria)
        ids = (data[0].split() if data and data[0] else [])[-limit:][::-1]
        out = []
        for i in ids:
            typ, msgdata = m.fetch(i, "(BODY.PEEK[])")
            if not msgdata or not isinstance(msgdata[0], tuple):
                continue
            msg = email.message_from_bytes(msgdata[0][1])
            out.append({"id": i.decode(), "from": _dec(msg.get("From")), "subject": _dec(msg.get("Subject")),
                        "date": msg.get("Date", ""), "body": _body(msg).strip(),
                        "message_id": msg.get("Message-ID", ""), "reply_to": msg.get("Reply-To") or msg.get("From")})
        return out
    finally:
        try:
            m.logout()
        except Exception:
            pass


def _smtp_send(cfg: dict, to: str, subject: str, body: str, in_reply_to: str = "") -> str:
    _i, host, port = _hosts(cfg)
    msg = EmailMessage()
    msg["From"] = cfg["address"]
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(cfg["address"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(cfg["address"], cfg["password"])
            s.send_message(msg)
    return f"Sent to {to}."


# ── Outlook desktop (Windows COM) ────────────────────────────────────────────
def _outlook():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client.Dispatch("Outlook.Application")


def _ol_messages(unread_only: bool, limit: int, query: str = "") -> list[dict]:
    ns = _outlook().GetNamespace("MAPI")
    items = ns.GetDefaultFolder(6).Items
    items.Sort("[ReceivedTime]", True)
    if unread_only:
        items = items.Restrict("[UnRead] = True")
    out = []
    for it in items:
        try:
            if query and query.lower() not in (f"{it.Subject} {it.SenderName} {it.Body[:2000]}").lower():
                continue
            out.append({"id": it.EntryID, "from": it.SenderName, "subject": it.Subject,
                        "date": str(it.ReceivedTime), "body": str(it.Body or "").strip()})
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out


def _ol_send(to: str, subject: str, body: str) -> str:
    mail = _outlook().CreateItem(0)
    mail.To, mail.Subject, mail.Body = to, subject, body
    mail.Send()
    return f"Sent to {to} from Outlook."


def _ol_calendar(days: int) -> str:
    ns = _outlook().GetNamespace("MAPI")
    items = ns.GetDefaultFolder(9).Items
    items.IncludeRecurrences = True
    items.Sort("[Start]")
    start = datetime.now().replace(hour=0, minute=0, second=0)
    end = start + timedelta(days=max(1, days))
    fmt = "%m/%d/%Y %H:%M"
    sel = items.Restrict(f"[Start] >= '{start.strftime(fmt)}' AND [Start] < '{end.strftime(fmt)}'")
    lines = []
    for it in sel:
        try:
            lines.append(f"{str(it.Start)[:16]} — {it.Subject}" + (f" ({it.Location})" if it.Location else ""))
        except Exception:
            continue
        if len(lines) >= 30:
            break
    return "\n".join(lines) or "Nothing on the calendar in that period."


# ── tool ─────────────────────────────────────────────────────────────────────
def _fmt(msgs: list[dict], with_body: bool = False) -> str:
    if not msgs:
        return "No messages."
    out = []
    for n, m in enumerate(msgs, 1):
        line = f"{n}. From {m['from']} — {m['subject']} ({m['date'][:22]})"
        if with_body:
            line += "\n" + re.sub(r"\s+", " ", m["body"])[:1500]
        out.append(line)
    return "\n".join(out)


_last: list[dict] = []


def run(parameters: dict, player=None) -> str:
    global _last
    p = parameters or {}
    cfg = _cfg()
    mode = str(cfg.get("mode") or ("outlook_app" if not cfg.get("address") else "imap")).lower()
    action = str(p.get("action") or "unread").lower()
    try:
        limit = max(1, min(25, int(p.get("count") or 5)))
    except (TypeError, ValueError):
        limit = 5
    try:
        if action == "calendar":
            if mode != "outlook_app":
                return "The calendar works through the Outlook desktop app (set mode to outlook_app)."
            return _ol_calendar(int(p.get("days") or 1))
        if action in ("unread", "recent", "search"):
            q = str(p.get("query") or "")
            if mode == "outlook_app":
                _last = _ol_messages(action == "unread", limit, q if action == "search" else "")
            else:
                if not cfg.get("address") or not cfg.get("password"):
                    return "E-mail is not set up. Add the address and an app password in ⚙ → PLUGIN SETTINGS → E-mail."
                crit = "UNSEEN" if action == "unread" else "ALL"
                if action == "search" and q:
                    safe = q.replace('"', "")
                    crit = f'(OR OR SUBJECT "{safe}" FROM "{safe}" BODY "{safe}")'
                _last = _fetch(cfg, crit, limit)
            return _fmt(_last)
        if action == "read":
            try:
                idx = int(p.get("index") or 1) - 1
            except (TypeError, ValueError):
                idx = 0
            if not _last or not 0 <= idx < len(_last):
                return "List the messages first (unread, recent or search), then read one by number."
            return _fmt([_last[idx]], with_body=True)
        if action in ("send", "reply"):
            body = str(p.get("body") or "").strip()
            if action == "reply":
                try:
                    m = _last[int(p.get("index") or 1) - 1]
                except Exception:
                    return "List the messages first, then reply by number."
                to = email.utils.parseaddr(m.get("reply_to") or m["from"])[1] or m["from"]
                subject = m["subject"] if m["subject"].lower().startswith("re:") else f"Re: {m['subject']}"
                ref = m.get("message_id", "")
            else:
                to = str(p.get("to") or "").strip()
                subject = str(p.get("subject") or "(no subject)")
                ref = ""
            if not to or "@" not in to and mode != "outlook_app":
                return "Who should it go to? I need an e-mail address."
            if not body:
                return "What should the message say?"

            def do_send():
                if mode == "outlook_app":
                    return _ol_send(to, subject, body)
                return _smtp_send(cfg, to, subject, body, ref)
            return confirm_gate.request("email-send", f"Send e-mail to {to}?",
                                        f"Subject: {subject}\n{body[:200]}", do_send)
        return "Unknown action."
    except imaplib.IMAP4.error as e:
        return f"The mail server refused the login ({e}). Use an app password, not the normal password."
    except Exception as e:
        return f"E-mail error: {type(e).__name__}: {str(e)[:200]}"


PLUGIN = {
    "name": "email",
    "description": ("Read and send e-mail: unread (latest unread messages), recent, search by keyword, read N "
                    "(full text of message N from the last list), send (to, subject, body), reply N, and "
                    "calendar (Outlook desktop). Sending asks the user to confirm."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "unread | recent | search | read | send | reply | calendar"},
            "query": {"type": "STRING", "description": "Search words"},
            "index": {"type": "INTEGER", "description": "Message number from the last list"},
            "to": {"type": "STRING", "description": "Recipient e-mail address"},
            "subject": {"type": "STRING", "description": "Subject"},
            "body": {"type": "STRING", "description": "Message text, written in full"},
            "count": {"type": "INTEGER", "description": "How many messages (default 5)"},
            "days": {"type": "INTEGER", "description": "Calendar: days ahead (default 1 = today)"},
        },
        "required": ["action"],
    },
}


def _test(values: dict):
    mode = str(values.get("mode") or "imap")
    if mode == "outlook_app":
        try:
            n = len(_ol_messages(True, 50))
            return True, f"Outlook connected — {n} unread."
        except Exception as e:
            return False, f"Outlook not reachable: {e}"
    try:
        m = _imap(values)
        m.logout()
        return True, "Mailbox login OK."
    except Exception as e:
        return False, str(e)[:200]


PLUGIN_SETTINGS = {
    "namespace": NS,
    "title": "✉ E-mail",
    "fields": [
        {"key": "mode", "label": "Connect through", "type": "choice", "options": ["imap", "outlook_app"],
         "default": "imap"},
        {"key": "address", "label": "E-mail address", "placeholder": "you@gmail.com"},
        {"key": "password", "label": "App password", "type": "password"},
        {"key": "imap_host", "label": "IMAP host (blank = automatic)"},
        {"key": "smtp_host", "label": "SMTP host (blank = automatic)"},
        {"key": "smtp_port", "label": "SMTP port (465 SSL / 587 STARTTLS)"},
    ],
    "action": {"label": "TEST CONNECTION", "run": _test},
}

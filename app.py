"""
DISK / ADVANCED CLEANER TOOL  -  desktop app (FastHTML UI in a pywebview window)
================================================================================

A safe, good-looking disk-cleanup tool. It runs as a native desktop window
(pywebview) with the UI rendered by a small local FastHTML server. All scanning
and deleting happens in this local Python process, so it has full access to your
files and never touches the network.

Setup (once)
------------
    pip install python-fasthtml pywebview

Run
---
    python app.py           opens the native desktop window
    python app.py --web     fallback: opens in your default browser instead

(On Windows you can just double-click  Run-DiskCleaner.bat )

Safety
------
Nothing is deleted until you open the confirm dialog and type DELETE.
Files toggled to KEEP are never touched.
"""

import os
import sys
import threading
import webbrowser

from fasthtml.common import *

# ---------------------------------------------------------------------------
#  File-type catalog
# ---------------------------------------------------------------------------

FILE_TYPES = [
    ("png",   "PNG images",    "*.png",         lambda n, sz: n.endswith(".png")),
    ("jpg",   "JPG images",    "*.jpg, *.jpeg", lambda n, sz: n.endswith((".jpg", ".jpeg"))),
    ("py",    "Python files",  "*.py",          lambda n, sz: n.endswith(".py")),
    ("cpp",   "C++ files",     "*.cpp",         lambda n, sz: n.endswith(".cpp")),
    ("vdi",   "Virtual disks", "*.vdi",         lambda n, sz: n.endswith(".vdi")),
    ("empty", "Empty files",   "0 bytes",       lambda n, sz: sz == 0),
    ("all",   "All file types", "everything",   lambda n, sz: True),
]
TYPE_MAP = {k: (name, hint, test) for k, name, hint, test in FILE_TYPES}
DEFAULT_CHECKED = {"png", "jpg"}

RISKY_DIR_NAMES = {
    "venv", ".venv", "node_modules", ".git", "site-packages",
    "windows", "system32", "program files", "program files (x86)",
    "appdata", "programdata",
}

DISPLAY_CAP = 3000  # max rows rendered; all matches are still counted/deleted

# ---------------------------------------------------------------------------
#  Shared state (single-user local app)
# ---------------------------------------------------------------------------

STATE = {
    "path": "C:\\Users\\chafn\\Downloads" if os.name == "nt"
            else os.path.expanduser("~"),
    "types": set(DEFAULT_CHECKED),
    "files": {},        # id -> dict(path, name, dir, type, size, is_empty, risky, action)
    "scanned": 0,
    "scan_done": False,
    "truncated": False,
    "last_result": None,  # dict after a delete
}
_next_id = [0]


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def size_label(n):
    units = ["B", "KB", "MB", "GB", "TB"]
    i, val = 0, float(n)
    while val >= 1024 and i < len(units) - 1:
        val /= 1024
        i += 1
    return f"{val:.0f} {units[i]}" if i == 0 else f"{val:.1f} {units[i]}"


def risky_component(path):
    parts = path.replace("/", "\\").split("\\")
    for part in parts[:-1]:
        if part.lower() in RISKY_DIR_NAMES:
            return part
    return None


def shorten_dir(d, maxlen=54):
    return d if len(d) <= maxlen else "…" + d[-(maxlen - 1):]


def run_scan(path, types):
    """Walk the tree, populate STATE['files']. Returns (matched, scanned)."""
    tests = [TYPE_MAP[t][2] for t in types] or [lambda n, sz: False]
    files, scanned, truncated = {}, 0, False
    for dirpath, _dirs, names in os.walk(path):
        for name in names:
            scanned += 1
            full = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            low = name.lower()
            if any(t(low, size) for t in tests):
                if len(files) >= DISPLAY_CAP:
                    truncated = True
                    continue
                _next_id[0] += 1
                fid = str(_next_id[0])
                ext = os.path.splitext(name)[1].lower().lstrip(".") or "-"
                files[fid] = {
                    "path": full, "name": name,
                    "dir": shorten_dir(dirpath),
                    "type": "empty" if size == 0 else ext,
                    "size": size, "is_empty": size == 0,
                    "risky": risky_component(full),
                    "action": "DELETE",
                }
    STATE.update(files=files, scanned=scanned, scan_done=True,
                 truncated=truncated, last_result=None)
    return len(files), scanned


def pick_folder_native():
    """Native folder dialog via the pywebview window (cross-platform)."""
    try:
        import webview
        win = webview.windows[0] if webview.windows else None
        if win is None:
            return None
        start = STATE["path"] if os.path.isdir(STATE["path"]) else ""
        try:
            folder_dialog = webview.FileDialog.FOLDER   # pywebview >= 5.4
        except AttributeError:
            folder_dialog = webview.FOLDER_DIALOG       # older versions
        result = win.create_file_dialog(folder_dialog, directory=start)
        if result:
            return result[0]
    except Exception:
        pass
    return None


def counts():
    to_del = [f for f in STATE["files"].values() if f["action"] == "DELETE"]
    to_keep = sum(1 for f in STATE["files"].values() if f["action"] == "KEEP")
    reclaim = sum(f["size"] for f in to_del)
    return len(to_del), to_keep, reclaim


# ---------------------------------------------------------------------------
#  Inline SVG icon set (no external dependencies)
# ---------------------------------------------------------------------------

ICONS = {
    "sparkle": '<path d="M12 3l1.8 4.4L18 9l-4.2 1.6L12 15l-1.8-4.4L6 9l4.2-1.6z"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h3.5l2 2H19a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "folder-open": '<path d="M3 7a2 2 0 0 1 2-2h3.5l2 2H19a2 2 0 0 1 2 2H6.5a2 2 0 0 0-1.9 1.4L3 18z"/>',
    "shield": '<path d="M12 3l7 2.6v5.4c0 4.4-3 7-7 8.8-4-1.8-7-4.4-7-8.8V5.6z"/><path d="M9 12l2 2 4-4.2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20.5 20.5l-4.2-4.2"/>',
    "drives": '<rect x="3" y="4.5" width="18" height="6.5" rx="1.8"/><rect x="3" y="13" width="18" height="6.5" rx="1.8"/><path d="M16.5 6.5v2.5M16.5 15v2.5"/>',
    "file": '<path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9z"/><path d="M13 3v6h6"/>',
    "file-x": '<path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9z"/><path d="M13 3v6h6"/><path d="M9.2 13.8l3.6 3.6M12.8 13.8l-3.6 3.6"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v2"/><path d="M6 7l1 12a2 2 0 0 0 2 1.8h6a2 2 0 0 0 2-1.8L18 7"/>',
    "check": '<path d="M20 7L10 17l-5-5"/>',
    "check-circle": '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 12.5l2.5 2.5 4.5-5.5"/>',
    "warning-circle": '<circle cx="12" cy="12" r="8.5"/><path d="M12 8v4.5"/><path d="M12 16h0.01"/>',
    "warning": '<path d="M12 4L3 19h18z"/><path d="M12 10v4"/><path d="M12 17h0.01"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
}


def Icon(name, size=16, color=None, fill=False, weight=1.8, style=""):
    st = f"width:{size}px;height:{size}px;display:inline-block;vertical-align:middle;flex:none;{style}"
    if color:
        st += f"color:{color};"
    stroke = "none" if fill else "currentColor"
    fillv = "currentColor" if fill else "none"
    return NotStr(
        f'<svg viewBox="0 0 24 24" fill="{fillv}" stroke="{stroke}" '
        f'stroke-width="{weight}" stroke-linecap="round" stroke-linejoin="round" '
        f'style="{st}">{ICONS[name]}</svg>')


# ---------------------------------------------------------------------------
#  Styles
# ---------------------------------------------------------------------------

CSS = """
:root{
  --bg:#161826; --surface:#232532; --text:#e9e9ed; --accent:#9184d9;
  --n300:#cfd3e5; --n400:#b2b6ca; --n500:#9397ab; --n600:#75798c;
  --n700:#595d6c; --n800:#3f424d; --n900:#292b31;
  --acc300:#d2cefd; --acc700:#5d5294; --acc900:#2b2741;
  --divider:rgba(233,233,237,.16);
  --danger:#e08f8f; --danger-fill:#3a2530; --danger-line:#7d4a53;
  --safe:#8fcf9f; --safe-fill:#1f3129; --safe-line:#3e6a52;
  --track:#191b28; --radius-md:8px; --radius-lg:14px; --shadow-sm:0 0 0 1px #3f424d;
  --font:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);font-family:var(--font);color:var(--text);min-height:100vh;-webkit-font-smoothing:antialiased}
.window{width:100%;min-height:100vh;background:var(--bg);animation:fade .35s ease}
@keyframes fade{from{opacity:0}to{opacity:1}}

.header{padding:26px 30px 20px;display:flex;align-items:flex-start;gap:20px}
.header h1{font-size:27px;letter-spacing:-.01em;margin-bottom:6px;font-weight:650}
.header .sub{font-size:13px;color:var(--n400);display:flex;align-items:center;gap:7px}
.pill{display:inline-flex;align-items:center;gap:8px;padding:7px 13px;border-radius:999px;white-space:nowrap;
  font-size:11px;letter-spacing:.1em;text-transform:uppercase;font-weight:600}
.pill .dot{width:7px;height:7px;border-radius:50%}
.pill.safe{background:var(--safe-fill);border:1px solid var(--safe-line);color:var(--safe)}
.pill.safe .dot{background:var(--safe);box-shadow:0 0 8px var(--safe)}
.pill.idle{background:var(--n900);border:1px solid var(--n800);color:var(--n400)}
.pill.idle .dot{background:var(--n500)}
.pill.busy{background:var(--acc900);border:1px solid var(--acc700);color:var(--acc300)}
.pill.busy .dot{background:var(--accent);animation:blink 1s infinite}
@keyframes blink{50%{opacity:.3}}

.body{padding:0 30px 30px;display:flex;flex-direction:column;gap:20px}
.card{background:var(--surface);border-radius:var(--radius-lg);box-shadow:var(--shadow-sm)}
.pad{padding:20px}

label.fld{display:block}
.fld .cap{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--n400);margin-bottom:8px;display:block}
.inputwrap{position:relative}
.inputwrap .ic{position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--n400)}
.input{width:100%;height:38px;background:var(--track);border:1px solid var(--n800);border-radius:var(--radius-md);
  color:var(--text);font-family:var(--mono);font-size:13px;padding:0 12px 0 34px;transition:.15s}
.input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(145,132,217,.18)}

.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:0;border-radius:var(--radius-md);
  font-family:var(--font);font-size:13.5px;font-weight:550;cursor:pointer;padding:0 16px;height:36px;transition:.15s;white-space:nowrap}
.btn:active{transform:translateY(1px)}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:#a29cef;box-shadow:0 4px 14px rgba(145,132,217,.4)}
.btn-secondary{background:var(--track);color:var(--n300);box-shadow:inset 0 0 0 1px var(--n800)}
.btn-secondary:hover{background:#20222f;color:var(--text)}
.btn-danger{background:var(--danger-fill);color:var(--danger);box-shadow:inset 0 0 0 1px var(--danger-line)}
.btn-danger:hover{background:#4a2c38}
.btn[disabled]{opacity:.5;cursor:not-allowed}

.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:2px}
.type-card{display:flex;align-items:center;gap:11px;padding:11px 13px;border-radius:var(--radius-md);
  background:var(--track);border:1px solid var(--divider);cursor:pointer;transition:.15s;position:relative}
.type-card:hover{border-color:var(--n700)}
.type-card input{position:absolute;opacity:0;pointer-events:none}
.type-box{width:18px;height:18px;flex:none;border-radius:5px;border:1.5px solid var(--n600);
  display:grid;place-items:center;transition:.15s;color:#fff}
.type-box svg{opacity:0;transform:scale(.5);transition:.15s}
.type-name{display:block;font-size:13.5px;color:var(--n300)}
.type-hint{display:block;font-size:11px;color:var(--n500);font-family:var(--mono)}
.type-card:has(input:checked){background:var(--acc900);border-color:var(--acc700)}
.type-card:has(input:checked) .type-box{background:var(--accent);border-color:var(--accent)}
.type-card:has(input:checked) .type-box svg{opacity:1;transform:none}
.type-card:has(input:checked) .type-name{color:var(--text)}
.type-card:has(input:checked) .type-hint{color:var(--acc300)}

.progress{flex:1;height:6px;border-radius:999px;background:var(--track);overflow:hidden}
.progress > div{height:100%;background:linear-gradient(90deg,var(--acc700),var(--accent))}
.progress.busy > div{width:40%!important;animation:slide 1.1s ease-in-out infinite}
@keyframes slide{0%{margin-left:-40%}100%{margin-left:100%}}

.summary{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:1px;background:var(--divider);
  border-radius:var(--radius-lg);overflow:hidden;box-shadow:var(--shadow-sm)}
.summary .cell{background:var(--surface);padding:16px 20px;display:flex;flex-direction:column;justify-content:center}
.summary .cell.reclaim{background:var(--danger-fill);flex-direction:row;align-items:center;gap:14px}
.summary .big{font-size:26px;font-weight:600;line-height:1}
.summary .lbl{font-size:12px;color:var(--n400);margin-top:4px}

.tbl-head{display:flex;align-items:center;gap:14px;padding:15px 20px;border-bottom:1px solid var(--divider);flex-wrap:wrap}
.tbl-head .title{font-size:15px;font-weight:600}
.tag{font-size:11px;font-weight:600;padding:3px 9px;border-radius:999px;background:var(--n900);color:var(--n400);border:1px solid var(--n800)}
.hint{font-size:12px;color:var(--n500)}
.scroll{max-height:360px;overflow-y:auto}
.scroll::-webkit-scrollbar{width:12px;height:12px}
.scroll::-webkit-scrollbar-track{background:transparent}
.scroll::-webkit-scrollbar-thumb{background:var(--n800);border-radius:8px;border:3px solid var(--surface)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
thead tr{position:sticky;top:0;z-index:1;background:var(--surface)}
th{text-align:left;font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--n500);font-weight:600;padding:10px 20px}
tbody tr{border-top:1px solid var(--divider);transition:background .12s}
tbody tr:hover{background:rgba(255,255,255,.02)}
td{padding:9px 20px;vertical-align:middle}

.toggle{display:inline-flex;border-radius:999px;overflow:hidden;height:26px;cursor:pointer;border:1px solid var(--n800)}
.toggle span{display:grid;place-items:center;padding:0 11px;font-size:10.5px;font-weight:600;letter-spacing:.04em;color:var(--n600);transition:.12s}
.toggle.del{border-color:var(--danger-line)}
.toggle.del .d{background:var(--danger-fill);color:var(--danger)}
.toggle.keep{border-color:var(--safe-line)}
.toggle.keep .k{background:var(--safe-fill);color:var(--safe)}
.fname{font-family:var(--mono);font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fdir{font-family:var(--mono);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--n600)}
.typetag{font-size:11px;font-family:var(--mono);color:var(--n400);background:var(--track);padding:2px 8px;border-radius:5px;border:1px solid var(--divider)}
.riskflag{display:inline-flex;align-items:center;gap:4px;font-size:10px;color:var(--danger);margin-left:8px}

.footer{display:flex;align-items:center;gap:16px;padding:16px 28px;background:linear-gradient(#1b1d29,#171925);border-top:1px solid #2a2d3d;flex-wrap:wrap}
.footer .msg{font-size:13px;color:var(--n300)}
.footer .msg b{color:var(--danger)}

.placeholder{padding:54px 20px;text-align:center;color:var(--n500)}
.placeholder .big{font-size:15px;color:var(--n300);margin:14px 0 4px}

.banner{display:flex;align-items:center;gap:12px;padding:13px 18px;border-radius:var(--radius-md);font-size:13px}
.banner.ok{background:var(--safe-fill);border:1px solid var(--safe-line);color:var(--safe)}
.banner.warn{background:var(--danger-fill);border:1px solid var(--danger-line);color:var(--danger)}

.overlay{position:fixed;inset:0;background:rgba(8,9,15,.66);backdrop-filter:blur(3px);
  display:grid;place-items:center;z-index:50;animation:fade .18s}
@keyframes fade{from{opacity:0}to{opacity:1}}
.modal{width:440px;max-width:92vw;background:var(--surface);border-radius:var(--radius-lg);
  box-shadow:0 24px 70px rgba(0,0,0,.6),0 0 0 1px var(--n700);overflow:hidden;animation:pop .2s cubic-bezier(.2,.9,.3,1)}
@keyframes pop{from{transform:scale(.94);opacity:0}to{transform:none;opacity:1}}
.modal .accent{height:3px;background:var(--danger)}
.modal .mpad{padding:24px 26px}
.modal h3{font-size:17px;color:var(--danger);margin-bottom:8px;display:flex;align-items:center;gap:8px}
.modal p{font-size:13.5px;color:var(--n300);line-height:1.5}
.modal .confirm-input{width:100%;height:40px;background:var(--track);border:1px solid var(--n800);border-radius:var(--radius-md);
  color:var(--text);font-family:var(--mono);font-size:14px;text-align:center;letter-spacing:.15em;margin-top:14px}
.modal .confirm-input:focus{outline:none;border-color:var(--danger);box-shadow:0 0 0 3px rgba(224,143,143,.18)}
.modal .mrow{display:flex;justify-content:flex-end;gap:10px;margin-top:18px}

.spin{animation:spin 0.7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.htmx-indicator{display:none}
.htmx-request .htmx-indicator{display:inline-flex}
.htmx-request .indicator-hide{display:none}
"""


# ---------------------------------------------------------------------------
#  Component renderers
# ---------------------------------------------------------------------------

def status_pill(oob=False):
    lr = STATE["last_result"]
    if lr is not None:
        cls, txt = "safe", "Cleanup complete"
    elif STATE["scan_done"]:
        cls, txt = "safe", "Scan complete"
    else:
        cls, txt = "idle", "Ready"
    attrs = {"id": "status-pill", "cls": f"pill {cls}"}
    if oob:
        attrs["hx_swap_oob"] = "true"
    return Span(Span(cls="dot"), Span(txt), **attrs)


def scan_meta(oob=False):
    done = STATE["scan_done"]
    txt = (f"{STATE['scanned']:,} files scanned" if done
           else "Ready to scan")
    bar = Div(Div(style=f"width:{'100%' if done else '0'}"), cls="progress",
              id="scan-progress")
    attrs = {"id": "scan-meta", "style": "display:flex;align-items:center;gap:12px;flex:1"}
    if oob:
        attrs["hx_swap_oob"] = "true"
    return Div(bar, Span(txt, cls="hint", style="white-space:nowrap"), **attrs)


def type_card(key):
    name, hint, _ = TYPE_MAP[key]
    return Label(
        Input(type="checkbox", name="types", value=key,
              checked=(key in STATE["types"])),
        Span(Icon("check", 12, weight=3), cls="type-box"),
        Span(Span(name, cls="type-name"), Span(hint, cls="type-hint"),
             style="min-width:0"),
        cls="type-card")


def setup_card():
    return Form(
        Div(
            Label(
                Span("Location", cls="cap"),
                Div(Span(Icon("folder", 16), cls="ic"),
                    Input(value=STATE["path"], name="path", cls="input",
                          placeholder="C:\\Users\\you\\Downloads   or   C:\\",
                          autocomplete="off"),
                    cls="inputwrap", id="loc-wrap"),
                cls="fld", style="flex:1;min-width:0"),
            Button(Icon("folder-open", 15), "Browse", type="button",
                   cls="btn btn-secondary", style="height:38px",
                   hx_post="/browse", hx_target="#dynamic", hx_swap="none"),
            style="display:flex;gap:12px;align-items:flex-end;margin-bottom:18px"),

        Span("What to scan", cls="cap"),
        Div(*[type_card(k) for k, *_ in FILE_TYPES], cls="grid"),

        Div(
            Button(
                Span(Icon("search", 15), "Scan", cls="indicator-hide",
                     style="display:inline-flex;align-items:center;gap:8px"),
                Span(Icon("sparkle", 15, style="", weight=2), "Scanning…",
                     cls="htmx-indicator",
                     style="align-items:center;gap:8px"),
                cls="btn btn-primary", style="height:38px;padding:0 22px",
                type="submit"),
            scan_meta(),
            style="display:flex;align-items:center;gap:12px;margin-top:18px"),

        hx_post="/scan", hx_target="#dynamic", hx_swap="outerHTML",
        cls="card pad")


def summary_bar():
    to_del, to_keep, reclaim = counts()
    return Div(
        Div(Icon("drives", 26, color="var(--danger)"),
            Div(Div(size_label(reclaim), cls="big", style="color:var(--danger)"),
                Div(f"to reclaim · {to_del} files flagged",
                    cls="lbl", style="color:color-mix(in srgb,var(--danger) 80%,#fff)")),
            cls="cell reclaim"),
        Div(Div(str(to_del), cls="big", style="color:var(--danger)"),
            Div("marked for delete", cls="lbl"), cls="cell"),
        Div(Div(str(to_keep), cls="big", style="color:var(--safe)"),
            Div("kept safe", cls="lbl"), cls="cell"),
        cls="summary")


def action_toggle(fid, action):
    if action == "DELETE":
        return Div(Span("KEEP", cls="k"), Span("DELETE", cls="d"),
                   cls="toggle del", title="Click to keep",
                   hx_post=f"/toggle/{fid}", hx_target="#dynamic", hx_swap="outerHTML")
    return Div(Span("KEEP", cls="k"), Span("DELETE", cls="d"),
               cls="toggle keep", title="Click to mark for delete",
               hx_post=f"/toggle/{fid}", hx_target="#dynamic", hx_swap="outerHTML")


def result_row(fid, f):
    delete = f["action"] == "DELETE"
    icon = "file-x" if delete else "file"
    icolor = "var(--danger)" if delete else "var(--n500)"
    ncolor = "var(--text)" if delete else "var(--n400)"
    risk = (Span(Icon("warning", 12), "risky", cls="riskflag")
            if f["risky"] else "")
    return Tr(
        Td(action_toggle(fid, f["action"]), style="width:150px"),
        Td(Div(Icon(icon, 16, color=icolor),
               Div(Div(f["name"], risk, cls="fname", style=f"color:{ncolor}"),
                   Div(f["dir"], cls="fdir"), style="min-width:0"),
               style="display:flex;align-items:center;gap:10px;min-width:0"),
           style="max-width:1px"),
        Td(Span(f["type"], cls="typetag"), style="width:70px"),
        Td(size_label(f["size"]), style="width:90px;text-align:right;font-family:var(--mono);font-size:12.5px;"
           + ("color:var(--n300)" if delete else "color:var(--n500)")))


def results_card():
    files = STATE["files"]
    n = len(files)
    trunc = (Span(f"showing first {DISPLAY_CAP:,}", cls="hint")
             if STATE["truncated"] else "")
    return Div(
        Div(Span("Results", cls="title"),
            Span(f"{n} files", cls="tag"),
            Span("Toggle each row to keep it or mark it for deletion.", cls="hint"),
            trunc,
            Div(Button(Icon("check-circle", 15), "Keep all", cls="btn btn-secondary",
                       style="font-size:13px;height:32px",
                       hx_post="/bulk/KEEP", hx_target="#dynamic", hx_swap="outerHTML"),
                Button(Icon("trash", 15), "Select all", cls="btn btn-secondary",
                       style="font-size:13px;height:32px",
                       hx_post="/bulk/DELETE", hx_target="#dynamic", hx_swap="outerHTML"),
                style="margin-left:auto;display:flex;gap:8px"),
            cls="tbl-head"),
        Div(Table(
            Thead(Tr(Th("Action"), Th("File"), Th("Type"),
                     Th("Size", style="text-align:right"))),
            Tbody(*[result_row(fid, f) for fid, f in files.items()])),
            cls="scroll"),
        cls="card", style="overflow:hidden")


def footer_bar():
    to_del, _to_keep, reclaim = counts()
    disabled = to_del == 0
    return Div(
        Icon("warning-circle", 18, color="var(--danger)"),
        Span(NotStr(f'Deleting <b>{to_del} files</b> frees <b>{size_label(reclaim)}</b>. '
                    'This can’t be undone.'), cls="msg"),
        Div(Button("Delete " + (f"{to_del} files…" if to_del else "files…"),
                   Icon("trash", 15, fill=True) if not disabled else "",
                   cls="btn btn-danger", style="height:40px;padding:0 20px",
                   disabled=disabled,
                   hx_get="/confirm", hx_target="#modal", hx_swap="innerHTML"),
            style="margin-left:auto;display:flex;gap:10px"),
        cls="footer")


def result_banner():
    lr = STATE["last_result"]
    if not lr:
        return ""
    if lr["failed"]:
        return Div(Icon("warning-circle", 16),
                   NotStr(f'Deleted <b>{lr["deleted"]}</b>, freed <b>{lr["freed"]}</b>. '
                          f'<b>{lr["failed"]}</b> could not be deleted (in use or '
                          f'protected). Kept {lr["kept"]}.'),
                   cls="banner warn")
    return Div(Icon("check-circle", 16),
               NotStr(f'Cleanup complete — deleted <b>{lr["deleted"]}</b> files, '
                      f'freed <b>{lr["freed"]}</b>. Kept {lr["kept"]}.'),
               cls="banner ok")


def dynamic():
    """The whole region that changes after scan/toggle/delete."""
    if not STATE["scan_done"]:
        inner = Div(
            Icon("search", 34, color="var(--n600)"),
            Div("No scan yet", cls="big"),
            Div("Choose a location and file types above, then press Scan.",
                cls="hint"),
            cls="placeholder", style="display:flex;flex-direction:column;align-items:center;gap:2px")
        return Div(Div(inner, cls="card"), id="dynamic",
                   style="display:flex;flex-direction:column;gap:20px")

    banner = result_banner()
    if len(STATE["files"]) == 0:
        body = [banner] if banner else []
        body.append(Div(
            Icon("check-circle", 34, color="var(--safe)"),
            Div("Nothing to clean", cls="big"),
            Div(f"Scanned {STATE['scanned']:,} files — no matches for the "
                "selected types here.", cls="hint"),
            cls="placeholder", style="display:flex;flex-direction:column;align-items:center;gap:2px"))
        return Div(*[b for b in body if b], id="dynamic",
                   style="display:flex;flex-direction:column;gap:20px")

    children = []
    if banner:
        children.append(banner)
    children += [summary_bar(), results_card(), footer_bar()]
    return Div(*children, id="dynamic",
               style="display:flex;flex-direction:column;gap:20px")


# ---------------------------------------------------------------------------
#  App
# ---------------------------------------------------------------------------

app, rt = fast_app(pico=False, hdrs=(
    Meta(name="viewport", content="width=device-width, initial-scale=1"),
    Title("Disk Cleaner"),
    Style(CSS),
))


def page():
    return Div(
        Div(  # header
            Div(H1("Advanced Disk Cleaner"),
                P(Icon("shield", 15, color="var(--safe)"),
                  "Safe mode — nothing is removed until you confirm the delete.",
                  cls="sub"),
                style="flex:1;min-width:0"),
            status_pill(),
            cls="header"),
        Div(setup_card(), dynamic(), cls="body"),
        Div(id="modal"),
        cls="window")


@rt("/")
def get():
    return page()


@rt("/scan")
async def post(request):
    form = await request.form()
    path = (form.get("path") or "").strip().strip('"')
    types = set(form.getlist("types"))
    STATE["path"] = path
    STATE["types"] = types

    if not path or not os.path.isdir(path):
        STATE.update(scan_done=False)
        d = dynamic()
        # show an inline error banner in place of results
        err = Div(Icon("warning-circle", 16),
                  NotStr(f'<b>{path or "(empty)"}</b> is not a valid folder or drive. '
                         'Paste a path like C:\\Users\\you\\Downloads'),
                  cls="banner warn")
        return Div(err, id="dynamic",
                   style="display:flex;flex-direction:column;gap:20px"), \
            status_pill(oob=True), scan_meta(oob=True)
    if not types:
        return Div(Div(Icon("warning-circle", 16),
                       "Select at least one file type to scan.", cls="banner warn"),
                   id="dynamic", style="display:flex;flex-direction:column;gap:20px"), \
            status_pill(oob=True), scan_meta(oob=True)

    run_scan(path, types)
    return dynamic(), status_pill(oob=True), scan_meta(oob=True)


@rt("/browse")
def post():
    chosen = pick_folder_native()
    if chosen:
        STATE["path"] = chosen
    # Update just the location input via OOB; leave results untouched.
    return Div(Span(Icon("folder", 16), cls="ic"),
               Input(value=STATE["path"], name="path", cls="input",
                     autocomplete="off"),
               cls="inputwrap", id="loc-wrap", hx_swap_oob="true")


@rt("/toggle/{fid}")
def post(fid: str):
    f = STATE["files"].get(fid)
    if f:
        f["action"] = "KEEP" if f["action"] == "DELETE" else "DELETE"
    STATE["last_result"] = None
    return dynamic()


@rt("/bulk/{action}")
def post(action: str):
    action = "KEEP" if action.upper() == "KEEP" else "DELETE"
    for f in STATE["files"].values():
        f["action"] = action
    STATE["last_result"] = None
    return dynamic()


@rt("/confirm")
def get():
    to_del, _k, reclaim = counts()
    risky = sum(1 for f in STATE["files"].values()
                if f["action"] == "DELETE" and f["risky"])
    warn = (Div(Icon("warning", 14, color="var(--danger)"),
                f"{risky} of these are inside important folders "
                "(venv, node_modules, .git, Windows…).",
                style="display:flex;gap:7px;align-items:center;font-size:12px;color:var(--danger);margin-top:10px")
            if risky else "")
    modal = Div(Div(
        Div(cls="accent"),
        Div(H3(Icon("warning-circle", 18), "Confirm deletion"),
            P(NotStr(f"<b style='color:var(--danger)'>{to_del} file(s)</b> "
                     f"totalling <b style='color:var(--danger)'>{size_label(reclaim)}</b> "
                     "will be permanently deleted. This cannot be undone.")),
            warn,
            Form(
                Input(name="confirm", cls="confirm-input", placeholder="type DELETE",
                      autocomplete="off",
                      oninput="this.closest('form').querySelector('.godel').disabled = this.value!=='DELETE'"),
                Div(Button("Cancel", type="button", cls="btn btn-secondary",
                           style="height:40px;padding:0 18px",
                           onclick="document.getElementById('modal').innerHTML=''"),
                    Button(Icon("trash", 15, fill=True), "Delete", type="submit",
                           cls="btn btn-danger godel", style="height:40px;padding:0 20px",
                           disabled=True),
                    cls="mrow"),
                hx_post="/delete", hx_target="#dynamic", hx_swap="outerHTML"),
            cls="mpad"),
        cls="modal"),
        cls="overlay",
        onclick="if(event.target===this)document.getElementById('modal').innerHTML=''")
    return modal


@rt("/delete")
async def post(request):
    form = await request.form()
    if (form.get("confirm") or "") != "DELETE":
        # keep modal open (shouldn't happen, button is gated) — just clear it
        return dynamic(), Div(id="modal", hx_swap_oob="true")

    deleted = failed = freed = 0
    for fid in list(STATE["files"].keys()):
        f = STATE["files"][fid]
        if f["action"] != "DELETE":
            continue
        try:
            os.remove(f["path"])
            freed += f["size"]
            deleted += 1
            del STATE["files"][fid]
        except Exception:
            failed += 1
    kept = sum(1 for f in STATE["files"].values() if f["action"] == "KEEP")
    STATE["last_result"] = {"deleted": deleted, "failed": failed,
                            "freed": size_label(freed), "kept": kept}
    return (dynamic(),
            Div(id="modal", hx_swap_oob="true"),
            status_pill(oob=True))


# ---------------------------------------------------------------------------
#  Launch  -  native desktop window via pywebview
# ---------------------------------------------------------------------------

HOST, PORT = "127.0.0.1", 8000


def _find_free_port(preferred):
    import socket
    for p in (preferred, 0):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((HOST, p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            s.close()
    return preferred


def _run_server(port):
    import uvicorn
    # No reloader: reload spawns a subprocess and breaks the threaded window.
    uvicorn.run(app, host=HOST, port=port, log_level="warning")


def _wait_until_up(port, timeout=15):
    import socket
    import time
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((HOST, port)) == 0:
                return True
        time.sleep(0.15)
    return False


def main():
    # Browser fallback: `python app.py --web` serves in the default browser
    # instead of opening a native window (useful if pywebview is unavailable).
    port = _find_free_port(PORT)

    if "--web" in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{port}")).start()
        print(f"\n  DISK / ADVANCED CLEANER TOOL  (web mode)")
        print(f"  Open in your browser:  http://{HOST}:{port}\n")
        _run_server(port)
        return

    try:
        import webview
    except ImportError:
        print("pywebview is not installed. Install it with:\n"
              "    pip install pywebview\n"
              "or run in browser mode:  python app.py --web")
        sys.exit(1)

    threading.Thread(target=_run_server, args=(port,), daemon=True).start()
    if not _wait_until_up(port):
        print("Server did not start in time.")
        sys.exit(1)

    webview.create_window(
        "Disk Cleaner",
        f"http://{HOST}:{port}",
        width=1180, height=880, min_size=(940, 660),
        background_color="#0e0f18")
    webview.start()  # blocks until the window is closed


if __name__ == "__main__":
    main()

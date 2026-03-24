#!/usr/bin/env python3
"""Rich two-line status line for Claude Code."""

import colorsys
import json
import os
import subprocess
import sys
import time

# ── ANSI primitives ──────────────────────────────────────────────

ESC = "\x1b"
RST = f"{ESC}[0m"


def _sgr(code: str, text: str) -> str:
    return f"{ESC}[{code}m{text}{RST}"


def bold(text: str) -> str:
    return _sgr("1", text)


def faint(text: str) -> str:
    return _sgr("2", text)


def color256(n: int, text: str) -> str:
    return _sgr(f"38;5;{n}", text)


def color256_bold(n: int, text: str) -> str:
    return _sgr(f"1;38;5;{n}", text)


def truecolor_fg(r: int, g: int, b: int, text: str) -> str:
    return f"{ESC}[38;2;{r};{g};{b}m{text}{RST}"


def truecolor_bg(r: int, g: int, b: int, text: str) -> str:
    return f"{ESC}[48;2;{r};{g};{b}m{text}{RST}"


# ── Palette (256-color indices) ──────────────────────────────────

C_MODEL = 205
C_BRANCH = 81
C_CLEAN = 82
C_WARN = 220
C_ALERT = 196
C_MUTED = 243
C_TEXT = 255

VIM_PALETTE = {"NORMAL": C_BRANCH, "INSERT": C_CLEAN, "VISUAL": C_MODEL}

# ── Pre-computed constants ───────────────────────────────────────

_TILDE = os.path.expanduser("~")
_BAR_TICKS = " ▏▎▍▌▋▊▉█"
_EMPTY_BG = (50, 50, 50)


# ── Color interpolation via HSL ──────────────────────────────────

def _severity_rgb(ratio: float) -> tuple[int, int, int]:
    """Map 0.0–1.0 severity to an RGB tuple via HSL hue rotation.

    Hue sweeps from 120° (green) through 60° (yellow) to 0° (red).
    Saturation 0.85, lightness 0.55 keeps colours vibrant on dark backgrounds.
    """
    ratio = max(0.0, min(1.0, ratio))
    hue = (1.0 - ratio) * (120.0 / 360.0)  # 0.333 → 0.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.55, 0.85)
    return int(r * 255), int(g * 255), int(b * 255)


def tint(pct: float, text: str) -> str:
    """Colour *text* according to a 0–100 severity percentage."""
    if pct <= 0:
        return faint(text)
    r, g, b = _severity_rgb(pct / 100)
    return truecolor_fg(r, g, b, text)


# ── Gauge rendering ──────────────────────────────────────────────

def gauge(pct: float, cols: int = 10) -> str:
    """Render a fractional-block gauge with severity colouring."""
    pct = max(0.0, min(100.0, pct))
    if pct <= 0:
        return blank_gauge(cols)

    span = pct * cols / 100
    whole = int(span)
    part = int((span - whole) * 8)

    lit = "█" * whole
    if whole < cols:
        lit += _BAR_TICKS[part]
        gap = cols - whole - 1
    else:
        gap = 0

    r, g, b = _severity_rgb(pct / 100)
    head = f"{ESC}[38;2;{r};{g};{b}m{lit}{RST}"
    tail = truecolor_bg(*_EMPTY_BG, " " * gap) if gap else ""
    return head + tail


def blank_gauge(cols: int = 6) -> str:
    return truecolor_bg(*_EMPTY_BG, " " * cols)


# ── Formatters ───────────────────────────────────────────────────

def compact_duration(ms: float) -> str:
    secs = int(ms / 1000)
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def countdown(epoch: float) -> str:
    left = int(epoch - time.time())
    if left <= 0:
        return "now"
    if left < 60:
        return f"{left}s"
    m, _ = divmod(left, 60)
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def abbrev_path(path: str) -> str:
    return "~" + path[len(_TILDE):] if path.startswith(_TILDE) else path


# ── Rate-limit segment ───────────────────────────────────────────

def rate_segment(tag: str, pct, resets_at) -> str:
    if pct is None:
        return faint(f"{tag} ") + blank_gauge(6) + " " + faint("--%")
    s = tint(pct, f"{tag} ") + gauge(pct, 6) + " " + tint(pct, f"{pct:.0f}%")
    if resets_at is not None:
        s += tint(pct, f"({countdown(resets_at)})")
    return s


# ── Git ──────────────────────────────────────────────────────────

def git_summary(cwd: str) -> str:
    if not cwd or not os.path.isdir(cwd):
        return ""

    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain=v2", "--branch", "-unormal"],
            capture_output=True, text=True, timeout=2,
        )
        if proc.returncode != 0:
            return ""
    except Exception:
        return ""

    ref = ""
    up_ahead = 0
    up_behind = 0
    n_staged = 0
    n_modified = 0
    n_untracked = 0

    for ln in proc.stdout.splitlines():
        if ln.startswith("# branch.head "):
            ref = ln[14:]
        elif ln.startswith("# branch.ab "):
            tokens = ln[12:].split()
            if len(tokens) >= 2:
                up_ahead = int(tokens[0][1:])
                up_behind = int(tokens[1][1:])
        elif ln[0] in "12u":
            xy = ln[2:4]
            if xy[0] in "MADRC":
                n_staged += 1
            if xy[1] in "MD":
                n_modified += 1
        elif ln[0] == "?":
            n_untracked += 1

    if ref == "(detached)":
        try:
            h = subprocess.run(
                ["git", "-C", cwd, "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=2,
            )
            ref = h.stdout.strip()[:7] if h.returncode == 0 else ""
        except Exception:
            ref = ""

    if not ref:
        return ""

    chunks = [color256(C_BRANCH, "\ue0a0 " + ref)]

    indicators = ""
    if n_modified:
        indicators += color256(C_WARN, f" *{n_modified}")
    if n_staged:
        indicators += color256(C_CLEAN, f" +{n_staged}")
    if n_untracked:
        indicators += color256(C_ALERT, f" ?{n_untracked}")
    chunks.append(indicators)

    arrows = []
    if up_ahead > 0:
        arrows.append(color256(C_CLEAN, f"↑{up_ahead}"))
    if up_behind > 0:
        arrows.append(color256(C_ALERT, f"↓{up_behind}"))
    if arrows:
        chunks.append(" " + " ".join(arrows))

    return "".join(chunks)


# ── Entrypoint ───────────────────────────────────────────────────

def render(data: dict) -> str | None:
    model_label = data.get("model", {}).get("display_name", "")
    cwd = data.get("workspace", {}).get("current_dir", "")
    ctx_used = data.get("context_window", {}).get("used_percentage", 0)

    costs = data.get("cost", {})
    usd = costs.get("total_cost_usd", 0)
    elapsed_ms = costs.get("total_duration_ms", 0)

    limits = data.get("rate_limits", {})
    h5_pct = limits.get("five_hour", {}).get("used_percentage", None)
    h5_rst = limits.get("five_hour", {}).get("resets_at", None)
    d7_pct = limits.get("seven_day", {}).get("used_percentage", None)
    d7_rst = limits.get("seven_day", {}).get("resets_at", None)

    vim = data.get("vim", {}).get("mode", "")
    wt = data.get("worktree", {}).get("name", "")

    div = faint(" │ ")

    # ── upper row: identity + workspace ──
    upper = []
    if model_label:
        upper.append(color256_bold(C_MODEL, f" {model_label}"))
    if cwd:
        upper.append(color256(C_TEXT, abbrev_path(cwd)))
    vcs = git_summary(cwd)
    if vcs:
        upper.append(vcs)
    if wt:
        upper.append(color256(C_WARN, f"⊞ {wt}"))
    if vim:
        vc = VIM_PALETTE.get(vim.upper(), C_TEXT)
        upper.append(color256_bold(vc, f"[{vim.upper()}]"))

    # ── lower row: metrics ──
    lower = []
    lower.append(tint(ctx_used, "ctx ") + gauge(ctx_used) + " " + tint(ctx_used, f"{ctx_used:.0f}%"))
    lower.append(rate_segment("5h", h5_pct, h5_rst))
    lower.append(rate_segment("7d", d7_pct, d7_rst))
    lower.append(color256(C_TEXT, f"${usd:.2f}") if usd > 0 else faint("$--.--"))
    lower.append(faint(compact_duration(elapsed_ms)) if elapsed_ms > 0 else faint("--:--"))

    rows = [r for r in [div.join(upper), div.join(lower)] if r]
    return "\n".join(rows) if rows else None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return
    output = render(payload)
    if output:
        print(output)


if __name__ == "__main__":
    main()

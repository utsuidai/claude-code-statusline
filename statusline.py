#!/usr/bin/env python3
"""Claude Code status line: rich two-line display."""

import json
import os
import subprocess
import sys
import time


def _ansi(code: str, text: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m"


def bold(text: str) -> str:
    return _ansi("1", text)


def dim(text: str) -> str:
    return _ansi("2", text)


def fg(color: int, text: str) -> str:
    return _ansi(f"38;5;{color}", text)


def bold_fg(color: int, text: str) -> str:
    return _ansi(f"1;38;5;{color}", text)


MAGENTA = 205
CYAN = 81
GREEN = 82
YELLOW = 220
RED = 196
GRAY = 243
WHITE = 255

BLOCKS = " ▏▎▍▌▋▊▉█"
_DARK_BG = "\x1b[48;2;50;50;50m"
_RESET = "\x1b[0m"
_HOME = os.path.expanduser("~")
_MODE_COLORS = {"NORMAL": CYAN, "INSERT": GREEN, "VISUAL": MAGENTA}


def gradient(pct: float) -> str:
    """Return truecolor ANSI escape for green→yellow→red gradient."""
    pct = max(0, min(100, pct))
    if pct < 50:
        r = int(pct * 5.1)
        return f"\x1b[38;2;{r};200;80m"
    else:
        g = int(200 - (pct - 50) * 4)
        return f"\x1b[38;2;255;{max(g, 0)};60m"


def colorize_pct(pct: float) -> int:
    if pct < 50:
        return GREEN
    elif pct < 80:
        return YELLOW
    return RED


def progress_bar(pct: float, width: int = 10) -> str:
    """Draw a fine-grained progress bar with truecolor gradient."""
    pct = max(0, min(100, pct))
    filled = pct * width / 100
    full = int(filled)
    frac = int((filled - full) * 8)
    filled_str = "█" * full
    if full < width:
        filled_str += BLOCKS[frac]
        empty = width - full - 1
    else:
        empty = 0
    empty_str = f"{_DARK_BG}{' ' * empty}{_RESET}" if empty else ""
    return gradient(pct) + filled_str + _RESET + empty_str


def empty_bar(width: int = 6) -> str:
    return f"{_DARK_BG}{' ' * width}{_RESET}"


def format_duration(ms: float) -> str:
    total_s = int(ms / 1000)
    if total_s < 60:
        return f"{total_s}s"
    minutes = total_s // 60
    seconds = total_s % 60
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h{minutes:02d}m"


def format_reset(resets_at: float) -> str:
    remaining = int(resets_at - time.time())
    if remaining <= 0:
        return "now"
    if remaining < 60:
        return f"{remaining}s"
    minutes = remaining // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours}h{minutes:02d}m"


def format_rate_segment(label: str, pct, resets_at) -> str:
    if pct is not None:
        c = colorize_pct(pct)
        s = dim(f"{label} ") + progress_bar(pct, 6) + " " + fg(c, f"{pct:.0f}%")
        if resets_at is not None:
            s += dim(f"({format_reset(resets_at)})")
        return s
    return dim(f"{label} ") + empty_bar(6) + " " + dim("--%")


def shorten_path(path: str) -> str:
    if path.startswith(_HOME):
        return "~" + path[len(_HOME):]
    return path


def get_git_info(cwd: str) -> str:
    if not cwd or not os.path.isdir(cwd):
        return ""

    # Single git call for branch, upstream, ahead/behind, and file status
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain=v2", "--branch", "-unormal"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode != 0:
            return ""
    except Exception:
        return ""

    branch = ""
    ahead = 0
    behind = 0
    staged = 0
    dirty = 0
    untracked = 0

    for line in r.stdout.splitlines():
        if line.startswith("# branch.head "):
            branch = line[14:]
        elif line.startswith("# branch.ab "):
            parts = line[12:].split()
            if len(parts) >= 2:
                ahead = int(parts[0][1:])
                behind = int(parts[1][1:])
        elif line[0] in "12u":
            xy = line[2:4]
            if xy[0] in "MADRC":
                staged += 1
            if xy[1] in "MD":
                dirty += 1
        elif line[0] == "?":
            untracked += 1

    if branch == "(detached)":
        try:
            h = subprocess.run(
                ["git", "-C", cwd, "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=2,
            )
            branch = h.stdout.strip()[:7] if h.returncode == 0 else ""
        except Exception:
            branch = ""

    if not branch:
        return ""

    result = [fg(CYAN, "\ue0a0 " + branch)]

    flags = ""
    if dirty:
        flags += fg(YELLOW, f" *{dirty}")
    if staged:
        flags += fg(GREEN, f" +{staged}")
    if untracked:
        flags += fg(RED, f" ?{untracked}")
    result.append(flags)

    tokens = []
    if ahead > 0:
        tokens.append(fg(GREEN, f"↑{ahead}"))
    if behind > 0:
        tokens.append(fg(RED, f"↓{behind}"))
    if tokens:
        result.append(" " + " ".join(tokens))

    return "".join(result)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    model_name = data.get("model", {}).get("display_name", "")
    cwd = data.get("workspace", {}).get("current_dir", "")
    ctx_pct = data.get("context_window", {}).get("used_percentage", 0)
    cost_data = data.get("cost", {})
    total_cost = cost_data.get("total_cost_usd", 0)
    duration_ms = cost_data.get("total_duration_ms", 0)
    rate = data.get("rate_limits", {})
    r5h = rate.get("five_hour", {}).get("used_percentage", None)
    r5h_reset = rate.get("five_hour", {}).get("resets_at", None)
    r7d = rate.get("seven_day", {}).get("used_percentage", None)
    r7d_reset = rate.get("seven_day", {}).get("resets_at", None)
    vim_mode = data.get("vim", {}).get("mode", "")
    wt_name = data.get("worktree", {}).get("name", "")

    sep = dim(" │ ")

    # Line 1
    line1_parts = []
    if model_name:
        line1_parts.append(bold_fg(MAGENTA, f" {model_name}"))
    if cwd:
        line1_parts.append(fg(WHITE, shorten_path(cwd)))
    git_info = get_git_info(cwd)
    if git_info:
        line1_parts.append(git_info)
    if wt_name:
        line1_parts.append(fg(YELLOW, f"⊞ {wt_name}"))
    if vim_mode:
        c = _MODE_COLORS.get(vim_mode.upper(), WHITE)
        line1_parts.append(bold_fg(c, f"[{vim_mode.upper()}]"))

    # Line 2
    line2_parts = []
    bar = progress_bar(ctx_pct)
    ctx_color = colorize_pct(ctx_pct)
    line2_parts.append(dim("ctx ") + bar + " " + fg(ctx_color, f"{ctx_pct:.0f}%"))
    line2_parts.append(format_rate_segment("5h", r5h, r5h_reset))
    line2_parts.append(format_rate_segment("7d", r7d, r7d_reset))

    if total_cost > 0:
        line2_parts.append(fg(WHITE, f"${total_cost:.2f}"))
    else:
        line2_parts.append(dim("$--.--"))

    if duration_ms > 0:
        line2_parts.append(dim(format_duration(duration_ms)))
    else:
        line2_parts.append(dim("--:--"))

    lines = [l for l in [sep.join(line1_parts), sep.join(line2_parts)] if l]
    if lines:
        print("\n".join(lines))


if __name__ == "__main__":
    main()

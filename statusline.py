#!/usr/bin/env python3
"""Claude Code status line: rich two-line display."""

import json
import os
import subprocess
import sys
import time


# ANSI color helpers
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


# Colors
MAGENTA = 205
CYAN = 81
GREEN = 82
YELLOW = 220
RED = 196
GRAY = 243
WHITE = 255


def colorize_pct(pct: float) -> int:
    """Return color based on percentage threshold."""
    if pct < 50:
        return GREEN
    elif pct < 80:
        return YELLOW
    return RED


def progress_bar(pct: float, width: int = 10) -> str:
    """Draw a progress bar with ▓░ characters."""
    filled = int(pct / 100 * width)
    filled = max(0, min(width, filled))
    color = colorize_pct(pct)
    bar = fg(color, "▓" * filled) + dim("░" * (width - filled))
    return bar


def format_duration(ms: float) -> str:
    """Format milliseconds as Xm Ys or Xh Ym."""
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
    """Format seconds until reset as compact string."""
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


def shorten_path(path: str) -> str:
    """Replace home directory with ~."""
    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    return path


def get_git_info(cwd: str) -> str:
    """Get git branch, dirty/staged status, and ahead/behind."""
    if not cwd or not os.path.isdir(cwd):
        return ""

    def git(*args):
        try:
            r = subprocess.run(
                ["git", "-C", cwd] + list(args),
                capture_output=True, text=True, timeout=2,
            )
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    branch = git("symbolic-ref", "--short", "HEAD")
    if not branch:
        # detached HEAD
        short = git("rev-parse", "--short", "HEAD")
        branch = short[:7] if short else ""
    if not branch:
        return ""

    parts = [fg(CYAN, "\ue0a0 " + branch)]

    # dirty / staged counts
    status = git("status", "--porcelain", "-uno")
    staged = sum(1 for l in status.splitlines() if l and l[0] in "MADRC") if status else 0
    dirty = sum(1 for l in status.splitlines() if l and l[1] in "MD") if status else 0
    # untracked
    untracked = git("status", "--porcelain", "-unormal")
    ut_count = len(untracked.splitlines()) if untracked else 0

    flags = ""
    if dirty:
        flags += fg(YELLOW, f" *{dirty}")
    if staged:
        flags += fg(GREEN, f" +{staged}")
    if ut_count:
        flags += fg(RED, f" ?{ut_count}")
    parts.append(flags)

    # ahead/behind
    upstream = git("rev-parse", "--abbrev-ref", "@{upstream}")
    if upstream:
        ab = git("rev-list", "--left-right", "--count", f"{upstream}...HEAD")
        if ab:
            behind, ahead = ab.split()
            tokens = []
            if int(ahead) > 0:
                tokens.append(fg(GREEN, f"↑{ahead}"))
            if int(behind) > 0:
                tokens.append(fg(RED, f"↓{behind}"))
            if tokens:
                parts.append(" " + " ".join(tokens))

    return "".join(parts)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    # Extract fields safely
    model = data.get("model", {})
    model_name = model.get("display_name", "")
    workspace = data.get("workspace", {})
    cwd = workspace.get("current_dir", "")
    ctx = data.get("context_window", {})
    ctx_pct = ctx.get("used_percentage", 0)
    cost_data = data.get("cost", {})
    total_cost = cost_data.get("total_cost_usd", 0)
    duration_ms = cost_data.get("total_duration_ms", 0)
    rate = data.get("rate_limits", {})
    r5h = rate.get("five_hour", {}).get("used_percentage", None)
    r5h_reset = rate.get("five_hour", {}).get("resets_at", None)
    r7d = rate.get("seven_day", {}).get("used_percentage", None)
    r7d_reset = rate.get("seven_day", {}).get("resets_at", None)
    vim = data.get("vim", {})
    vim_mode = vim.get("mode", "") if vim else ""
    worktree = data.get("worktree", {})
    wt_name = worktree.get("name", "") if worktree else ""

    sep = dim(" │ ")

    # === Line 1: Model + Dir + Git ===
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
        mode_colors = {"NORMAL": CYAN, "INSERT": GREEN, "VISUAL": MAGENTA}
        c = mode_colors.get(vim_mode.upper(), WHITE)
        line1_parts.append(bold_fg(c, f"[{vim_mode.upper()}]"))

    line1 = sep.join(line1_parts)

    # === Line 2: Context + Rate + Cost + Duration ===
    line2_parts = []

    # Context usage with progress bar
    bar = progress_bar(ctx_pct)
    ctx_color = colorize_pct(ctx_pct)
    line2_parts.append(
        dim("ctx ") + bar + " " + fg(ctx_color, f"{ctx_pct:.0f}%")
    )

    # Rate limits with reset countdown (grayed out when unavailable)
    if r5h is not None:
        c5 = colorize_pct(r5h)
        r5h_str = fg(c5, f"5h:{r5h:.0f}%")
        if r5h_reset is not None:
            r5h_str += dim(f"({format_reset(r5h_reset)})")
        line2_parts.append(r5h_str)
    else:
        line2_parts.append(dim("5h:--"))
    if r7d is not None:
        c7 = colorize_pct(r7d)
        r7d_str = fg(c7, f"7d:{r7d:.0f}%")
        if r7d_reset is not None:
            r7d_str += dim(f"({format_reset(r7d_reset)})")
        line2_parts.append(r7d_str)
    else:
        line2_parts.append(dim("7d:--"))

    # Cost (grayed out when zero/unavailable)
    if total_cost > 0:
        line2_parts.append(fg(WHITE, f"${total_cost:.2f}"))
    else:
        line2_parts.append(dim("$--.--"))

    # Duration (grayed out when zero/unavailable)
    if duration_ms > 0:
        line2_parts.append(dim(format_duration(duration_ms)))
    else:
        line2_parts.append(dim("--:--"))

    line2 = sep.join(line2_parts)

    lines = [l for l in [line1, line2] if l]
    if lines:
        print("\n".join(lines))


if __name__ == "__main__":
    main()

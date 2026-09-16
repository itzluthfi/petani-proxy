"""
core/tui.py - Modern, High-Craft Terminal User Interface for PetaniProxy.
Design Engineering craft: Restraint, typography hierarchy, zero emoji-clutter,
clean Unicode box-drawing, and arrow-key/single-press navigation.
"""

from __future__ import annotations
import os
import sys
import re
import shutil
from typing import List, Dict, Any, Optional, Tuple

# Force UTF-8 on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    class DummyColor:
        def __getattr__(self, name):
            return ""
    Fore = Style = DummyColor()

# Key code constants
KEY_UP = "up"
KEY_DOWN = "down"
KEY_LEFT = "left"
KEY_RIGHT = "right"
KEY_ENTER = "enter"
KEY_ESC = "esc"
KEY_SPACE = "space"
KEY_BACKSPACE = "backspace"

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

def visible_len(text: str) -> int:
    """Calculate visible width of text, ignoring ANSI color escape codes."""
    return len(_ANSI_RE.sub('', text))

def pad_to(text: str, target_width: int) -> str:
    """Pad text to target visible width."""
    vlen = visible_len(text)
    if vlen < target_width:
        return text + (" " * (target_width - vlen))
    return text

def get_terminal_width(default: int = 78) -> int:
    try:
        cols = shutil.get_terminal_size((default, 24)).columns
        return max(72, min(cols, 96))
    except Exception:
        return default

def clear_screen():
    if sys.platform == "win32":
        os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

def read_key() -> str:
    """
    Read a single keypress cross-platform.
    Returns: KEY_UP, KEY_DOWN, KEY_ENTER, KEY_ESC, KEY_SPACE, or single character.
    """
    if sys.platform == "win32":
        import msvcrt
        while True:
            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                ch2 = msvcrt.getch()
                if ch2 == b"H":
                    return KEY_UP
                elif ch2 == b"P":
                    return KEY_DOWN
                elif ch2 == b"K":
                    return KEY_LEFT
                elif ch2 == b"M":
                    return KEY_RIGHT
            elif ch == b"\r":
                return KEY_ENTER
            elif ch == b"\x1b":
                return KEY_ESC
            elif ch == b" ":
                return KEY_SPACE
            elif ch == b"\x08":
                return KEY_BACKSPACE
            elif ch == b"\x03":  # Ctrl+C
                raise KeyboardInterrupt
            else:
                try:
                    return ch.decode("utf-8", errors="ignore").lower()
                except Exception:
                    return ""
    else:
        import tty
        import termios
        import select

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    ch2 = sys.stdin.read(1)
                    if ch2 == "[":
                        ch3 = sys.stdin.read(1)
                        if ch3 == "A":
                            return KEY_UP
                        elif ch3 == "B":
                            return KEY_DOWN
                        elif ch3 == "C":
                            return KEY_RIGHT
                        elif ch3 == "D":
                            return KEY_LEFT
                return KEY_ESC
            elif ch in ("\r", "\n"):
                return KEY_ENTER
            elif ch == " ":
                return KEY_SPACE
            elif ch in ("\x7f", "\x08"):
                return KEY_BACKSPACE
            elif ch == "\x03":
                raise KeyboardInterrupt
            return ch.lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def render_badge(status: str, text: str) -> str:
    """Format a clean status badge with minimal glyph."""
    s = status.upper()
    if any(k in s for k in ("OK", "ACTIVE", "READY", "ONLINE", "SIAP", "GACOR", "ULTRA")):
        return f"{Fore.GREEN}● {text}{Style.RESET_ALL}"
    elif any(k in s for k in ("WARN", "PENDING", "UPDATE", "EXP")):
        return f"{Fore.YELLOW}▲ {text}{Style.RESET_ALL}"
    elif any(k in s for k in ("ERR", "OFF", "OFFLINE", "NONE", "FAIL", "BELUM")):
        return f"{Fore.RED}○ {text}{Style.RESET_ALL}"
    else:
        return f"{Fore.LIGHTBLACK_EX}○ {text}{Style.RESET_ALL}"

def build_header(title: str, subtitle: str, version: str = "", author: str = "@itzluthfi", width: int = 78) -> str:
    inner_w = width - 2
    ver_tag = f"v{version}" if version else ""
    header_label = f"PETANI PROXY {ver_tag}".strip()
    
    top_line = f"╭─ {Fore.WHITE}{Style.BRIGHT}{header_label}{Style.RESET_ALL}{Fore.CYAN} "
    top_rem = inner_w - visible_len(top_line) - 1
    border_top = f"{Fore.CYAN}{top_line}{'─' * max(2, top_rem)}╮{Style.RESET_ALL}"
    
    sub_text = f"  {subtitle}"
    sub_line = f"{Fore.CYAN}│{Fore.LIGHTBLACK_EX}{pad_to(sub_text, inner_w)}{Fore.CYAN}│{Style.RESET_ALL}"
    border_bot = f"{Fore.CYAN}╰{'─' * inner_w}╯{Style.RESET_ALL}"
    return f"{border_top}\n{sub_line}\n{border_bot}"

def build_metrics_card(title: str, metrics: List[Tuple[str, str, str, str]], width: int = 78) -> str:
    """
    Builds a 2-column metrics card with guaranteed border alignment.
    metrics: list of (col1_label, col1_val, col2_label, col2_val)
    """
    inner_w = width - 2
    col_w = inner_w // 2
    
    top_line = f"╭─ {Fore.WHITE}{Style.BRIGHT}{title}{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} "
    top_rem = inner_w - visible_len(top_line) - 1
    border_top = f"{Fore.LIGHTBLACK_EX}{top_line}{'─' * max(2, top_rem)}╮{Style.RESET_ALL}"
    
    lines = [border_top]
    for c1_lbl, c1_val, c2_lbl, c2_val in metrics:
        col1_content = f"  {Fore.LIGHTBLACK_EX}{c1_lbl:<15}{Style.RESET_ALL}{c1_val}"
        col2_content = f" {Fore.LIGHTBLACK_EX}{c2_lbl:<14}{Style.RESET_ALL}{c2_val}" if c2_lbl else ""
        
        c1_str = pad_to(col1_content, col_w)
        c2_str = pad_to(col2_content, inner_w - col_w)
        
        row_str = f"{Fore.LIGHTBLACK_EX}│{Style.RESET_ALL}{c1_str}{c2_str}{Fore.LIGHTBLACK_EX}│{Style.RESET_ALL}"
        lines.append(row_str)
        
    border_bot = f"{Fore.LIGHTBLACK_EX}╰{'─' * inner_w}╯{Style.RESET_ALL}"
    lines.append(border_bot)
    return "\n".join(lines)

def build_info_card(title: str, rows: List[Tuple[str, str]], width: Optional[int] = None, border_color = Fore.CYAN) -> str:
    """
    Builds a clean key-value summary card with rounded borders.
    """
    w = width or get_terminal_width(78)
    inner_w = w - 2
    
    top_line = f"╭─ {Fore.WHITE}{Style.BRIGHT}{title}{Style.RESET_ALL}{border_color} "
    top_rem = inner_w - visible_len(top_line) - 1
    border_top = f"{border_color}{top_line}{'─' * max(2, top_rem)}╮{Style.RESET_ALL}"
    
    lines = [border_top]
    for key, val in rows:
        content = f"  {Fore.LIGHTBLACK_EX}{key:<22}{Style.RESET_ALL}{val}"
        line_str = f"{border_color}│{Style.RESET_ALL}{pad_to(content, inner_w)}{border_color}│{Style.RESET_ALL}"
        lines.append(line_str)
        
    border_bot = f"{border_color}╰{'─' * inner_w}╯{Style.RESET_ALL}"
    lines.append(border_bot)
    return "\n".join(lines)

def build_table(
    headers: List[str],
    rows: List[List[str]],
    aligns: Optional[List[str]] = None,
    width: Optional[int] = None,
    title: Optional[str] = None
) -> str:
    """
    Build a modern, perfectly aligned Unicode table with rounded corners.
    Handles ANSI escape codes for accurate visual length calculations.
    """
    w = width or get_terminal_width(78)
    num_cols = len(headers)
    if num_cols == 0:
        return ""
    
    if aligns is None:
        aligns = ["left"] * num_cols
    
    # Calculate column widths
    col_widths = [visible_len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols:
                col_widths[i] = max(col_widths[i], visible_len(cell))
    
    # Add 2 padding spaces per column (1 left, 1 right)
    inner_widths = [cw + 2 for cw in col_widths]
    total_w = sum(inner_widths) + (num_cols + 1)
    
    # If table exceeds max width, proportionally shrink largest columns
    if total_w > w:
        scale = (w - (num_cols + 1)) / max(1, sum(inner_widths))
        inner_widths = [max(4, int(iw * scale)) for iw in inner_widths]
        col_widths = [iw - 2 for iw in inner_widths]
    
    # Borders
    top_border = f"{Fore.LIGHTBLACK_EX}╭" + "┬".join(["─" * iw for iw in inner_widths]) + f"╮{Style.RESET_ALL}"
    mid_border = f"{Fore.LIGHTBLACK_EX}├" + "┼".join(["─" * iw for iw in inner_widths]) + f"┤{Style.RESET_ALL}"
    bot_border = f"{Fore.LIGHTBLACK_EX}╰" + "┴".join(["─" * iw for iw in inner_widths]) + f"╯{Style.RESET_ALL}"
    
    lines = []
    
    # Optional Table Title Box
    if title:
        title_top = f"{Fore.LIGHTBLACK_EX}╭─ {Fore.WHITE}{Style.BRIGHT}{title}{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} "
        rem = (sum(inner_widths) + num_cols - 1) - visible_len(title_top)
        lines.append(f"{title_top}{'─' * max(2, rem)}╮{Style.RESET_ALL}")
        mid_bridge = f"{Fore.LIGHTBLACK_EX}├" + "┬".join(["─" * iw for iw in inner_widths]) + f"┤{Style.RESET_ALL}"
        lines.append(mid_bridge)
    else:
        lines.append(top_border)
        
    # Header Row
    header_cells = []
    for i, h in enumerate(headers):
        cw = col_widths[i]
        hl = f"{Fore.CYAN}{Style.BRIGHT}{pad_to(h, cw)}{Style.RESET_ALL}"
        header_cells.append(f" {hl} ")
    lines.append(f"{Fore.LIGHTBLACK_EX}│{Style.RESET_ALL}" + f"{Fore.LIGHTBLACK_EX}│{Style.RESET_ALL}".join(header_cells) + f"{Fore.LIGHTBLACK_EX}│{Style.RESET_ALL}")
    lines.append(mid_border)
    
    # Data Rows
    for row in rows:
        row_cells = []
        for i in range(num_cols):
            val = row[i] if i < len(row) else ""
            cw = col_widths[i]
            vlen = visible_len(val)
            align = aligns[i] if i < len(aligns) else "left"
            
            if vlen > cw:
                val = val[:max(1, cw-1)] + "…"
                vlen = visible_len(val)
                
            if align == "right":
                padded = (" " * (cw - vlen)) + val
            elif align == "center":
                left_pad = (cw - vlen) // 2
                right_pad = cw - vlen - left_pad
                padded = (" " * left_pad) + val + (" " * right_pad)
            else:
                padded = val + (" " * (cw - vlen))
                
            row_cells.append(f" {padded} ")
        lines.append(f"{Fore.LIGHTBLACK_EX}│{Style.RESET_ALL}" + f"{Fore.LIGHTBLACK_EX}│{Style.RESET_ALL}".join(row_cells) + f"{Fore.LIGHTBLACK_EX}│{Style.RESET_ALL}")
        
    lines.append(bot_border)
    return "\n".join(lines)

class MenuItem:
    def __init__(self, key: str, label: str, desc: str = "", badge: str = "", is_header: bool = False):
        self.key = key.lower()
        self.label = label
        self.desc = desc
        self.badge = badge
        self.is_header = is_header

class InteractiveMenu:
    """
    Interactive Keyboard-Driven Menu.
    Supports:
    - Arrow Keys Up / Down (or k / j) to navigate smoothly
    - Enter / Space to execute highlighted item
    - Instant hotkeys ('1', 'w', 'c', 'g', 'e', 't', 's', 'q') with 0 typing
    - Esc or 'q' to exit
    """
    def __init__(
        self,
        title: str = "PETANI PROXY",
        subtitle: str = "High-Performance Multi-Protocol Scraper & Local Rotating Gateway",
        version: str = "1.2.0",
        metrics_title: str = "SYSTEM READINESS & METRICS",
        metrics_data: Optional[List[Tuple[str, str, str, str]]] = None,
        update_notice: Optional[str] = None
    ):
        self.title = title
        self.subtitle = subtitle
        self.version = version
        self.metrics_title = metrics_title
        self.metrics_data = metrics_data or []
        self.update_notice = update_notice
        self.items: List[MenuItem] = []
        self.selected_index: int = 0

    def add_section(self, section_name: str):
        self.items.append(MenuItem(key="", label=section_name, is_header=True))

    def add_item(self, key: str, label: str, desc: str = "", badge: str = ""):
        self.items.append(MenuItem(key=key, label=label, desc=desc, badge=badge))

    def _get_selectable_indices(self) -> List[int]:
        return [i for i, it in enumerate(self.items) if not it.is_header]

    def run(self) -> str:
        selectable = self._get_selectable_indices()
        if not selectable:
            return ""
        
        if self.selected_index not in selectable:
            self.selected_index = selectable[0]

    def render(self, width: Optional[int] = None):
        """Render the menu frame to stdout."""
        w = width or get_terminal_width(78)
        print(build_header(self.title, self.subtitle, self.version, width=w))
        print()

        if self.update_notice:
            print(f"  {Fore.YELLOW}▲ {self.update_notice}{Style.RESET_ALL}\n")

        if self.metrics_data:
            print(build_metrics_card(self.metrics_title, self.metrics_data, width=w))
            print()

        for i, item in enumerate(self.items):
            if item.is_header:
                print(f"\n  {Fore.LIGHTBLACK_EX}{Style.BRIGHT}{item.label.upper()}{Style.RESET_ALL}")
                continue

            is_selected = (i == self.selected_index)
            cursor = f"{Fore.CYAN}{Style.BRIGHT}❯{Style.RESET_ALL} " if is_selected else "  "
            key_tag = f"{Fore.CYAN if is_selected else Fore.LIGHTBLACK_EX}[{item.key.upper()}]{Style.RESET_ALL}"
            
            label_color = f"{Fore.WHITE}{Style.BRIGHT}" if is_selected else Fore.WHITE
            label_str = f"{label_color}{item.label:<23}{Style.RESET_ALL}"
            
            badge_str = f" {item.badge}" if item.badge else ""
            desc_str = f"{Fore.LIGHTBLACK_EX}{item.desc}{Style.RESET_ALL}" if item.desc else ""
            
            print(f"{cursor}{key_tag} {label_str}{badge_str}  {desc_str}")

        print()
        print(f"{Fore.LIGHTBLACK_EX}  ↑/↓: Navigate  •  Enter: Select  •  [Key]: Instant Action  •  Esc/q: Exit{Style.RESET_ALL}")

    def run(self) -> str:
        selectable = self._get_selectable_indices()
        if not selectable:
            return ""
        
        if self.selected_index not in selectable:
            self.selected_index = selectable[0]

        width = get_terminal_width(78)

        while True:
            clear_screen()
            self.render(width=width)

            try:
                key = read_key()
            except KeyboardInterrupt:
                return "0"

            if key in (KEY_UP, "k"):
                curr_pos = selectable.index(self.selected_index)
                new_pos = (curr_pos - 1) % len(selectable)
                self.selected_index = selectable[new_pos]
            elif key in (KEY_DOWN, "j"):
                curr_pos = selectable.index(self.selected_index)
                new_pos = (curr_pos + 1) % len(selectable)
                self.selected_index = selectable[new_pos]
            elif key in (KEY_ENTER, KEY_SPACE):
                return self.items[self.selected_index].key
            elif key in (KEY_ESC, "q"):
                return "0"
            elif key:
                for item in self.items:
                    if not item.is_header and item.key == key:
                        return item.key

def quick_confirm(prompt: str, default: bool = True) -> bool:
    """
    Zero-typing confirmation prompt.
    User simply taps 'y' or 'n' or 'Enter' (default).
    """
    hint = "[Y/n]" if default else "[y/N]"
    sys.stdout.write(f"\n  {Fore.YELLOW}❯ {prompt} {Fore.LIGHTBLACK_EX}{hint}: {Style.RESET_ALL}")
    sys.stdout.flush()
    try:
        k = read_key()
        if k in (KEY_ENTER, KEY_SPACE):
            return default
        elif k == "y":
            print(f"{Fore.GREEN}yes{Style.RESET_ALL}")
            return True
        elif k in ("n", KEY_ESC):
            print(f"{Fore.RED}no{Style.RESET_ALL}")
            return False
        return default
    except KeyboardInterrupt:
        print()
        return False

def quick_pause(msg: str = "Tekan tombol apa saja untuk melanjutkan..."):
    """Pauses until any single key is pressed."""
    sys.stdout.write(f"\n  {Fore.LIGHTBLACK_EX}❯ {msg}{Style.RESET_ALL}")
    sys.stdout.flush()
    try:
        read_key()
        print()
    except KeyboardInterrupt:
        print()

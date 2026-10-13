#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = ROOT_DIR / "pyproject.toml"

# Cross-platform single-character / keypress handler
if os.name == "nt":
    import msvcrt

    def get_key():
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            if code == "H":
                return "up"
            if code == "P":
                return "down"
            return "unknown"
        if ch == "\r":
            return "return"
        if ch == "\x08":
            return "backspace"
        if ch == "\x1b":
            return "escape"
        if ch == "\x03":
            return "ctrl-c"
        return ch
else:
    import termios
    import tty

    def get_key():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    return "up"
                if seq == "[B":
                    return "down"
                return "escape"
            if ch in ("\n", "\r"):
                return "return"
            if ch in ("\x7f", "\x08"):
                return "backspace"
            if ch == "\x03":
                return "ctrl-c"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def parse_compound_version(v: str):
    match = re.match(r"^(\d+\.\d+\.\d+)(?:([\-\+])ee\.?(\d+(?:\.\d+)*))?$", v.strip())
    if match:
        base_str, sep_char, ee_str = match.groups()
        base_parts = list(map(int, base_str.split(".")))
        while len(base_parts) < 3:
            base_parts.append(0)
        sep = sep_char or "-"
        if ee_str:
            ee_parts = list(map(int, ee_str.split(".")))
            while len(ee_parts) < 3:
                ee_parts.append(0)
        else:
            ee_parts = [0, 0, 1]
        return base_parts, sep, ee_parts
    else:
        main_ver, *rest = v.split("-", 1)
        raw_parts = re.findall(r"\d+", main_ver)
        base_parts = [int(p) for p in raw_parts[:3]] if raw_parts else [0, 2, 2]
        while len(base_parts) < 3:
            base_parts.append(0)
        return base_parts, "-", [0, 0, 1]


def format_version(base_parts, sep, ee_parts):
    return f"{base_parts[0]}.{base_parts[1]}.{base_parts[2]}{sep}ee.{ee_parts[0]}.{ee_parts[1]}.{ee_parts[2]}"


def get_current_pyproject_version() -> str:
    if not PYPROJECT_PATH.exists():
        print(f"\033[31mError: pyproject.toml not found at {PYPROJECT_PATH}\033[0m")
        sys.exit(1)

    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = re.search(r'^\[project\](?:(?!^\[)[\s\S])*?\bversion\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        print("\033[31mError: Could not locate version field in pyproject.toml [project] section.\033[0m")
        sys.exit(1)

    return match.group(1)


def update_pyproject_file(prev_ver: str, next_ver: str):
    success = False
    try:
        raw = PYPROJECT_PATH.read_text(encoding="utf-8")
        updated = re.sub(
            r'(^\[project\](?:(?!^\[)[\s\S])*?\bversion\s*=\s*")[^"]+(")',
            rf"\g<1>{next_ver}\g<2>",
            raw,
            flags=re.MULTILINE,
        )
        PYPROJECT_PATH.write_text(updated, encoding="utf-8")
        success = True
    except Exception:
        success = False

    clear_screen()
    print("\n")
    if success:
        print(f"\033[32m✔\033[0m pyproject.toml  \033[90m({prev_ver} -> \033[1;32m{next_ver}\033[0;90m)\033[0m")
    else:
        print("\033[31m✖\033[0m pyproject.toml  \033[31m(Update Failed!)\033[0m")
    print("\n")
    sys.exit(0)


def main():
    prev_version = get_current_pyproject_version()
    base_parts, sep, ee_parts = parse_compound_version(prev_version)
    
    curr_base = list(base_parts)
    curr_sep = sep
    curr_ee = list(ee_parts)
    current_preview = format_version(curr_base, curr_sep, curr_ee)

    MENU_ITEMS = [
        # EE Section (Top)
        {"id": "ee_patch", "section": "ee", "label": "ee-patch", "desc": "Increment EE patch (e.g. .0.0.1 -> .0.0.2)"},
        {"id": "ee_minor", "section": "ee", "label": "ee-minor", "desc": "Increment EE minor (e.g. .0.0.1 -> .0.1.0)"},
        {"id": "ee_major", "section": "ee", "label": "ee-major", "desc": "Increment EE major (e.g. .0.0.1 -> .1.0.0)"},
        
        # Base Section (Bottom)
        {"id": "base_patch", "section": "base", "label": "base-patch", "desc": "Increment Base patch (e.g. 0.2.2 -> 0.2.3)"},
        {"id": "base_minor", "section": "base", "label": "base-minor", "desc": "Increment Base minor (e.g. 0.2.2 -> 0.3.0)"},
        {"id": "base_major", "section": "base", "label": "base-major", "desc": "Increment Base major (e.g. 0.2.2 -> 1.0.0)"},
        
        # Utilities
        {"id": "as_is", "section": "util", "label": "as-is", "desc": "Reset preview to original Previous Version"},
        {"id": "custom", "section": "util", "label": "custom", "desc": "Type a custom version manually"},
        
        # Actions
        {"id": "confirm", "section": "action", "label": "[ Confirm & Save ]", "desc": "Write new version to pyproject.toml"},
        {"id": "cancel", "section": "action", "label": "[ Cancel ]", "desc": "Exit without saving changes"},
    ]

    selected_index = 0
    is_custom_mode = False
    custom_input = ""

    def render():
        clear_screen()
        print("\n" + "=" * 60)
        print(f"  \033[1;36mPrevious Version:\033[0m  \033[33m{prev_version}\033[0m")
        print(f"  \033[1;32mCurrent Version: \033[0m  \033[1;42;30m {current_preview} \033[0m \033[90m(Live Preview)\033[0m")
        print("=" * 60 + "\n")

        if is_custom_mode:
            print("\033[90m< [ESC] to cancel <\033[0m\n")
            print(f"Enter custom version: \033[1;32m{custom_input}_\033[0m\n")
            print("\033[90mPress [Enter] to apply to preview.\033[0m")
            return

        last_section = None
        for idx, item in enumerate(MENU_ITEMS):
            if last_section and last_section != item["section"]:
                print("")
            last_section = item["section"]

            is_selected = idx == selected_index
            prefix = "▶ " if is_selected else "  "

            if item["id"] == "confirm":
                line = f"{prefix}\033[1;32m{item['label']:<22}\033[0m \033[90m- {item['desc']}\033[0m"
            elif item["id"] == "cancel":
                line = f"{prefix}\033[1;31m{item['label']:<22}\033[0m \033[90m- {item['desc']}\033[0m"
            elif item["id"] == "custom":
                line = f"{prefix}\033[1;33m{item['label']:<22}\033[0m \033[90m>_ type manual version\033[0m"
            else:
                line = f"{prefix}{item['label']:<16} \033[90m- {item['desc']}\033[0m"

            if is_selected and item["id"] not in ("confirm", "cancel", "custom"):
                print(f"\033[1;36m{line}\033[0m")
            else:
                print(line)

        print("\n\033[90m[↑/↓] Navigate  |  [Enter] Select/Update Preview  |  [Ctrl+C] Exit\033[0m")

    while True:
        render()
        key = get_key()

        if key == "ctrl-c":
            clear_screen()
            sys.exit(0)

        if is_custom_mode:
            if key == "escape":
                is_custom_mode = False
                custom_input = ""
                continue

            if key == "return":
                if len(custom_input.strip()) > 0:
                    current_preview = custom_input.strip()
                    parsed_b, parsed_s, parsed_e = parse_compound_version(current_preview)
                    curr_base = parsed_b
                    curr_sep = parsed_s
                    curr_ee = parsed_e
                    is_custom_mode = False
                    custom_input = ""
                continue

            if key == "backspace":
                custom_input = custom_input[:-1]
            elif len(key) == 1 and key.isprintable():
                custom_input += key
            continue

        if key == "up":
            selected_index = (selected_index - 1 + len(MENU_ITEMS)) % len(MENU_ITEMS)
        elif key == "down":
            selected_index = (selected_index + 1) % len(MENU_ITEMS)
        elif key == "return":
            item = MENU_ITEMS[selected_index]
            action_id = item["id"]

            if action_id == "confirm":
                update_pyproject_file(prev_version, current_preview)
            elif action_id == "cancel":
                clear_screen()
                print("\n\033[33mVersion update cancelled.\033[0m\n")
                sys.exit(0)
            elif action_id == "custom":
                is_custom_mode = True
                custom_input = current_preview
            elif action_id == "as_is":
                curr_base = list(base_parts)
                curr_sep = sep
                curr_ee = list(ee_parts)
                current_preview = format_version(curr_base, curr_sep, curr_ee)
            elif action_id == "ee_patch":
                curr_ee[2] += 1
                current_preview = format_version(curr_base, curr_sep, curr_ee)
            elif action_id == "ee_minor":
                curr_ee[1] += 1
                curr_ee[2] = 0
                current_preview = format_version(curr_base, curr_sep, curr_ee)
            elif action_id == "ee_major":
                curr_ee[0] += 1
                curr_ee[1] = 0
                curr_ee[2] = 0
                current_preview = format_version(curr_base, curr_sep, curr_ee)
            elif action_id == "base_patch":
                curr_base[2] += 1
                curr_ee = [0, 0, 1]
                current_preview = format_version(curr_base, curr_sep, curr_ee)
            elif action_id == "base_minor":
                curr_base[1] += 1
                curr_base[2] = 0
                curr_ee = [0, 0, 1]
                current_preview = format_version(curr_base, curr_sep, curr_ee)
            elif action_id == "base_major":
                curr_base[0] += 1
                curr_base[1] = 0
                curr_base[2] = 0
                curr_ee = [0, 0, 1]
                current_preview = format_version(curr_base, curr_sep, curr_ee)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

# Ensure UTF-8 output encoding across all platforms (specifically Windows consoles)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = ROOT_DIR / "pyproject.toml"
PACKAGE_JSON_PATH = ROOT_DIR / "studio" / "ui" / "package.json"

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


def parse_studio_version(v: str):
    """
    Parse versions in the new scheme:
      X.Y.Z-alpha.x.y
      X.Y.Z-beta.x.y
      X.Y.Z-rc.x.y
      X.Y.Z (release)

    Returns:
      (base_parts: [int, int, int], phase: str | None, x: int, y: int)
    """
    v_clean = v.strip().lstrip("v")
    # Matches e.g. "1.0.0-alpha.1.0" or "1.0.0-beta.2" or "1.0.0"
    match = re.match(
        r"^(\d+\.\d+\.\d+)(?:-([a-zA-Z]+)(?:\.(\d+))?(?:\.(\d+))?)?$",
        v_clean,
    )
    if match:
        base_str, phase, x_str, y_str = match.groups()
        base_parts = [int(p) for p in base_str.split(".")]
        while len(base_parts) < 3:
            base_parts.append(0)
        
        phase_val = phase.lower() if phase else None
        x_val = int(x_str) if x_str is not None else 1
        y_val = int(y_str) if y_str is not None else 0
        return base_parts, phase_val, x_val, y_val

    # Legacy fallback: e.g. "0.3.2-ee.0.3.0" -> initial studio baseline is 1.0.0-alpha.1.0
    return [1, 0, 0], "alpha", 1, 0


def format_studio_version(base_parts, phase, x, y) -> str:
    base_str = f"{base_parts[0]}.{base_parts[1]}.{base_parts[2]}"
    if phase:
        return f"{base_str}-{phase}.{x}.{y}"
    return base_str


def get_current_pyproject_version() -> str:
    if not PYPROJECT_PATH.exists():
        print(f"\033[31mError: pyproject.toml not found at {PYPROJECT_PATH}\033[0m")
        sys.exit(1)

    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = re.search(
        r'^\[project\](?:(?!^\[)[\s\S])*?\bversion\s*=\s*"([^"]+)"',
        content,
        re.MULTILINE,
    )
    if not match:
        print("\033[31mError: Could not locate version field in pyproject.toml [project] section.\033[0m")
        sys.exit(1)

    return match.group(1).strip()


def update_version_in_files(prev_ver: str, next_ver: str):
    results = []

    # 1. Update pyproject.toml
    try:
        raw_pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")
        updated_pyproject = re.sub(
            r'(^\[project\](?:(?!^\[)[\s\S])*?\bversion\s*=\s*")[^"]+(")',
            rf"\g<1>{next_ver}\g<2>",
            raw_pyproject,
            flags=re.MULTILINE,
        )
        PYPROJECT_PATH.write_text(updated_pyproject, encoding="utf-8")
        results.append(("pyproject.toml", True, prev_ver, next_ver))
    except Exception as e:
        results.append(("pyproject.toml", False, prev_ver, str(e)))

    # 2. Update studio/ui/package.json
    if PACKAGE_JSON_PATH.exists():
        try:
            raw_pkg = PACKAGE_JSON_PATH.read_text(encoding="utf-8")
            old_pkg_match = re.search(r'"version"\s*:\s*"([^"]+)"', raw_pkg)
            old_pkg_ver = old_pkg_match.group(1) if old_pkg_match else prev_ver

            updated_pkg = re.sub(
                r'("version"\s*:\s*")[^"]+(")',
                rf'\g<1>{next_ver}\g<2>',
                raw_pkg,
            )
            PACKAGE_JSON_PATH.write_text(updated_pkg, encoding="utf-8")
            results.append(("studio/ui/package.json", True, old_pkg_ver, next_ver))
        except Exception as e:
            results.append(("studio/ui/package.json", False, prev_ver, str(e)))

    clear_screen()
    print("\n" + "=" * 62)
    print("  \033[1;32m✔ Version Bump Successfully Applied!\033[0m")
    print("=" * 62 + "\n")
    for file_name, success, old_v, new_v in results:
        if success:
            print(f"  \033[32m✔\033[0m {file_name:<26} \033[90m({old_v} -> \033[1;32m{new_v}\033[0;90m)\033[0m")
        else:
            print(f"  \033[31m✖\033[0m {file_name:<26} \033[31m(Update Failed: {new_v})\033[0m")
    print("\n")
    sys.exit(0)


def main():
    prev_version = get_current_pyproject_version()
    base_parts, phase, x_val, y_val = parse_studio_version(prev_version)

    curr_base = list(base_parts)
    curr_phase = phase
    curr_x = x_val
    curr_y = y_val

    # If previous version was legacy (contained 'ee'), initialize preview directly to 1.0.0-alpha.1.0
    if "ee" in prev_version:
        curr_base = [1, 0, 0]
        curr_phase = "alpha"
        curr_x = 1
        curr_y = 0

    current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)

    MENU_ITEMS = [
        # Pre-Release Iterations
        {
            "id": "patch",
            "section": "pre_release",
            "label": "patch (+y)",
            "desc": "Increment patch/bugfix counter (e.g. .1.0 -> .1.1)",
        },
        {
            "id": "feature",
            "section": "pre_release",
            "label": "feature (+x)",
            "desc": "Increment feature counter and reset patch (e.g. .1.2 -> .2.0)",
        },

        # Phase Transitions
        {
            "id": "phase_alpha",
            "section": "phase",
            "label": "to-alpha",
            "desc": "Switch phase to Alpha (resets counter to .1.0)",
        },
        {
            "id": "phase_beta",
            "section": "phase",
            "label": "to-beta",
            "desc": "Switch phase to Beta (resets counter to .1.0)",
        },
        {
            "id": "phase_rc",
            "section": "phase",
            "label": "to-rc",
            "desc": "Switch phase to Release Candidate (resets counter to .1.0)",
        },
        {
            "id": "phase_release",
            "section": "phase",
            "label": "to-release",
            "desc": "Promote to official Release (drops pre-release suffix, e.g. 1.0.0)",
        },

        # Base SemVer (Target)
        {
            "id": "base_patch",
            "section": "base",
            "label": "base-patch",
            "desc": "Increment base patch (e.g. 1.0.0 -> 1.0.1)",
        },
        {
            "id": "base_minor",
            "section": "base",
            "label": "base-minor",
            "desc": "Increment base minor (e.g. 1.0.0 -> 1.1.0)",
        },
        {
            "id": "base_major",
            "section": "base",
            "label": "base-major",
            "desc": "Increment base major (e.g. 1.0.0 -> 2.0.0)",
        },

        # Utilities
        {
            "id": "as_is",
            "section": "util",
            "label": "as-is",
            "desc": "Reset preview to original Previous Version",
        },
        {
            "id": "custom",
            "section": "util",
            "label": "custom",
            "desc": "Type manual custom version string",
        },

        # Actions
        {
            "id": "confirm",
            "section": "action",
            "label": "[ Confirm & Save ]",
            "desc": "Write new version to pyproject.toml & package.json",
        },
        {
            "id": "cancel",
            "section": "action",
            "label": "[ Cancel ]",
            "desc": "Exit without saving changes",
        },
    ]

    selected_index = 0
    is_custom_mode = False
    custom_input = ""

    def render():
        clear_screen()
        phase_badge = f"\033[1;35m[{curr_phase.upper() if curr_phase else 'RELEASE'}]\033[0m"
        print("\n" + "=" * 62)
        print(f"  \033[1;36mPrevious Version:\033[0m  \033[33m{prev_version}\033[0m")
        print(f"  \033[1;32mCurrent Version: \033[0m  \033[1;42;30m {current_preview} \033[0m  {phase_badge} \033[90m(Live Preview)\033[0m")
        print("=" * 62 + "\n")

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
                line = f"{prefix}\033[1;32m{item['label']:<20}\033[0m \033[90m- {item['desc']}\033[0m"
            elif item["id"] == "cancel":
                line = f"{prefix}\033[1;31m{item['label']:<20}\033[0m \033[90m- {item['desc']}\033[0m"
            elif item["id"] == "custom":
                line = f"{prefix}\033[1;33m{item['label']:<20}\033[0m \033[90m>_ type manual version\033[0m"
            else:
                line = f"{prefix}{item['label']:<18} \033[90m- {item['desc']}\033[0m"

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
                    parsed_b, parsed_p, parsed_x, parsed_y = parse_studio_version(current_preview)
                    curr_base = parsed_b
                    curr_phase = parsed_p
                    curr_x = parsed_x
                    curr_y = parsed_y
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
                update_version_in_files(prev_version, current_preview)
            elif action_id == "cancel":
                clear_screen()
                print("\n\033[33mVersion update cancelled.\033[0m\n")
                sys.exit(0)
            elif action_id == "custom":
                is_custom_mode = True
                custom_input = current_preview
            elif action_id == "as_is":
                curr_base = list(base_parts)
                curr_phase = phase
                curr_x = x_val
                curr_y = y_val
                current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)
            elif action_id == "patch":
                if curr_phase:
                    curr_y += 1
                else:
                    curr_base[2] += 1
                current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)
            elif action_id == "feature":
                if curr_phase:
                    curr_x += 1
                    curr_y = 0
                else:
                    curr_base[1] += 1
                    curr_base[2] = 0
                current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)
            elif action_id == "phase_alpha":
                curr_phase = "alpha"
                curr_x = 1
                curr_y = 0
                current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)
            elif action_id == "phase_beta":
                curr_phase = "beta"
                curr_x = 1
                curr_y = 0
                current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)
            elif action_id == "phase_rc":
                curr_phase = "rc"
                curr_x = 1
                curr_y = 0
                current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)
            elif action_id == "phase_release":
                curr_phase = None
                curr_x = 0
                curr_y = 0
                current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)
            elif action_id == "base_patch":
                curr_base[2] += 1
                current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)
            elif action_id == "base_minor":
                curr_base[1] += 1
                curr_base[2] = 0
                current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)
            elif action_id == "base_major":
                curr_base[0] += 1
                curr_base[1] = 0
                curr_base[2] = 0
                current_preview = format_studio_version(curr_base, curr_phase, curr_x, curr_y)


if __name__ == "__main__":
    main()

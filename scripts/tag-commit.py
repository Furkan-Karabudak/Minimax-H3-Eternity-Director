#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path

# Ensure UTF-8 output encoding across all platforms (specifically Windows consoles / Git hooks)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = ROOT_DIR / "pyproject.toml"


def get_pyproject_version() -> str:
    if not PYPROJECT_PATH.exists():
        print(f"\n\033[31m✖ pyproject.toml not found at {PYPROJECT_PATH}\033[0m\n")
        sys.exit(0)

    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = re.search(r'^\[project\](?:(?!^\[)[\s\S])*?\bversion\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        print("\n\033[31m✖ Could not locate version field in pyproject.toml [project] section.\033[0m\n")
        sys.exit(1)

    ver = match.group(1).strip()
    return ver if ver.startswith("v") else f"v{ver}"


def main():
    try:
        # 1. Read version from pyproject.toml
        version = get_pyproject_version()

        # 2. Check if the tag already exists
        result = subprocess.run(
            ["git", "tag"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True
        )
        existing_tags = [t.strip() for t in result.stdout.splitlines() if t.strip()]

        if version in existing_tags:
            print(f"\n\033[33mℹ Tag {version} already exists, skipping.\033[0m\n")
            sys.exit(0)

        # 3. Create annotated tag on the latest commit
        subprocess.run(
            ["git", "tag", "-a", version, "-m", f"release {version}"],
            check=True
        )
        print(f"\n\033[32m✔ Tag {version} successfully attached to the commit.\033[0m")

        # 4. Push the newly created tag to remote origin
        subprocess.run(
            ["git", "push", "origin", version],
            check=True
        )
        print(f"\033[32m✔ Tag {version} successfully pushed to GitHub.\033[0m\n")

    except subprocess.CalledProcessError as err:
        print(f"\n\033[31m✖ Failed to create or push tag:\033[0m {err}")
        sys.exit(1)
    except Exception as err:
        print(f"\n\033[31m✖ Error:\033[0m {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()


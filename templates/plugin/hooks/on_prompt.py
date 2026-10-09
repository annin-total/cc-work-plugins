"""UserPromptSubmit hook の例。stdin の JSON を UTF-8 で読み、何もせず終わる。"""

import json
import sys


def main() -> int:
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    _ = payload.get("prompt", "")
    return 0


if __name__ == "__main__":
    sys.exit(main())

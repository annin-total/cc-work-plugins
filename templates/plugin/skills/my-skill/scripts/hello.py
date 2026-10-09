"""同梱スクリプトの例。引数を UTF-8 で出力する。"""

import sys


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("hello:", " ".join(sys.argv[1:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

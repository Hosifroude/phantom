from __future__ import annotations

import sys

from dashboard_writer import write_dashboard


def main() -> int:
    write_dashboard()
    return 0


if __name__ == "__main__":
    sys.exit(main())

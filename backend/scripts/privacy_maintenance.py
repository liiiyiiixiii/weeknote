"""审计并按需清理旧版本误存入 raw_input 的附件提取正文。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from app import storage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际删除旧 raw_input 中的附件正文；默认只报告数量",
    )
    args = parser.parse_args()

    if os.getenv("APP_ENV", "development").lower() == "production" and not storage.DB_PATH.exists():
        print(f"生产数据库不存在：{storage.DB_PATH}，未执行。")
        return 1
    storage.init_db()
    count = storage.legacy_attachment_context_count()
    print(f"数据库：{storage.DB_PATH}")
    print(f"检测到 {count} 条可能含旧附件正文的周报记录。")
    if not args.apply:
        print("当前为只读审计；确认备份后可加 --apply 执行清理。")
        return 0
    removed = storage.scrub_legacy_attachment_contexts()
    print(f"已清理 {removed} 条记录。此操作会保留附件标记前的用户原始文字。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

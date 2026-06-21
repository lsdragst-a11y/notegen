"""手动/任务计划程序入口：跑一轮磁盘治理并打印摘要。
Run: .venv/Scripts/python.exe scripts/run_maintenance.py [--dry-run]
（server.py 启动后自带每日一轮，本脚本用于手动触发或排查。）"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import maintenance  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="只列出会删什么，不真删")
    args = ap.parse_args()
    summary = maintenance.run_once(dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    d = summary["disk"]
    verb = "将删除" if args.dry_run else "已删除"
    print(f"\n{verb}过期文件 {len(summary['old_files_removed'])} 个、"
          f"孤儿上传 {len(summary['orphan_uploads_removed'])} 个；"
          f"磁盘剩余 {d['free_gb']}GB（{d['free_ratio']:.0%}）"
          + ("，低于水位线！" if d["low"] else ""))


if __name__ == "__main__":
    main()

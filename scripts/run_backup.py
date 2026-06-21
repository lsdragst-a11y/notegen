"""手动备份入口：打一个 zip + 滚动清理。
Run: .venv/Scripts/python.exe scripts/run_backup.py [--include-videos] [--keep N] [--dest DIR]
（server.py 启动后自带每日一轮；目的地建议用 NOTEGEN_BACKUP_DIR 指到第二块盘。）"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import backup  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-videos", action="store_true",
                    help="把视频也打进包（默认排除，体积考虑）")
    ap.add_argument("--keep", type=int, default=None, help="滚动保留份数（默认 7）")
    ap.add_argument("--dest", default=None, help="备份目录（默认 backups/）")
    args = ap.parse_args()
    s = backup.run_backup(dest_dir=args.dest, include_videos=args.include_videos or None,
                          keep=args.keep)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    print(f"\n备份完成 → {s['path']}（{s['size_mb']}MB，{s['files']} 个文件"
          f"{'，跳过视频 ' + str(s['skipped_videos']) + ' 个' if s['skipped_videos'] else ''}）"
          f"{'；清理旧备份 ' + str(len(s['pruned'])) + ' 份' if s['pruned'] else ''}")


if __name__ == "__main__":
    main()

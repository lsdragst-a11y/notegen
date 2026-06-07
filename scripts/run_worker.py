"""起单个 RQ SimpleWorker 消费 default 队列。
- SimpleWorker：同进程消费、不 os.fork（Windows 无 fork）。
- 单 worker = 并发=1：天然串行，契合「大模型串行加载」铁律。
- pipeline 仍以 subprocess 跑（worker_tasks 内），崩溃不带垮 worker。
- Windows 无 signal.SIGALRM，job_timeout 死刑计时必须用 TimerDeathPenalty
  （线程计时器），否则首个真任务一跑就 AttributeError 崩 worker。
Run: .venv/Scripts/python.exe scripts/run_worker.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rq import SimpleWorker  # noqa: E402
from rq.timeouts import TimerDeathPenalty  # noqa: E402
import jobqueue  # noqa: E402
import db  # noqa: E402


def main():
    db.init_db()  # worker 先于 api 起也能写库
    conn = jobqueue.get_rq()
    queue = jobqueue.get_queue()
    print(f"[worker] SimpleWorker 启动，监听 default 队列 @ {jobqueue.REDIS_URL}")
    w = SimpleWorker([queue], connection=conn)
    w.death_penalty_class = TimerDeathPenalty
    w.work()


if __name__ == "__main__":
    main()

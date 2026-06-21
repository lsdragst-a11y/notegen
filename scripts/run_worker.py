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
import userdata  # noqa: E402
from logging_setup import setup_logging  # noqa: E402

log = setup_logging("worker")


def main():
    db.init_db()  # worker 先于 api 起也能写库
    orphaned = userdata.jobs_repo.reconcile_orphans()
    if orphaned:
        log.warning(f"复位 {orphaned} 个上次残留的 running 任务为 interrupted")
    conn = jobqueue.get_rq()
    # 列表序 = 优先级：QA 插队在排队 pipeline 任务之前（仍与运行中任务串行）
    queues = [jobqueue.get_qa_queue(), jobqueue.get_queue()]
    log.info(f"SimpleWorker 启动，监听 qa + default 队列 @ {jobqueue.REDIS_URL}")
    w = SimpleWorker(queues, connection=conn)
    w.death_penalty_class = TimerDeathPenalty
    w.work()


if __name__ == "__main__":
    main()

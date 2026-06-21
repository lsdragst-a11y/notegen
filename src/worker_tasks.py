"""RQ 任务：run_generate(job_id, source, opts)。
subprocess 跑 pipeline.py（崩溃隔离），解析 stdout 的 [PROGRESS] marker + 既有
[asr]/[pegasus]/[clip] 细行写 Redis 进度。等价于旧 server._run_pipeline_impl，
但状态走 jobqueue（Redis）而非内存。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Optional

from rq import get_current_job

import jobqueue
import service_common as SC
import userdata
from progress import parse_progress_marker, stage_band, interpolate


class PipelineFailed(Exception):
    """pipeline 跑完无产物：标 failed 并抛出，让 RQ 记 failed registry。"""


# ============ 输出文件名后缀（与 _build_cmd 参数和 pipeline._output_stem 对应）============
# 完整 stem 格式：{id}.{OUT_TAG}.neural.texttile[.cc{N}][.mm[.vl]]
#   - .cc{N}：adaptive_chunk_chars ≠ 800 时出现（_run_pipeline_subprocess 按时长自适应）
#   - .mm.vl：--keyframes --vlm-captions（_build_cmd 默认开）
# 换 ASR 模型 / chunker 时只改这里，stem 提取和 fallback 扫描两处共用。
_OUT_TAG = "large-v3"
_OUT_GLOB = f"*.{_OUT_TAG}.neural.texttile*.md"
_OUT_STEM_RE = re.compile(rf"data[\\/]outputs[\\/]([^\\/]+)\.{re.escape(_OUT_TAG)}")
_OUT_SUFFIX_RE = re.compile(
    rf"\.{re.escape(_OUT_TAG)}\.neural\.texttile(\.cc\d+)?(\.mm(\.vl)?)?$")


def _no_retry() -> None:
    """致命错误（无产物/产出复制失败）不重试：把当前 job 的 retries_left 清零，
    让 RQ 直接进 FailedJobRegistry。仅 transient（下载/网络）才走 Retry。
    （符合 spec：pipeline 真错不重试，避免白白再烧 GPU。）"""
    job = get_current_job()
    if job is not None:
        job.retries_left = 0


def _mirror_job(opts: dict, job_id: str, status: str, *, note_id=None, error=None) -> None:
    """有 user_id 才镜像 SQLite jobs 终态（无 uid = 旧/公开路径，不写库）。"""
    if opts.get("user_id"):
        userdata.jobs_repo.update_status(job_id, status, note_id=note_id, error=error)


def _publish(stem: str, opts: dict) -> str:
    """按 user_id 分流：有 uid → 私有发布 + 写 notes 行；否则公开发布。返回 note_id。"""
    uid = opts.get("user_id")
    if uid:
        note_id, storage_path, fields = SC.publish_private(stem, uid)
        userdata.notes_repo.upsert(id=note_id, owner_id=uid, visibility="private",
                                   storage_path=storage_path, **fields)
        return note_id
    return SC.publish_to_web(stem)


def run_generate(job_id: str, source: str, opts: dict) -> Optional[str]:
    started = time.time()
    unload_qa_model()  # QA 模型若常驻必须先让出 VRAM
    jobqueue.set_progress(job_id, stage="running", percent=4, msg="启动 pipeline")
    _mirror_job(opts, job_id, "running")
    try:
        stem, returncode = _run_pipeline_subprocess(job_id, source, opts)
    except Exception as e:
        jobqueue.set_progress(job_id, stage="failed", percent=0, msg=f"运行错误：{e}")
        _mirror_job(opts, job_id, "failed", error=f"运行错误：{e}")
        raise

    if not stem:
        stem = _scan_output_fallback(job_id, started)
        if stem:
            jobqueue.set_progress(job_id, stage="收尾", percent=98,
                                  msg=f"进程异常退出但输出完整（{stem}），尝试 publish")

    if not stem:
        jobqueue.set_progress(job_id, stage="failed", percent=0,
                              msg=f"pipeline 退出码 {returncode}，未找到输出文件",
                              returncode=returncode)
        _mirror_job(opts, job_id, "failed", error=f"无输出(rc={returncode})")
        _no_retry()
        raise PipelineFailed(f"job {job_id}: no output (rc={returncode})")

    try:
        note_id = _publish(stem, opts)
    except Exception as e:
        jobqueue.set_progress(job_id, stage="failed", percent=0, msg=f"产出复制失败：{e}")
        _mirror_job(opts, job_id, "failed", error=f"产出复制失败：{e}")
        raise

    msg = "完成"
    if returncode not in (0, None):
        msg = f"完成（pipeline 退出码 {returncode}，已知 Windows cleanup 问题，不影响输出）"
    jobqueue.set_progress(job_id, stage="done", percent=100, msg=msg,
                          note_id=note_id, returncode=returncode)
    _mirror_job(opts, job_id, "done", note_id=note_id)
    return note_id


def _resolve_summary_path(note_id: str):
    """note_id → summary.json 路径。私有/已入库笔记走对象存储；
    旧公开 demo 笔记落在 web/public/notes/<id>/。找不到返回 None。"""
    safe = (note_id or "").strip()
    if not safe or "/" in safe or "\\" in safe or ".." in safe:
        return None
    try:
        row = userdata.notes_repo.get(safe)
    except Exception:
        row = None
    if row is not None:
        try:
            p = _get_store().file_path(row["storage_path"], "summary.json")
            if p.is_file():
                return p
        except Exception:
            pass
    p = SC.NOTES_DIR / safe / "summary.json"
    return p if p.is_file() else None


def _get_store():
    from object_store import default_store  # lazy：测试可 monkeypatch
    return default_store


def unload_qa_model() -> None:
    """卸载常驻在 worker 进程里的 QA 模型（Qwen ~5GB VRAM）。
    每个 pipeline 任务开跑前必须调用：12GB 卡上 pipeline 子进程内部还要加载
    全套模型（Whisper/Pegasus/CLIP/Qwen），不让位必 OOM。"""
    try:
        import segment_llm
        if getattr(segment_llm, "_MODEL", None) is None:
            return
        segment_llm._MODEL = None
        segment_llm._TOKENIZER = None
        import gc
        import torch
        gc.collect()
        torch.cuda.empty_cache()
        print("[worker] 已卸载常驻 QA 模型，VRAM 让位给 pipeline", flush=True)
    except Exception as e:
        print(f"[worker] QA 模型卸载异常（继续跑 pipeline）：{e}", flush=True)


def run_ask(qa_id: str, note_id: str, question: str, lang: str,
            history: Optional[list[dict]] = None) -> None:
    """RQ 任务：worker 进程内直接跑 qa.answer_question——模型常驻，首问冷加载
    ~1min，后续问题秒级（2026-06-11 从子进程模式改造，换首答延迟）。
    代价：CUDA 级硬崩会带垮 worker（Python 异常已兜住）；与 pipeline 的 VRAM
    互斥靠 run_generate 开头的 unload_qa_model()，worker 串行保证不并发。"""
    jobqueue.set_qa(qa_id, status="running")
    summary = _resolve_summary_path(note_id)
    if summary is None:
        jobqueue.set_qa(qa_id, status="failed", error="笔记不存在或缺 summary.json")
        return
    try:
        chunks = json.loads(summary.read_text(encoding="utf-8"))
        if not isinstance(chunks, list) or not chunks:
            jobqueue.set_qa(qa_id, status="failed", error="summary.json 为空或格式不对")
            return
        import qa as qa_mod
        # hybrid 检索：pipeline 落盘的 chunk 向量存在则启用（查询编码走 CPU，
        # 不与常驻 Qwen 抢 VRAM）；缺失/不匹配静默回落 BM25
        doc_vecs, embed_fn = None, None
        emb_file = summary.parent / "embeddings.npz"
        if emb_file.is_file():
            try:
                import embeddings as emb_mod
                vecs = emb_mod.load_chunk_embeddings(emb_file)
                if vecs and len(vecs) == len(chunks):
                    doc_vecs, embed_fn = vecs, emb_mod.encode_query
            except Exception:
                pass
        result = qa_mod.answer_question(chunks, question, lang=lang, history=history,
                                        doc_vecs=doc_vecs, embed_fn=embed_fn)
    except Exception as e:
        jobqueue.set_qa(qa_id, status="failed", error=f"问答失败：{e}")
        raise  # 让 RQ 记 failed registry（QA 未配 retry，不会重跑烧卡）
    jobqueue.set_qa(qa_id, status="done", result=result)


def _build_cmd(source: str, opts: dict, chunk_chars: int) -> list[str]:
    is_local = bool(opts.get("is_local"))
    cmd = [
        str(SC.PY), "src/pipeline.py", source,
        *(["--local"] if is_local else []),
        "--chunker", "texttile",
        "--chunk-chars", str(chunk_chars),
        "--chapters",
        "--summarizer", "neural",
        "--keyframes",
        "--llm-chapters",
        "--vlm-captions",
    ]
    quality = opts.get("quality") or "best"
    if not is_local and quality != "best":
        cmd += ["--quality", quality]
    return cmd


def _run_pipeline_subprocess(job_id: str, source: str, opts: dict):
    """spawn pipeline.py，流式解析 stdout 写 Redis 进度。返回 (stem|None, returncode)。
    （测试 monkeypatch 此函数为假实现。）"""
    is_local = bool(opts.get("is_local"))
    local_meta = opts.get("local_meta") or {}

    # Step 0：估时 + 选 chunk_chars
    chunk_chars = 800
    try:
        if is_local:
            dur = float(local_meta.get("duration") or 0)
        else:
            from download import fetch_metadata  # noqa
            jobqueue.set_progress(job_id, stage="探测", percent=2, msg="读取视频元信息")
            dur = float((fetch_metadata(source) or {}).get("duration") or 0)
        if dur > 0:
            chunk_chars = SC.adaptive_chunk_chars(dur)
            est = SC.estimate_pipeline_seconds(dur)
            jobqueue.set_progress(job_id, stage="探测", percent=3,
                                  msg=f"视频 {dur/60:.1f} min · 预计 {est/60:.1f} min · cc={chunk_chars}")
    except Exception as e:
        jobqueue.set_progress(job_id, stage="探测", percent=2, msg=f"元信息读取失败（不影响）：{e}")

    cmd = _build_cmd(source, opts, chunk_chars)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(SC.ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            env=env, bufsize=1,
        )
    except Exception as e:
        jobqueue.set_progress(job_id, stage="failed", percent=0, msg=f"启动失败：{e}")
        return None, -1

    lo, hi = 0, 0          # 当前 stage 的百分比带
    stem: Optional[str] = None
    for line in proc.stdout or []:
        line = line.rstrip()
        if not line:
            continue
        jobqueue.append_log(job_id, line)

        marker = parse_progress_marker(line)
        if marker:
            metrics = jobqueue.record_stage_start(job_id, marker)
            lo, hi = stage_band(marker["i"], marker["n"])
            jobqueue.set_progress(job_id, stage=marker["label"], percent=lo,
                                  msg=marker["label"], metrics=metrics)
            continue

        # 细粒度行：在当前 stage 带内插值
        m = re.search(r"\[asr\]\s*([\d.]+)\s*s\s*/\s*([\d.]+)\s*s", line)
        if m:
            frac = float(m.group(1)) / max(float(m.group(2)), 0.1)
            jobqueue.set_progress(job_id, percent=interpolate(lo, hi, frac),
                                  msg=f"语音识别 {float(m.group(1)):.0f}s/{float(m.group(2)):.0f}s")
            continue
        m = re.match(r"\s*\[pegasus\]\s*(\d+)/(\d+)", line)
        if m:
            frac = int(m.group(1)) / max(int(m.group(2)), 1)
            jobqueue.set_progress(job_id, percent=interpolate(lo, hi, frac),
                                  msg=f"Pegasus {m.group(1)}/{m.group(2)}")
            continue
        m = re.match(r"\s*\[clip\]\s*(\d+)/(\d+)", line)
        if m:
            frac = int(m.group(1)) / max(int(m.group(2)), 1)
            jobqueue.set_progress(job_id, percent=interpolate(lo, hi, frac),
                                  msg=f"CLIP 关键帧 {m.group(1)}/{m.group(2)}")
            continue
        if "[OK]" in line and "笔记" in line:
            mm = _OUT_STEM_RE.search(line)
            if mm:
                stem = mm.group(1)
    proc.wait()
    return stem, proc.returncode


def _scan_output_fallback(job_id: str, started: float) -> Optional[str]:
    """subprocess 没吐 stem 时，扫 data/outputs 找 job 时段内新写的 md（Windows
    cleanup crash 但产物完整的情形）。返回 stem 或 None。
    （测试 monkeypatch 此函数。）"""
    candidates = [p for p in SC.DATA_OUTPUTS.glob(_OUT_GLOB)
                  if p.stat().st_mtime >= started - 30]
    if not candidates:
        return None
    candidates.sort(key=lambda p: -p.stat().st_mtime)
    # 旧 regex 只认 (.mm)?，线上配置实际产出 .cc{N}.mm.vl → 剥不掉后缀，
    # publish 拿到带后缀的假 stem 必然找不到文件。现在覆盖全部可选段。
    return _OUT_SUFFIX_RE.sub("", candidates[0].stem)

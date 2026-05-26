# scripts/ 索引

51 个脚本，按用途分组。Dispatcher 命名规则：

- `_dryrun_*.py` — 只读，跑当前代码的逻辑在已有产物上做对比，不写盘
- `_postfix_*.py` — 对已生成的产物做就地修补（最次写一次，不重新跑 LLM/ASR）
- `_apply_*.py` — 轻量化重跑：只重做一个阶段并同步 web，不重 ASR
- `regen_*.py` — 复用已有产物重生成下游
- `eval_*.py` / `compare_*.py` / `analyze_*.py` — 论文表 / ablation / 数据分析
- `run_*.py` / `rerun_*.py` / `retry_*.py` / `audit_*.py` / `stabilize_*.py` — 一次性批跑 corpus
- `show_*.py` / `check_*.py` — 只读人工诊断
- `test_*.py` / `verify_*.py` / `smoke_test.py` / `stress_*.py` — smoke / regression test

跑法：所有脚本必须用项目 venv：`./.venv/Scripts/python.exe scripts/<file>.py`。

---

## 必跑 / 常态运维（落地 + 同步 web）

| 脚本 | 用途 |
|---|---|
| `_apply_chapter_titles.py` | 轻量化 apply：只重跑 `refine_chapter_titles` + 同步 web 的 title/title_zh/title_en，含 CJK 残留检测重试 |
| `regen_chapter_abstracts.py` | 重跑 chapter abstract（不重 ASR / 章节切分） |
| `regen_md.py` | 复用现有 summary/chapters.json 重新生成 markdown |
| `translate_notes.py` | 给 web/public/notes/ 补双语字段（title/abstract/headline/text/summary/keywords 的 _zh/_en） |
| `_postfix_asr_titles.py` | 历史 chapters.json 章标题/abstract/recap 里的 ASR 同音字 post-fix |
| `_postfix_qmask.py` | strip 已存在 chapters.json 里 LLM 误复制的 `[?]` 字面 |
| `prepare_web_demo.py` | 把 data/outputs 产物拷贝到 web/public/notes/{id}/ |
| `backfill_category.py` | 扫 web/public/notes/ 给每个笔记 meta.json 回填 category |
| `backfill_category_raw.py` | 扫 data/raw 给 meta.json 回填 category，并同步到 web |
| `build_catalog.py` | 扫 web/public/notes/ 重建 catalog.json（也是 ID 约定的 source-of-truth）|

---

## 论文表 / Ablation / 评估

| 脚本 | 用途 |
|---|---|
| `aggregate_eval.py` | 聚合 chapters.json + meta.json 为论文附录 B 表（markdown） |
| `build_mm_manifest.py` | /mm-ablation 前端页的 manifest.json |
| `eval_segmentation.py` | 章节切分评估：chunker × alpha 双 ablation，8 视频 benchmark |
| `eval_headlines.py` | Headline 质量自动评估，跨 8 视频 × 2 chunker |
| `eval_dedupe_ablation.py` | dedupe on/off ablation |
| `eval_chunk_chars_sweep.py` | chunk_chars ∈ {200,400,600,800,1000} sweep |
| `eval_texttile_at_cc800.py` | texttile × cc=800 × alpha sweep |
| `compare_segmentation.py` | 多模态章节切分 ablation 按段落对齐打印 |
| `compare_chapter_k.py` | 新旧 `num_chapters` 默认公式对比 |
| `compare_headlines_after_cleaning.py` | chunk cleaning 启用前后 headline 对比 |
| `compare_asr.py` | 两份 ASR 输出并排对比，字符级差异 |
| `analyze_human_ratings.py` | 人工打分 vs 自动指标关联分析 |
| `sample_headlines_for_rating.py` | stratified 抽 30 个 headline 给人工打分 |
| `md_to_docx.py` | paper/draft.md → .docx |

---

## Dryrun（迭代时跑，验证当前代码效果，不写盘）

| 脚本 | 用途 |
|---|---|
| `_dryrun_chapter_titles.py` | 章标题 prompt 回归（J6/J7 用过） |
| `_dryrun_chapter_abstracts.py` | 章 abstract 校准回归 |
| `_dryrun_chapter_recaps.py` | 章末复习 LLM 生成测试 |
| `_dryrun_chapter_quizzes.py` | 章末自测题 LLM 生成 |
| `regress_segment_rules.py` | 真 Qwen 在代表视频上跑 segment_hierarchical 回归 |

---

## 一次性批跑（保留作为可回溯，普通迭代别动）

| 脚本 | 何时跑过 |
|---|---|
| `audit_batch.py` | 一次跑 6 新视频审查批 |
| `run_new_videos.py` | 扩 benchmark 跑 2 视频 |
| `run_5_new_videos.py` | 扩 21+ corpus，5 新视频 mm.vl 全 pipeline |
| `retry_3_failed.py` | batch_5_new 里 3 个失败 case 重跑 |
| `rerun_all_chunkers.py` | 8 视频 × 2 chunker × cc=400 全 ablation 重跑 |
| `rerun_asr_with_hotword.py` | 用新 domain-aware initial_prompt 重跑 ASR |
| `stabilize_summaries.py` | 锁 8 视频 × 2 chunker summary.json 在 cc=800 + α=0.3 |

---

## 调研 / 探针（只读，写脚本前先跑这些）

| 脚本 | 用途 |
|---|---|
| `analyze_gaps.py` | ASR segment 静音 gap 分布（定 VAD chunking 阈值） |
| `analyze_punct.py` | ASR segment 末标点分布 |
| `dedupe_scan.py` | 扫所有 ASR cache 看 dedupe 影响 |
| `check_meta.py` | 候选视频 metadata 是否符合 benchmark 选片 |
| `show_all_chunks.py` | 列所有 8 视频 × 2 chunker chunks，便于一次性标 gold |
| `show_chunks.py` | 列单视频 chunks 的 headline+keywords，标 gold 边界 |
| `show_meta.py` | B 站视频 metadata（UTF-8 安全输出） |

---

## Smoke / 单元测试

| 脚本 | 用途 |
|---|---|
| `smoke_test.py` | 项目轻量自动 smoke test（无 GPU 重路径） |
| `stress_test_auto_subs.py` | 强制 LLM 反复输出"倔强单顶层"，验证 auto_subs 兜底 |
| `test_pegasus.py` | Pegasus 模型加载冒烟 |
| `test_texttile.py` | chunk_by_chars vs texttile 对比 |
| `test_trim_outliers.py` | trim_topic_outliers 在 9 个失败 chunks 上 |
| `verify_chapter_titles.py` | Pegasus 章标题 copy-detection + fallback 验证（p39 等） |
| `verify_fixes.py` | 三个 fix 在 p39+王道 OS+计网 p38 上的验证 |

---

## 笔记 ID 约定

`web/public/notes/{id}/` 与 `data/outputs/{stem}.*.chapters.json` 共享同一 `id`。

- **Canonical**: BV-prefix 长 id（如 `BV1BE411D7ii_p68_p0`）— 现 28 个笔记，BV 号 + 分 P + `_p0`（首段 / 全片）
- **Legacy**: 5 个早期 demo 短 id（`python` / `os` / `claudecode` / `network` / `linear-algebra`）— 不再新增；保留向后兼容
- 不要 rename 现有目录（会破坏 `data/outputs/{stem}` ↔ `web/public/notes/{id}` 交叉引用）

`catalog.json` **不是 source-of-truth**：
- 前端通过 `/api/notes` 直接 `fs.readdir(public/notes/)` 拿列表（见 `web/app/api/notes/route.ts`）
- `catalog.json` 仅作 SSR 兜底，由 `scripts/build_catalog.py` 重生成

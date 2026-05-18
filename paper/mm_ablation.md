# 多模态 ablation：纯文本 vs CLIP-sim vs VLM-caption 三栏对比

配对：9 个视频 txt+mm 都跑了；其中 9 个也跑了 mm.vl（VLM caption）。

| # | 视频 | 时长 | 段数 | txt 章/att/通过 | mm 章/att/通过 | mm.vl 章/att/通过 | vl 自适应 |
|---|---|---|---|---|---|---|---|
| 1 | 王道计算机考研 计算机网络 p38 3.6.2 以太网与IEEE 802.3（咸鱼版） | 37:19 | 11 | 5/1/#1 | 6/1/#1 | 6/1/#1 | used (n_chunks=11 ≤ 15) |
| 2 | 王道计算机考研 计算机网络 p44 3.8 以太网交换机（咸鱼版） | 28:54 | 9 | 4/3/#3 | 4/2/#2 | 3/2/#2 | downgrade→sim (prefix_run=5/9 同质化) |
| 3 | BV19E411D78Q_p46_p0 | 33:40 | 11 | 7/2/#2 | 4/2/#2 | 4/2/#2 | used (n_chunks=11 ≤ 15) |
| 4 | BV19E411D78Q_p49_p0 | 33:22 | 11 | 3/1/#1 | 5/1/#1 | 4/1/#1 | used (n_chunks=11 ≤ 15) |
| 5 | 33 分钟掌握 Vibe 编码基础知识 | Vibe Coding Fundamentals In  | 33:22 | 46 | 11/3/#3 | 10/3/rep | 10/3/rep | downgrade→sim (n_chunks=46 > 15) |
| 6 | 【中配+原声】2026年，如何学习编程 - Tina Huang _ 26-03-10 p02 原声 | 15:49 | 21 | 10/3/#3 | 8/3/fb | 6/2/#2 | downgrade→sim (n_chunks=21 > 15) |
| 7 | 【AI 产品】Tina Huang｜吴恩达 8 小时 AI Agent 课程精华版 | 30:23 | 36 | 16/3/rep | 9/3/rep | 9/3/rep | downgrade→sim (n_chunks=36 > 15) |
| 8 | 王道计算机考研 操作系统 p37 2.3.5_3 哲学家进餐问题 | 15:00 | 5 | 3/2/#2 | 3/1/#1 | 5/1/#1 | used (n_chunks=5 ≤ 15) |
| 9 | AI Agents in 25 Minutes (n8n Tutorial) | 25:57 | 34 | 13/3/fb | 32/1/#1 | 9/2/#2 | downgrade→sim (n_chunks=34 > 15) |

## 汇总

- 跑了三路对比的视频：9/9
- VL 自适应实际启用 caption：4
- VL 自适应降级回 sim cue：5（外层 n_chunks>15: 4，内层 prefix_run 同质化: 1）
- VL caption 启用且切更细（vs mm）：1/4

**字段说明**: `章/att/通过` = 章数 / LLM attempts / 通过方式 (#1/#2/#3/rep=repair/fb=fallback)
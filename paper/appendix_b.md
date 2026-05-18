# 附录 B：评估视频切分路径汇总

共 9 个视频 × 默认配置（chunker=texttile, cc=800, summarizer=neural, --llm-chapters）。

| # | 视频 | 语言 | 时长 | 段数 | 章数 | max ch | 切分路径 | LLM attempts | 通过方式 | repair | wrap-up |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 王道计算机考研 计算机网络 p38 3.6.2 以太网与IEEE 802.3（咸鱼版） | zh | 37:19 | 11 | 5 | 3 | LLM | 1 | attempt #1 | - | ✓ |
| 2 | 王道计算机考研 计算机网络 p44 3.8 以太网交换机（咸鱼版） | zh | 28:54 | 9 | 4 | 4 | LLM | 3 | attempt #3 | - | ✓ |
| 3 | BV19E411D78Q_p46_p0 | zh | 33:40 | 11 | 7 | 3 | LLM | 2 | attempt #2 | - | ✓ |
| 4 | BV19E411D78Q_p49_p0 | zh | 33:22 | 11 | 3 | 5 | LLM | 1 | attempt #1 | - | ✓ |
| 5 | 33 分钟掌握 Vibe 编码基础知识 | Vibe Coding Fundamentals In  | zh | 33:22 | 46 | 11 | 5 | LLM | 3 | attempt #3 | - | - |
| 6 | 【中配+原声】2026年，如何学习编程 - Tina Huang _ 26-03-10 p02 原声 | zh | 15:49 | 21 | 10 | 4 | LLM | 3 | attempt #3 | - | - |
| 7 | 【AI 产品】Tina Huang｜吴恩达 8 小时 AI Agent 课程精华版 | zh | 30:23 | 36 | 16 | 4 | LLM | 3 | repair (after 3 attempts) | repair_missing+repair_oversize | - |
| 8 | 王道计算机考研 操作系统 p37 2.3.5_3 哲学家进餐问题 | zh | 15:00 | 5 | 3 | 2 | LLM | 2 | attempt #2 | - | - |
| 9 | EH5jx5qPabU_p0 | en | 25:57 | 34 | 19 | 5 | LLM | 2 | attempt #2 | - | - |

## 汇总统计

- 总视频数：9（中文 8 / 英文 1）
- **LLM 切分成功**：9/9 = 100%
- LLM attempt 1 直接通过：2/9 = 22%
- **程序化 repair 救活**：1/9 = 11%
- `_repair_oversize` 实际触发：1/9
- Fallback 到 TextTiling：0/9
- 末尾 wrap-up 章被识别：4/9
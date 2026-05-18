### 6.4 24 视频 corpus：多模态架构泛化验证（auto-aggregated）

VL caption + 三层自适应架构在以下 24 视频 corpus 上的完整验证。

| 视频 | n | mm.vl 章 | VL 路径 | LLM 状态 | 备注 |
|---|---|---|---|---|---|
| 王道计算机考研 计算机网络 p34 3.5.2_4 CSMA CA协议（咸鱼版） | 12 | 5 | used | #2 |  |
| 王道计算机考研 计算机网络 p38 3.6.2 以太网与IEEE 802.3（咸鱼版） | 11 | 6 | used | #1 |  |
| 王道计算机考研 计算机网络 p44 3.8 以太网交换机（咸鱼版） | 9 | 3 | **内层 gate** | #2 | prefix_run=5/9 |
| BV19E411D78Q_p46_p0 | 11 | 4 | used | #2 |  |
| BV19E411D78Q_p47_p0 | 12 | 4 | **内层 gate** | #2 | prefix_run=4/12 |
| BV19E411D78Q_p48_p0 | 13 | 4 | used | #2 |  |
| BV19E411D78Q_p49_p0 | 11 | 4 | used | #1 |  |
| 特厨探店|讲究的淮扬菜是什么样？—二泉园老菜馆 | 2 | 2 | used | #1 |  |
| 从 LLM 到 Agent Skill，一期视频带你打通底层逻辑！ | 14 | 6 | used | #3 |  |
| 33 分钟掌握 Vibe 编码基础知识 | Vibe Coding Fundamentals In  | 46 | 10 | 外层 gate | repair |  |
| BV1h5L364Ezv_p0 | 3 | 3 | used | #1 |  |
| BV1nBWyzBEp2_p2_p0 | 37 | 8 | 外层 gate | repair |  |
| 【中配+原声】2026年，如何学习编程 - Tina Huang _ 26-03-10 p02 原声 | 21 | 6 | 外层 gate | #2 |  |
| 【YouTube最好的英语播客】level 1 | 适合每日磨耳朵，绝佳的英语听力素材 p01 Ep | 10 | 3 | used | #2 |  |
| 【YouTube最好的英语播客】level 1 | 适合每日磨耳朵，绝佳的英语听力素材 p03 Ep | 5 | 5 | used | #3 | prefix_run=4/5 |
| 【AI 产品】Tina Huang｜吴恩达 8 小时 AI Agent 课程精华版 | 36 | 9 | 外层 gate | repair |  |
| BV1VsTfzdEZE_p0 | 3 | 1 | used | #1 |  |
| 王道计算机考研 操作系统 p37 2.3.5_3 哲学家进餐问题 | 5 | 5 | used | #1 | prefix_run=4/5 |
| BV1YE411D7nH_p47_p0 | 9 | 3 | used | #1 |  |
| BV1YE411D7nH_p53_p0 | 9 | 3 | used | #1 |  |
| BV1YP5W6ZEP9_p0 | 5 | 3 | used | #2 |  |
| AI Agents in 25 Minutes (n8n Tutorial) | 34 | 9 | 外层 gate | #2 |  |
| FwOTs4UxQS4_p0 | 11 | 6 | **救援** | #2 | 救援触发 |
| WSPChlfxJyA_p0 | 27 | 12 | 外层 gate | fb | 唯一 fallback |

**核心数据**：

| 维度 | 数值 |
|---|---|
| LLM 切分覆盖率 | **23/24 = 96%** |
| 一次过 (attempt 1) | 8/24 |
| Retry-with-feedback (attempt 2-3) | 12/24 |
| Programmatic repair | 3/24 |
| 救援触发 | 1/24 |
| 外层 gate 降级 | 6/24 |
| 内层 gate 降级 | 2/24 |
| Fallback TextTiling | 1/24 |
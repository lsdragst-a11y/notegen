# 独立边界复核：Batch 4（6 个视频）

> 复核人：只读分析代理 | 日期：2026-06-10  
> 方法：先通读 ASR 句级转写独立标话题切点，再载入 LLM 草稿对比，产出提议边界。

---

## BV1W8AGzwEFW_p0 — 在上海花2000点外卖都能吃到啥？带你狠狠大吃一顿！ (1006.74s, vlog)

| 时间 | 话题 |
|---|---|
| 0–230 | 开场+聚会+第一波外卖依次到场并尝味（达美乐、生煎、鸭血粉丝、蛋饼、越南粉、牛油锅） |
| 230–284 | 品牌广告插播（内裤赞助商，约 230–283s 明显话题断裂） |
| 284–368 | 广告后回归：外卖吐槽（难吃/不纯粹），全标牛排试吃，馄饨/紫菜麻糬 |
| 368–501 | 新一批菜品：鲜肉潮汕薄皮蒸饺、螺蛳粉对比（重庆 vs 上海），白切鸡 |
| 501–667 | Taco / 德式烤猪手 / 包子馅肠粉 / 上杯 / 韭菜鸡蛋包子讨论 |
| 667–805 | 印度咖喱饭 / 寿宇朝饭 / 印度薄饼收尾 |
| 805–1006 | 门口找到的大可炸鸡 / 评选最佳 / 次日早晨收尾 |

**LLM 草稿 [262.09, 368.87, 522.98, 805.51]**：
- 262.09：`~挪→284.09`。262s 处正值广告末尾（"透气率更是高达636毫米每秒"），真正回到外卖话题的切点在 284.09（"这东西重新吃不到吗"，明确话题复归）。
- 368.87：`✓` 强边界，"鲜肉潮汕 薄皮蒸饺"起新一批菜品，上一轮吃完自然收束。
- 522.98：`~挪→501.98`。501s"Taco/跟我俩人"为 Taco 首次登场，是场景切换点；522s 仅是继续讨论，不是新起点。
- 805.51：`✓` 强边界，"哈哈哈哈"后转入正式寻找炸鸡 + 评总结段。

**提议边界**：[284.09, 368.87, 501.98, 667.96, 805.51]  （6 段）

**备注**：中等置信度；广告断点 284.09 > 262.09；501.98 比 522.98 更贴合 Taco 话题开启；增补 667.96（印度菜段切入）；共 6 段符合 vlog 颗粒度。

---

## BV1QQ5x6eEZh_p0 — 泡面实力排行！究竟哪款夯到爆！！ (373.4s, vlog)

> ⚠️ **domain 不一致**：gold 文件 `domain` 字段为 `"learning"`，manifest 指定为 vlog；内容实为吃播/测评类，按 vlog 判定。

| 时间 | 话题 |
|---|---|
| 0–57 | 经典旗舰款群（番茄鸡蛋面、红烧牛肉面、老坛酸菜、老母鸡汤） |
| 57–101 | 大桶/香辣牛肉面 + 藤椒牛肉（辣口经典延伸款） |
| 101–157 | 特色味型款（NPC 级鲜虾鱼板面、超香香菜面） |
| 157–256 | 外国款 + 中国地方款（韩国辛拉面、安徽板面、河南烩面、老北京炸酱面） |
| 256–357 | 火鸡拌面 + 酸辣藤骨面 + 热干面 + 总结（高分段） |

**LLM 草稿 [69.64, 157.04, 256.92, 305.74]**：
- 69.64：`~挪→57.98`。69.64s 处为"老母鸡汤面"叙述中段；57.98（"老母鸡汤面"正式开始）才是此款起点，但更合适的组别切换在 77.14（"香辣牛肉面大桶装"，完成经典四款，转入大桶辣口款）。调整为 `~挪→77.14`。
- 157.04：`✓` 合理边界，韩国辛拉面为唯一外国款，明显话题切换。
- 256.92：`~挪→252.94`。256.92s 处正值"河南烩面/羊汤"叙述中，252.94（"河南烩面…和正宗线下比"）进入地方款末尾过渡更准；但差异小，也可保留 256.92。
- 305.74：`✓` 火鸡拌面"必须给导航"，新高分段开始。

**提议边界**：[77.14, 157.04, 256.92, 305.74]  （5 段）

**备注**：高置信度；内容为顺序试吃，颗粒度与 LLM 草稿基本吻合；domain 字段 `learning` 有误，应为 vlog/探店/测评。

---

## BV13BREBrEjU_p0 — 随机挑战！69元吃菜单上第6个食物，被命运安排了… (510.13s, vlog)

> ⚠️ **domain 不一致**：gold 文件 `domain` 字段为 `"learning"`，manifest 指定为 vlog；内容为 city walk 探店挑战，按 vlog 判定。

| 时间 | 话题 |
|---|---|
| 0–86 | 开场介绍挑战规则 + 第一家蜜雪冰城（葡萄雪葩酸奶冰）+ city walk 决定 |
| 86–170 | city walk 路上随机找第六家店 → 找到馒头店，品尝评分 |
| 170–288 | 商场内冒险：Dlonke Bark 可颂门店 → 三重奏黑巧蛋糕（29元） |
| 288–398 | 街头继续：锅盔夹凉粉（9元） + 中招（不便宜/买不到） |
| 398–510 | 最后2.5元挑战 → 牛杂筋（2元）品尝 + 挑战成功 + 结语 |

**LLM 草稿 [86.58, 170.29, 288.52, 398.06]**：
- 86.58：`✓` 强边界，"看着有点像大理石的质感"是葡萄雪葩评价结束 + city walk 转场开始（"今天的金额…city walk"→第六家店逻辑）。86.58 处正好是"看着有点像…旺仔Q糖"，即第一家完成、转入寻找。
- 170.29：`✓` 馒头品尝结束，"感觉越吃越好吃了"→ 进入商场段，切点准确。
- 288.52：`✓` 巧克力蛋糕吃完，"这一口下去…耶回到解放前"→ 继续找下一个，切点合理。
- 398.06：`~挪→432.94`。398.06s 为"开个玩笑开个来说"（锅盔后闲聊）；实际牛杂筋场景从 432.94（"随便数啊 一二三四五六"）才开始，是新的随机挑战点。`~挪→432.94`。

**提议边界**：[86.58, 170.29, 288.52, 432.94]  （5 段）

**备注**：中等置信度；398.06 → 432.94 是主要改动（锅盔结束后的闲聊段归入前一章更合理）；domain 字段 `learning` 有误，应为 vlog。

---

## FwOTs4UxQS4_p0 — AI Agents, Clearly Explained (607.49s, english)

| 时间 | 话题 |
|---|---|
| 3–64 | 引言：视频定位，1-2-3 学习路径概述 |
| 64–137 | Level 1：大语言模型（LLM）基础——输入输出模型，被动性，知识局限性 |
| 137–175 | Level 2 开篇：AI 工作流——预定义路径概念引入，Calendar 示例 |
| 175–285 | Level 2 深化：工作流的控制逻辑，RAG 定义，make.com 实例演示 |
| 285–361 | Level 3 过渡：AI 工作流与 AI 代理的区别——人类决策者被 LLM 替代 |
| 361–443 | Level 3 核心：代理三特征（Reason + Act = ReAct，Iterate），LinkedIn 例子 |
| 443–577 | 真实代理案例：Andrew Ng 视觉代理 demo，n8n 预告，3 级可视化总结 |
| 577–607 | 结尾：总结三层，推荐资源，Notion 提示库 |

**LLM 草稿 [64.54, 175.06, 285.7, 361.47, 443.83, 577.42]**：
- 64.54：`✓` "Kicking things off at level 1, large language models"——明确新主题起点。
- 175.06：`✓` "This is a fundamental trait of AI workflows"——工作流节固定路径总结后自然转段。但 175.06 仍在 workflow 内；更准确的 Level 2 引入在 137.72（"Moving to level two, AI workflows"）。`~挪→137.72`。
- 285.7：`✓` "As you can see, this is an AI workflow…Step one, Step two, Step three"——make.com 实例总结，转入 Level 3 概念。
- 361.47：`✓` "the AI agent must reason"——代理核心定义，ReAct 展开。
- 443.83：`✓` "autonomously add in another LLM to critique"——迭代能力展开，Andrew Ng demo 引入。
- 577.42：`✓` "receives a goal…how best to achieve the goal"——可视化总结三级架构，进入结语。

**提议边界**：[64.54, 137.72, 285.7, 361.47, 443.83, 577.42]  （7 段）

**备注**：高置信度；唯一调整是 175.06→137.72（Level 2 正式起点）；整体结构清晰，章节与教学层级一一对应。

---

## EH5jx5qPabU_p0 — AI Agents in 25 Minutes (n8n Tutorial) (1556.65s, english)

| 时间 | 话题 |
|---|---|
| 0–87 | 引言 + 代理定义 + Agent vs Automation 对比（静态流程 vs 动态推理） |
| 87–219 | 代理三组件（Brain/Memory/Tools）+ 单代理 vs 多代理 + 护栏（guardrails） |
| 219–319 | HubSpot 赞助插播 + 理论快速回顾（recap of agent theory） |
| 319–484 | APIs & HTTP 请求详解（GET/POST，vending machine 比喻，框架概念） |
| 484–689 | N8n 平台介绍 + 开始构建（trigger, AI agent node, 设计思路） |
| 689–855 | 设置 LLM（OpenAI 连接 + API Key）+ 内存（simple memory + 上下文窗口）+ 聊天演示 |
| 855–997 | 工具接入：Google Calendar + OpenWeather API + Google Sheets |
| 997–1230 | 自定义工具：AirNow HTTP 请求节点 + 写提示词给代理 |
| 1230–1395 | 测试 + 错误排查（2 轮 error + ChatGPT fix 演示）+ 运行成功 |
| 1395–1556 | 聊天模式演示 + 商业应用场景 + N8n/Futurepedia 资源推荐 |

**LLM 草稿 [219.62, 319.02, 484.94, 689.93, 855.19, 997.05, 1230.83, 1395.11]**：
- 219.62：`✓` "one agent acts as a manager and delegates tasks"——多代理系统完成，HubSpot 赞助段开始（219s "I always come back..."过渡句）。实际赞助从 304.78 起（"There's a lot of information in this video...HubSpot"），但 219.62 把多代理/护栏纳入同一章，语义上可接受。`~挪→210.56`（"We'll be building a single agent system"——前文总结，护栏未开始）但差异小，保留草稿。
- 319.02：`✓` 赞助完结，"We've covered a lot so let's quickly recap"——理论收束后进入 API 技术章节，362s "APIs and APIs are both HTTP requests"是 API 正式起点。`~挪→362.52` 更准，但 319.02 也可作为理论回顾/技术导入的边界。保留。
- 484.94：`✓` "With N8n you don't have to build everything from scratch"——API 概念完结，N8n 平台正式介绍，强切点。
- 689.93：`✓` "every morning it checks my calendar…AI agent node, memory"——从代理设计转入 LLM 配置，强切点。
- 855.19：`✓` "of open AI models"——LLM/Memory 配置完成，工具接入（Google Calendar）开始。
- 997.05：`~挪→976.18`。997.05s "drop downs to tell it to"为 Google Calendar 设置中段；976.18（"now it's finally time to build...we're going to start"→等等这是 670s）——重新确认：976s 起"click save up at the top"→ 存档，997s 进入下一工具。实际下一大主题是 HTTP 自定义工具，从 1040.61（"with N8n you don't have to build everything from scratch...HTTP request"）或 1188.78（"here's how, first I'll add a new tool and search for HTTP request"）起。但 997.05→1040.61 段是 Google Sheets + Gmail 工具，仍属工具接入段。`✗ 多切`——建议合并 855-1230 为一个大"工具配置"章，或在 1040.61 切分为两小章：标准工具 vs 自定义 HTTP 工具。按当前 9 段颗粒度，`~挪→1040.61`。
- 1230.83：`✓` "so I'll use the query tool…that's all I need"——AirNow URL 获取完成，转入提示词撰写 + 测试阶段。
- 1395.11：`✓` "so I just go to the node, but I still got an error"——调试段结束/成功后，聊天演示段开始（1406.16 "this time it completed"）。实际 1395.11 仍在第二个 error 修复中，1406.16 才完成并进入演示。`~挪→1406.16`，差异小，可保留草稿。

**提议边界**：[219.62, 319.02, 484.94, 689.93, 855.19, 1040.61, 1230.83, 1406.16]  （9 段）

**备注**：中高置信度；主要改动：997.05→1040.61（自定义 HTTP 工具是独立技术主题，更清晰的切点）；1395.11→1406.16（调试成功后再切，避免将 error 修复剖半）；其余草稿边界质量高。

---

## WSPChlfxJyA_p0 — (Claude AI Features Walkthrough) (1151.72s, english)

| 时间 | 话题 |
|---|---|
| 0–118 | 引言：Claude 定价 + 基础聊天界面 + 为什么不要用 global 自定义指令 |
| 118–239 | 提示公式：ICC（Instructions / Context / Constraints），示例对比 |
| 239–329 | 上下文访谈技巧 + 网页搜索功能 |
| 329–443 | 文件上传 + Artifacts 概念引入（analytics dashboard, p5.js 示例） |
| 443–553 | Artifacts 深入：可下载文件，写作模式，各类格式演示 |
| 553–639 | Research 研究模式（agentically, 169 sources, citations） |
| 639–718 | Projects 项目系统引入（persistent memory/chat history/知识库） |
| 718–823 | Project 具体设置（custom instructions, project files, 限制说明） |
| 823–891 | Skills 概述（Anthropic 内置 vs 自定义 skills，创建方法） |
| 891–974 | Skills 实战演示（YouTube 四个 skills：critique/intro/title/summary） |
| 974–1053 | Connectors（Google Drive/Calendar/Slack/Asana，Granola 示例） |
| 1053–1151 | 模型选择（Opus/Sonnet/Haiku）+ 桌面版 + Claude Code 预告 |

**LLM 草稿 [163.65, 239.13, 329.56, 443.79, 553.47, 639.41, 718.78, 823.73, 891.39, 974.47, 1053.54]**：
- 163.65：`~挪→118.36`。163.65s "context is setting the stage with your role objectives"仍是 ICC 公式讲解中段；118.36（"now back to the prompt box…the three most important parts"）才是 ICC 公式的真正起点，prompt 功能讲完了 global instruction 的弊端后转回。`~挪→118.36`。
- 239.13：`✓` "So I could skim through it and then ask to elaborate"——迭代示例完结，进入 context interview 讲解，切点准确。
- 329.56：`✓` "And you'll need to ask it to search the web in your prompt"——网页搜索节结束（ground-first-ask-second 示例），文件上传新主题，切点准确。
- 443.79：`✓` "And take a screenshot of my channel"——从文件上传功能转入 YouTube channel 分析，Artifacts dashboard 延伸，切点合理。但 443.79s 与 Artifacts 主题衔接略松；479.43（"using the plus button…you can upload files to work from or analyze"）已在描述文件上传，而 artifact 引出在 553s（"these are called artifacts"）。从内容看 329–553 可视为一个大"创作 Creation"章，11 段切分粒度细，维持 LLM 划法。
- 553.47：`✓` "That you can view directly inside Claude. Or download"——从 Artifacts 的可下载文件，进入 Artifacts 独立窗口详述，切点合理。
- 639.41：`✓` "This completely changes how Claude finds and analyzes information"——Artifacts 章结束，Research 模式引入，强切点。
- 718.78：`✓` "That only apply to that project. It's far more effective"——Research 完成，Projects 系统详细讲解开始（project instructions/files）。
- 823.73：`✓` "Custom skills are ones you or your organization create"——Projects 设置完毕，Skills 概念引入，强切点。
- 891.39：`✓` "One is my script critique skill"——Skills 理论完，进入实战演示，强切点。
- 974.47：`~挪→999.37`。974.47s "That I put in YouTube descriptions"仍为 Skills 演示末尾（summary skill 说明）；999.37（"Connectors allow Claude to access different apps"）是 Connectors 正式定义，更准的新话题起点。`~挪→999.37`。
- 1053.54：`✓` "Opus is the most powerful model for complex tasks"——Connectors 章完结，模型选择新章，切点准确。

**提议边界**：[118.36, 239.13, 329.56, 443.79, 553.47, 639.41, 718.78, 823.73, 891.39, 999.37, 1053.54]  （12 段）

**备注**：高置信度；主要改动：163.65→118.36（ICC 起点提前）；974.47→999.37（Connectors 定义句更准）；其余草稿与内容结构高度吻合。

---

*以上提议边界仅基于转写文本分析，最终需对照视频画面/场景切换核定。*

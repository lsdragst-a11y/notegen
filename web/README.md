# NoteGen Web — 教学视频笔记前端

Next.js 16 + Tailwind 4 + Plyr + Framer Motion，苹果风格 UI。

## 开发

```bash
# 第一次：准备 demo 数据（从 backend 输出 copy 到 web/public/）
cd ..  # to E:\claudeproject\notegen\
.venv/Scripts/python.exe scripts/prepare_web_demo.py

# 起 dev server
cd web
npm run dev
# 打开 http://localhost:3000
```

## 结构

```
app/
  page.tsx                # landing：粒子背景 + hero + demo 卡片
  notes/[id]/page.tsx     # 详情：左视频 + 右笔记
components/
  NoteWorkspace.tsx       # 三栏工作台：章节、笔记、视频与工具
  ChatPanel.tsx           # 时间戳问答入口
  VideoPlayer.tsx         # Plyr 包装，dynamic import 避开 SSR
  ChapterChip.tsx         # Dynamic Island 风格章节浮窗
  NotesContent.tsx        # 笔记主体（顶部卡 + 知识点速览 + 章节 + 术语表）
  GlossaryList.tsx        # 术语 hover 显示 snippet
lib/
  types.ts                # 跟 backend summary.json/chapters.json 对齐的类型
  notes.ts                # fetch / 重难点检测 / 术语聚合（与 backend 算法一致）
public/
  notes/{id}/             # 每 demo: summary.json + chapters.json + meta.json + keyframes/
  notes/catalog.json      # landing 卡片用
  videos/{id}.mp4         # demo 视频文件
```

## 当前 demo 视频（5 个，~115MB）

- python — 20 分钟学完 Python 基础
- os — 王道操作系统 哲学家进餐
- claudecode — 10 分钟学会 Claude Code
- network — 计算机网络 以太网与 MAC 帧
- linear-algebra — 考研数一线代

## 关键交互

- 点 demo 卡片 → 进详情
- 视频播放 → 章节 chip 自动更新当前章 + 进度
- 点知识点速览卡片 → 视频 seek 到对应时间
- 点章标题旁时间 → seek
- 术语表 hover → 显示 snippet + 跳转按钮
- 视频上方进度条带章节色块

## 后端接入路线

当前纯静态 demo。后续路径：
- FastAPI 后端 `/api/generate` 接收 URL，跑 pipeline，存到 public/notes/
- WebSocket 进度推送：[1/4] 下载 → [2/4] 抽音频 → [3/4] ASR → [4/4] 章节
- landing 输入框 enable，提交后展示 spinner + 进度

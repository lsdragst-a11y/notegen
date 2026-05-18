"""一次性 smoke test：加载 Randeng-Pegasus-238M-Summary-Chinese 并跑官方示例。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch
from transformers import PegasusForConditionalGeneration
from tokenizers_pegasus import PegasusTokenizer

MODEL_DIR = ROOT / "models" / "Randeng-Pegasus-238M-Summary-Chinese"
device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.float16 if device == "cuda" else torch.float32

print(f"device={device}, dtype={dtype}")
print("loading tokenizer ...")
tokenizer = PegasusTokenizer.from_pretrained(str(MODEL_DIR))
print("loading model ...")
model = PegasusForConditionalGeneration.from_pretrained(
    str(MODEL_DIR), torch_dtype=dtype
).to(device)
model.eval()

text = (
    "在北京冬奥会自由式滑雪女子坡面障碍技巧决赛中，中国选手谷爱凌夺得银牌。祝贺谷爱凌！"
    "今天上午，自由式滑雪女子坡面障碍技巧决赛举行。决赛分三轮进行，取选手最佳成绩排名决出奖牌。"
    "第一跳，中国选手谷爱凌获得69.90分。在12位选手中排名第三。完成动作后，谷爱凌又扮了个鬼脸，甚是可爱。"
    "第二轮中，谷爱凌在道具区第三个障碍处失误，落地时摔倒。获得16.98分。网友：摔倒了也没关系，继续加油！"
    "在第二跳失误摔倒的情况下，谷爱凌顶住压力，第三跳稳稳发挥，流畅落地！获得86.23分！"
    "此轮比赛，共12位选手参赛，谷爱凌第10位出场。网友：看比赛时我比谷爱凌紧张，加油！"
)
inputs = tokenizer(text, max_length=1024, return_tensors="pt").to(device)
with torch.no_grad():
    out = model.generate(inputs["input_ids"], max_length=64, num_beams=4)
print("summary:", tokenizer.batch_decode(out, skip_special_tokens=True)[0])

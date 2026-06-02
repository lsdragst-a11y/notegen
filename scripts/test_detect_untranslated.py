"""Offline pure-function test for the translate-language validation fix.
No GPU / no model load. Verifies _detect_untranslated catches the CJK-leak
signatures (p80 ch0 partial leak, p46/GPU-vlog full Chinese echo) for zh->en
and the symmetric un-translated-English case for en->zh.
Run: .venv/Scripts/python.exe scripts/test_detect_untranslated.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import segment_llm as S

FAILS = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + " : " + msg)
    if not cond:
        FAILS.append(msg)

# ---- zh->en: any CJK in the English output is a leak ----
en_out = [
    "TCP connection management and termination",          # clean
    "TCP connection management and挥手过程termination",   # p80 ch0 partial leak
    "IPv4分组与IP首部",                                    # p46 full echo (no translation)
    "Process state transitions",                          # clean
    "Oyster shrimp,包容 heart, and price",                # BV1q6 partial leak
]
bad = S._detect_untranslated(en_out, "en")
check(bad == [1, 2, 4], f"zh->en flags exactly the leaked indices, got {bad}")

# acronyms-only english must stay clean (no false positive on TCP/ACK/MSL/RTT)
check(S._detect_untranslated(["ACK/SYN/FIN flag bits", "RTT and 2MSL wait"], "en") == [],
      "zh->en does not false-flag acronym-bearing clean english")

# ---- en->zh: a non-empty output with zero CJK means it was not translated ----
zh_out = [
    "TCP 连接管理与四次挥手",   # clean (has CJK)
    "Process state transitions",  # not translated (pure english)
    "RTT 与 2MSL 等待",          # clean
]
bad_zh = S._detect_untranslated(zh_out, "zh")
check(bad_zh == [1], f"en->zh flags the un-translated english entry, got {bad_zh}")

# ---- empties never flagged (treated as 'no translation', not a leak) ----
check(S._detect_untranslated(["", "  "], "en") == [], "empty strings not flagged (en)")
check(S._detect_untranslated(["", "  "], "zh") == [], "empty strings not flagged (zh)")

# ---- unsupported target language: no validation ----
check(S._detect_untranslated(["whatever 任意"], "fr") == [], "unsupported tgt returns no flags")

print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAIL"))
sys.exit(1 if FAILS else 0)

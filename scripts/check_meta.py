"""检查候选视频的 metadata，判断是否符合 benchmark 选片标准。"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.download import fetch_metadata

URLS = [
    'https://www.bilibili.com/video/BV1zmR9BHE3H',
    'https://www.bilibili.com/video/BV1YE411D7nH?p=37',
    'https://www.bilibili.com/video/BV1L24y1i7v3',
    'https://www.bilibili.com/video/BV1Xt421t7aP',
]

for u in URLS:
    try:
        m = fetch_metadata(u)
        dur = int(m.get('duration') or 0)
        bv = u.split('/')[-1].split('?')[0]
        suffix = ''
        if 'p=' in u: suffix = ' p' + u.split('p=')[1].split('&')[0]
        mins, secs = divmod(dur, 60)
        verdict = 'OK' if 8*60 <= dur <= 25*60 else ('SHORT' if dur < 8*60 else 'LONG')
        print(f'{bv}{suffix}')
        print(f'  duration: {mins}m{secs:02}s  [{verdict}]')
        print(f'  uploader: {m.get("uploader","?")}')
        print(f'  title:    {(m.get("title") or "?")[:90]}')
        desc = (m.get('description') or '').strip().replace('\n', ' ')
        if desc:
            print(f'  desc:     {desc[:120]}')
        print()
    except Exception as e:
        print(f'{u}: FAIL {e!r}')

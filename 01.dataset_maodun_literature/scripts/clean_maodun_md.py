#!/usr/bin/env python3
"""
清理茅盾奖数字化 .md：去除书首书尾出版信息、盗版推广、目录页与独立插图行，
保留小说正文，输出到 02_clean_digit。

用法:
  python clean_maodun_md.py
  python clean_maodun_md.py --raw /path/to/01_raw_digit --out /path/to/02_clean_digit
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# --- 盗版 / 推广 / 非正文行（全文删除匹配行）---
PROMO_PATTERNS = [
    r"周读",
    r"ireadweek\.com",
    r"2338856113",
    r"幸福的味道",
    r"一种思路",
    r"行行[\"']?整理",
    r"本书仅供个人学习",
    r"请勿用于商业用途",
    r"请加小编QQ",
    r"微信公众号",
    r"小编也和结交",
    r"免费电子书",
    r"如果你对本书有兴趣，请购买正版",
    r"任何对本书籍的修改",
    r"书单",
    r"豆瓣.*当当.*亚马逊.*排行榜",
    r"如果你不知道读什么书",
    r"关注这个微信公众号",
]
PROMO_COMPILED = [re.compile(p, re.I) for p in PROMO_PATTERNS]

# 书尾常见非正文
BACK_MATTER_HEADERS = re.compile(
    r"^#\s*(后记|附录|致谢|出版说明|编者的话|参考文献|主要人物表)\s*$"
)

# 元数据标题：若其后无足够正文则跳过
SKIP_HEADER_HINTS = (
    "目录",
    "目 录",
    "总 目 录",
    "版权信息",
    "图书在版编目",
    "CIP",
    "文前辅文",
    "最新长篇小说",
    "长篇小说",
    "茅盾文学奖获奖作品",  # 仅作横幅时其后常是简介
    "与一个民族的秘史",  # 《北上》等封面宣传语
)

CIP_START = re.compile(r"图书在版编目|图书在版编目（CIP）|#?\s*版权信息")
CIP_LINE = re.compile(
    r"ISBN|责任编辑|出版发行|人民文学出版社|上海文化出版社|作家出版社|"
    r"印刷|经销|开本|印张|字数|印次|版次|定价|书号|邮购|网址|http",
    re.I,
)


def strip_cip_blocks(lines: list[str]) -> list[str]:
    """删除 CIP / 版权块（从触发行到「如有印装」或连续纯出版信息行结束）。"""
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if CIP_START.search(line) or (
            i < 80 and CIP_LINE.search(line) and len(line) < 200
        ):
            # 吞掉整个块直到明显结束
            j = i + 1
            while j < n and j < i + 45:
                t = lines[j]
                if "如有印装" in t or "请与本社" in t:
                    j += 1
                    break
                if t.strip() == "" and j > i + 3:
                    # 空行且已吞了一些行，检查下一行是否仍是 CIP
                    if j + 1 < n and not CIP_LINE.search(lines[j + 1]):
                        j += 1
                        break
                j += 1
            i = j
            continue
        out.append(line)
        i += 1
    return out


def remove_promo_lines(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        if any(p.search(line) for p in PROMO_COMPILED):
            continue
        out.append(line)
    return out


def is_standalone_image(line: str) -> bool:
    s = line.strip()
    return bool(re.match(r"^!\[.*?\]\([^)]+\)\s*$", s))


def is_toc_digit_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if re.match(r"^\d+$", s):
        return True
    if re.match(r"^[\d\s]+$", s) and len(s) <= 12:
        return True
    return False


def prose_volume_after(
    lines: list[str], header_idx: int, look: int = 45
) -> tuple[int, int]:
    """
    从 header 下一行起统计「正文量」：非空、非插图、非纯数字行的汉字文本长度。
    返回 (score, next_index_if_toc_digit_run)。
    """
    total = 0
    i = header_idx + 1
    digit_run = 0
    while i < len(lines) and i < header_idx + 1 + look:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if is_standalone_image(s):
            i += 1
            continue
        if re.match(r"^\d+$", s):
            digit_run += 1
            i += 1
            continue
        digit_run = 0
        if s.startswith("#"):
            if re.match(r"^#\s*\d+\s*$", s):
                i += 1
                continue
            # 「# 1 正月十七」类小节题
            if re.match(r"^#\s*\d{1,3}\s+[\u4e00-\u9fff]", s):
                i += 1
                continue
            break
        if re.match(r"^[\d\s\.]{1,15}$", s) and len(s) < 16:
            i += 1
            continue
        total += len(s)
        i += 1
    return total, digit_run


def header_looks_skippable(title: str) -> bool:
    t = title.strip().lstrip("#").strip()
    for hint in SKIP_HEADER_HINTS:
        if hint in t and len(t) < 40:
            return True
    if re.match(r"^第\s*\d*\s*章\s*$", t) and len(t) < 12:
        return True
    return False


def is_fragmented_toc_after(lines: list[str], header_idx: int) -> bool:
    """章题后大量极短行（单字、页码、目录碎片），视为目录页而非正文。"""
    non_empty = 0
    short_cnt = 0
    for j in range(header_idx + 1, min(header_idx + 1 + 45, len(lines))):
        s = lines[j].strip()
        if not s:
            continue
        if s.startswith("#"):
            break
        if is_standalone_image(s):
            continue
        non_empty += 1
        if len(s) <= 10:
            short_cnt += 1
    if non_empty < 10:
        return False
    return short_cnt / non_empty >= 0.55


def is_author_bio_header(lines: list[str], idx: int) -> bool:
    """# 李洱 等短标题 + 作者简介。"""
    t = lines[idx].strip().lstrip("#").strip()
    if len(t) > 10:
        return False
    chunk = "\n".join(lines[idx : idx + 30])
    hits = sum(
        1
        for k in ("生于", "年毕业于", "著有", "代表作", "现任职于")
        if k in chunk
    )
    return hits >= 2


def find_body_start(lines: list[str]) -> int:
    """找到正文起始行索引（含章节标题行）。"""
    n = len(lines)

    # 1) 优先：「1.章节名」电子版常见正文起点（如《应物兄》）
    for i in range(n):
        s = lines[i].strip()
        if re.match(r"^#\s*\d+[\.、]\s*\S", s):
            if is_fragmented_toc_after(lines, i):
                continue
            sc, _ = prose_volume_after(lines, i)
            if sc >= 100:
                return i

    # 1b) 文前「序曲/楔子」等（如《牵风记》「演奏终了之后的序曲」在「第一章」之前）
    for i in range(n):
        s = lines[i].strip()
        if not s.startswith("#"):
            continue
        if not re.search(r"(序曲|楔子|引子)", s):
            continue
        if is_fragmented_toc_after(lines, i):
            continue
        sc, _ = prose_volume_after(lines, i)
        if sc >= 120:
            return i

    # 2) 「第×章」且非页码目录（如《回响》首段目录后紧跟 1-10）
    for i in range(n):
        s = lines[i].strip()
        if not re.match(r"^#\s*第[一二三四五六七八九十百零0-9]+章", s):
            continue
        j = i + 1
        dr = 0
        while j < n and j < i + 30:
            t = lines[j].strip()
            if not t:
                j += 1
                continue
            if re.match(r"^\d+$", t):
                dr += 1
                j += 1
                continue
            break
        if dr >= 8:
            continue
        if is_fragmented_toc_after(lines, i):
            continue
        sc, _ = prose_volume_after(lines, i)
        if sc >= 120:
            return i

    # 3) 其余 # 标题：排除目录碎片、作者简介
    for i in range(n):
        raw = lines[i]
        s = raw.strip()
        if not s.startswith("#"):
            continue
        title = s
        if header_looks_skippable(title):
            continue
        if is_author_bio_header(lines, i):
            continue
        if is_fragmented_toc_after(lines, i):
            continue

        score, _ = prose_volume_after(lines, i)
        j = i + 1
        dr = 0
        while j < n and j < i + 25:
            t = lines[j].strip()
            if not t:
                j += 1
                continue
            if re.match(r"^\d+$", t):
                dr += 1
                j += 1
                continue
            break
        if dr >= 8:
            continue

        if score >= 180:
            return i

        if score >= 90 and len(title) < 80:
            return i

    # 4) 回退：第一个较长叙事段
    for i in range(n):
        s = lines[i].strip()
        if len(s) >= 120 and re.search(r"[\u4e00-\u9fff]{20,}", s):
            return i
    return 0


def find_body_end(lines: list[str], start: int) -> int:
    """从 start 起，截断于 后记/附录 或尾部推广。"""
    n = len(lines)
    end = n
    for i in range(start, n):
        s = lines[i].strip()
        if BACK_MATTER_HEADERS.match(s):
            end = i
            break
        if any(p.search(s) for p in PROMO_COMPILED):
            end = i
            break
    # 尾部再扫一遍纯推广（人世间类重复页）
    while end > start:
        tail = lines[end - 1].strip()
        if not tail:
            end -= 1
            continue
        if any(p.search(tail) for p in PROMO_COMPILED):
            end -= 1
            continue
        break
    return end


def strip_images(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not is_standalone_image(ln)]


def collapse_blank(lines: list[str], max_blank: int = 2) -> list[str]:
    out: list[str] = []
    blank = 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank <= max_blank:
                out.append("")
        else:
            blank = 0
            out.append(ln.rstrip())
    while out and not out[-1].strip():
        out.pop()
    return out


def clean_text(text: str) -> str:
    lines = text.splitlines()
    lines = strip_cip_blocks(lines)
    lines = remove_promo_lines(lines)
    start = find_body_start(lines)
    end = find_body_end(lines, start)
    body = lines[start:end]
    body = remove_promo_lines(body)
    body = strip_images(body)
    body = collapse_blank(body)
    return "\n".join(body) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="清理茅盾奖 raw .md 正文")
    ap.add_argument(
        "--raw",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "01_raw_digit",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "02_clean_digit",
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    md_files = sorted(args.raw.glob("*.md"))
    if not md_files:
        print(f"未找到 .md: {args.raw}")
        return

    for path in md_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        cleaned = clean_text(text)
        out_path = args.out / path.name
        out_path.write_text(cleaned, encoding="utf-8")
        n_in = len(text.splitlines())
        n_out = len(cleaned.splitlines())
        print(f"{path.name}: {n_in} -> {n_out} 行 -> {out_path}")

    print("完成。")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
从茅盾奖清洗后的 .md 中抽取含「精神」的句、段，导出 CSV / JSONL / HTML。
默认输入：01.dataset_maodun_literature/02_clean_digit
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

TARGET = "精神"
CATEGORY = "文学-茅盾文学奖"

# 篇章标题行：行首 # 数量表示层级（兼容仅使用 # 的正文）
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def parse_book_meta(stem: str) -> tuple[str, str]:
    """
    文件名形如 2019-人世间-梁晓声 或 2023-千里江山图-孙甘露
    返回 (book_id, 书名用于「出处」)
    """
    stem = stem.strip()
    m = re.match(r"^(\d{4})-(.+)-(.+)$", stem)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", m.group(2).strip()
    return stem, stem


def classify_heading(text: str) -> str:
    """粗分类，用于更新 part/chapter/section 上下文。"""
    t = text.strip()
    if re.search(r"第[一二三四五六七八九十百零\d]+章", t):
        return "chapter"
    if "部" in t and len(t) <= 40:
        return "part"
    if re.match(r"^[一二三四五六七八九十百千零]+[、．．]", t):
        return "section"
    if re.match(r"^\d+(\s|$)", t) or re.fullmatch(r"\d+", t):
        return "subsection"
    if len(t) <= 4 and re.fullmatch(r"[\u4e00-\u9fff·]+", t):
        return "author_or_short"  # 如「刘亮程」「李洱」
    return "other"


@dataclass
class HeadingContext:
    part: str = ""
    chapter: str = ""
    section: str = ""
    subsection: str = ""

    def update(self, title: str, kind: str) -> None:
        t = title.strip()
        if kind == "author_or_short":
            return
        if kind == "part":
            self.part = t
            return
        if kind == "chapter":
            self.chapter = t
            self.section = ""
            self.subsection = ""
            return
        if kind == "section":
            self.section = t
            self.subsection = ""
            return
        if kind == "subsection":
            self.subsection = t
            return
        if kind == "other":
            # 无「第×章」时的卷首标题、序曲等：仅当尚未有 chapter 时写入，避免覆盖后文篇章
            if not self.chapter:
                self.chapter = t

    def combined(self) -> str:
        parts = [x for x in (self.part, self.chapter, self.section, self.subsection) if x]
        return " > ".join(parts) if parts else ""


def split_sentences(text: str) -> list[str]:
    """
    中文句切分：在。！？… 后断开；省略号与引号场景不追求完美，后续可换 jieba 分句。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    # 按句末标点切分，保留分隔符在前一句末尾
    raw = re.split(r"(?<=[。！？…])", text)
    out: list[str] = []
    for seg in raw:
        s = seg.strip()
        if s:
            out.append(s)
    # 无句末标点的残余作为一句
    if not out and text:
        return [text]
    return out


def find_target_spans(sentence: str, needle: str = TARGET) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        i = sentence.find(needle, start)
        if i < 0:
            break
        spans.append((i, i + len(needle)))
        start = i + len(needle)
    return spans


def highlight_html(text: str, needle: str = TARGET) -> str:
    """将 text 中所有 needle 用 <mark> 包裹（HTML 转义后）。"""
    if needle not in text:
        return html.escape(text)
    parts: list[str] = []
    last = 0
    for a, b in find_target_spans(text, needle):
        parts.append(html.escape(text[last:a]))
        parts.append(f"<mark>{html.escape(needle)}</mark>")
        last = b
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def extract_file(md_path: Path, book_id: str, 出处: str) -> list[dict]:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    rows: list[dict] = []
    global_idx = 0

    # 将生成器改为显式收集段落
    paragraphs_with_ctx: list[tuple[str, HeadingContext]] = []
    ctx = HeadingContext()
    buf: list[str] = []

    def flush_para():
        nonlocal buf
        if not buf:
            return
        para = " ".join(x.strip() for x in buf if x.strip())
        buf = []
        if para:
            paragraphs_with_ctx.append((para, replace(ctx)))

    for line in lines:
        raw = line.rstrip("\n")
        m = HEADING_RE.match(raw.strip())
        if m:
            flush_para()
            title = m.group(2).strip()
            kind = classify_heading(title)
            ctx.update(title, kind)
            continue
        if not raw.strip():
            flush_para()
            continue
        buf.append(raw)
    flush_para()

    for paragraph, pctx in paragraphs_with_ctx:
        if TARGET not in paragraph:
            continue
        sentences = split_sentences(paragraph)
        hit_indices = [i for i, s in enumerate(sentences) if TARGET in s]
        n_hit = len(hit_indices)

        for sent_idx, sentence in enumerate(sentences):
            if TARGET not in sentence:
                continue
            spans = find_target_spans(sentence)
            n_span = len(spans)
            prev_s = sentences[sent_idx - 1] if sent_idx > 0 else ""
            next_s = sentences[sent_idx + 1] if sent_idx + 1 < len(sentences) else ""

            for occ_i, _span in enumerate(spans, start=1):
                global_idx += 1
                instance_id = f"{book_id}_{global_idx:06d}"
                rows.append(
                    {
                        "instance_id": instance_id,
                        "category": CATEGORY,
                        "出处": 出处,
                        "book_id": book_id,
                        "source_path": str(md_path.resolve()),
                        "篇章_part": pctx.part,
                        "篇章_chapter": pctx.chapter,
                        "篇章_section": pctx.section,
                        "篇章_subsection": pctx.subsection,
                        "篇章_combined": pctx.combined(),
                        "paragraph": paragraph,
                        "sentence": sentence,
                        "sentence_highlight_html": highlight_html(sentence),
                        "paragraph_highlight_html": highlight_html(paragraph),
                        "精神_句内次序": occ_i,
                        "精神_句内出现次数": n_span,
                        "句在段中序号": sent_idx + 1,
                        "段内含精神句数": n_hit,
                        "prev_sentence": prev_s,
                        "next_sentence": next_s,
                        "sense_label": "",
                    }
                )

    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("\ufeff", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_jsonl(rows: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_html(rows: list[dict], path: Path) -> None:
    thead = """
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:system-ui,sans-serif;font-size:14px;">
    <thead><tr>
    <th>instance_id</th><th>出处</th><th>篇章_combined</th><th>sentence_highlight</th><th>paragraph_highlight</th>
    </tr></thead><tbody>
    """
    parts = [thead]
    for r in rows:
        parts.append("<tr>")
        for key in ["instance_id", "出处", "篇章_combined"]:
            parts.append(f"<td>{html.escape(str(r.get(key,'')))}</td>")
        parts.append(f"<td>{r.get('sentence_highlight_html','')}</td>")
        parts.append(f"<td style='max-width:480px;'>{r.get('paragraph_highlight_html','')}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>精神抽取</title>
    <style>mark {{ background: #ffeb3b; }}</style></head><body>
    <p>共 {len(rows)} 条（含「精神」的每次出现一行）</p>
    {''.join(parts)}
    </body></html>"""
    path.write_text(doc, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="抽取含「精神」的句、段")
    ap.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "01.dataset_maodun_literature"
        / "02_clean_digit",
        help="清洗后的 .md 目录",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "output",
        help="输出目录",
    )
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    md_files = sorted(args.input_dir.glob("*.md"))
    if not md_files:
        print(f"未找到 .md: {args.input_dir}")
        return

    all_rows: list[dict] = []
    for md in md_files:
        book_id, 出处 = parse_book_meta(md.stem)
        rows = extract_file(md, book_id, 出处)
        all_rows.extend(rows)
        print(f"{md.name}: {len(rows)} 条")

    csv_path = args.output_dir / "jingshen_extracts.csv"
    jsonl_path = args.output_dir / "jingshen_extracts.jsonl"
    html_path = args.output_dir / "jingshen_extracts_preview.html"

    write_csv(all_rows, csv_path)
    write_jsonl(all_rows, jsonl_path)
    write_html(all_rows, html_path)

    print(f"合计: {len(all_rows)} 条")
    print(f"CSV: {csv_path}")
    print(f"JSONL: {jsonl_path}")
    print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()

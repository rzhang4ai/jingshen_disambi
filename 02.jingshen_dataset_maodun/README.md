# Step 2：「精神」抽句归段

## 目的

从茅盾奖清洗文本（`01.dataset_maodun_literature/02_clean_digit`）中抽取所有包含目标词 **「精神」** 的句子与所在段落，导出为结构化表格（CSV / JSONL），并生成带 `<mark>` 高亮的 HTML 预览。

## 脚本

- **`build_jingshen_dataset.py`**：主程序，无第三方依赖（仅 Python 3.10+ 标准库）。

## 逻辑说明

### 1. 输入与书目元数据

- 默认读取 `--input-dir` 下所有 `.md` 文件（通常为清洗后的正文）。
- 从文件名解析 **book_id** 与 **出处（书名）**：模式 `YYYY-{书名}-{作者}.md`，例如 `2019-人世间-梁晓声.md` → 出处 `人世间`，book_id `2019-人世间-梁晓声`。文件名首尾空格会去掉。

### 2. 篇章结构（溯源）

- 按 Markdown **标题行**解析：`^#{1,6}\s+标题`。
- 标题粗分类：
  - **chapter**：含「第…章」。
  - **part**：含「部」且较短（如「上部 搬家家」）。
  - **section**：以中文数字+顿号开头（如「一、童年」）。
  - **subsection**：以阿拉伯数字开头或纯数字（如「# 1」「# 1 正月十七」）。
  - **author_or_short**：仅 1～4 个汉字（如作者名「刘亮程」），**不**更新篇章上下文。
  - **other**：其余；仅在当前还**没有** `chapter` 时写入 `chapter`（用于序曲等无「第×章」的开篇），避免覆盖后文正式章题。
- `HeadingContext` 维护 `part / chapter / section / subsection`，合成一列 **篇章_combined**（` > ` 连接非空项）。

### 3. 段落与句子

- **段落**：以**空行**分隔；标题行不进入段落正文，但在进入正文前会更新篇章上下文。
- 每个段落 flush 时，对当时的 `HeadingContext` 做 **快照**（`dataclasses.replace`），保证该段对应正确的篇章信息，不受后续标题影响。
- **句切分**：在 `。！？…` 等句末标点后切分；无句末标点的残余合并为一句。对话体、引号内标点不单独优化（可后续换 `jieba` 或规则增强）。

### 4. 「精神」命中与一行一条

- 仅处理 **段落内包含「精神」** 的段落。
- 先得到句列表，再筛出含「精神」的句子。
- **同一句内「精神」出现多次**：每个出现单独一行，`精神_句内次序` 为 1、2、…，`精神_句内出现次数` 为句内总次数。
- **同一段多句含「精神」**：每句（每个出现）各一行；**段落**列重复完整段落文本；**段内含精神句数**为该段中含「精神」的句子个数；**句在段中序号**为该句在段内句列表中的 1-based 索引。
- **前句 / 后句**：便于后续窗口特征或人工复核。

### 5. 高亮

- **sentence_highlight_html** / **paragraph_highlight_html**：将文中所有「精神」替换为 `<mark>精神</mark>`，其余文本 HTML 转义。CSV 中存字符串；浏览器打开 HTML 预览可见黄色高亮。

### 6. 输出文件（默认 `--output-dir=output`）

| 文件 | 说明 |
|------|------|
| `jingshen_extracts.csv` | UTF-8 BOM，便于 Excel 打开 |
| `jingshen_extracts.jsonl` | 每行一条 JSON，便于程序消费 |
| `jingshen_extracts_preview.html` | 精简列预览 + 高亮 |

### 7. 字段列表

| 字段 | 含义 |
|------|------|
| instance_id | 全书内递增编号：`{book_id}_{6位序号}` |
| category | 固定：`文学-茅盾文学奖` |
| 出处 | 书名（来自文件名） |
| book_id | 文件名主体（含年-书名-作者） |
| source_path | 绝对路径 |
| 篇章_part / 篇章_chapter / 篇章_section / 篇章_subsection | 结构化篇章 |
| 篇章_combined | 合并面包屑 |
| paragraph | 原段全文 |
| sentence | 原句全文 |
| sentence_highlight_html | 句高亮 HTML |
| paragraph_highlight_html | 段高亮 HTML |
| 精神_句内次序 | 该句内第几个「精神」 |
| 精神_句内出现次数 | 该句内「精神」共几次 |
| 句在段中序号 | 该句在段内第几句 |
| 段内含精神句数 | 该段含「精神」的句子数 |
| prev_sentence / next_sentence | 邻句 |
| sense_label | 预留，供后续人工或模型标注 |

### 8. 已知局限

- 句切分对复杂引号、省略号嵌套可能偏差。
- 某部作品正文中若无「精神」（如当前《本巴》清洗本），则条数为 0。
- 篇章解析依赖 `#` 标题；无标题长段仅 `篇章_combined` 可能为空。

## 运行方式

在项目目录下（已激活 `jingshen_wsd` 亦可，脚本不依赖 conda 包）：

```bash
cd /Users/rzhang/Documents/03.CBS5502/jingshen_disambi/02.jingshen_dataset_maodun
python build_jingshen_dataset.py
```

自定义输入/输出：

```bash
python build_jingshen_dataset.py --input-dir /path/to/02_clean_digit --output-dir /path/to/output
```

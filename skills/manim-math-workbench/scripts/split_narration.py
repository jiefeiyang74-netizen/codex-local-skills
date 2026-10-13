#!/usr/bin/env python3
"""Lossless UTF-8 narration splitter; standard library only."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def count_chars(text):
    normalized = re.sub(r'(?<!\r)\n', '\r\n', text)
    return len(normalized.encode('utf-16-le')) // 2


def safe_positions(text, pattern):
    # Never split inside explicit math, code, or paired delimiters.
    protected = [(m.start(), m.end()) for m in re.finditer(
        r'\$\$[\s\S]*?\$\$|\$[^$]*\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|`[^`]*`', text)]
    stack = []
    pairs = {'(': ')', '[': ']', '{': '}', '（': '）', '【': '】'}
    for i, char in enumerate(text):
        if char in pairs:
            stack.append((i, pairs[char]))
        elif stack and char == stack[-1][1]:
            start, _ = stack.pop()
            protected.append((start, i + 1))
    protected.extend((start, len(text)) for start, _ in stack)
    return [m.end() for m in re.finditer(pattern, text)
            if not any(a < m.end() < b for a, b in protected)]


def split_text(text, limit=500):
    if limit < 1 or not text:
        raise ValueError('原文不能为空，字符上限必须为正数')
    if count_chars(text) <= limit:
        return [text]
    headings = [m.start() for m in re.finditer(
        r'(?m)^(?:[ \t]*)(?:第[一二三四五六七八九十百零〇0-9]+[题章节部分]|(?:题型|模型)[一二三四五六七八九十0-9]+)', text)]
    # Intro belongs to the first section; outro remains in the last section.
    cuts = [0] + headings[1:] + [len(text)] if headings else [0, len(text)]
    chunks = []

    def fit(section, level=0):
        if count_chars(section) <= limit:
            return [section]
        patterns = [r'(?:\r?\n[ \t]*){2,}', r'\r?\n',
                    r'[。！？!?；;][”’"\']*(?:[ \t]*(?:\r?\n)?)|(?<!\d)\.(?=\s|$)[ \t]*(?:\r?\n)?']
        if level == len(patterns):
            raise ValueError('单句或公式超过上限且无安全切分边界；请人工确认改稿，未输出分段')
        points = [0] + safe_positions(section, patterns[level])
        if points[-1] != len(section):
            points.append(len(section))
        parts = []
        for a, b in zip(points, points[1:]):
            if b > a:
                parts.extend(fit(section[a:b], level + 1))
        packed = []
        for part in parts:
            if packed and count_chars(packed[-1] + part) <= limit:
                packed[-1] += part
            else:
                packed.append(part)
        return packed

    for a, b in zip(cuts, cuts[1:]):
        chunks.extend(fit(text[a:b]))
    assert ''.join(chunks) == text
    assert all(count_chars(c) <= limit for c in chunks)
    return chunks


def generate(input_path, output_dir, limit=500):
    raw = Path(input_path).read_bytes()
    text = raw.decode('utf-8')  # Preserve BOM, line endings, and every source character.
    chunks = split_text(text, limit)
    files = {}
    entries = []
    markdown = ['# 剪映录音稿分段\n\n标题和字符数不在复制块内；精确保留换行及末尾空白请使用对应 TXT。\n\n']
    for i, chunk in enumerate(chunks, 1):
        name = f'{i:02d}.txt'
        files[name] = chunk.encode('utf-8')
        entries.append({'index': i, 'file': name, 'chars': count_chars(chunk)})
        fence = '`' * max(3, 1 + max((len(m.group()) for m in re.finditer(r'`+', chunk)), default=0))
        markdown.append(f'## 第{i}段/共{len(chunks)}段（{count_chars(chunk)}字符）\n\n{fence}text\n'
                        + chunk + ('' if chunk.endswith('\n') else '\n') + fence + '\n\n')
    files['复制用.md'] = ''.join(markdown).encode('utf-8')
    manifest = {'source': str(Path(input_path).resolve()), 'source_sha256': hashlib.sha256(raw).hexdigest(),
                'max_chars': limit, 'counting': 'UTF-16 code units; lone LF counted as CRLF',
                'concatenation_equals_source': ''.join(chunks) == text,
                'concatenation_bytes_equal_source': b''.join(files[e['file']] for e in entries) == raw,
                'chunks': entries}
    files['清单.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    target = Path(output_dir)
    # Validate the entire result and all conflicts before creating any output.
    if target.exists():
        if not target.is_dir():
            raise ValueError('输出路径不是目录')
        if any(p.name not in files or not p.is_file() or p.read_bytes() != files[p.name]
               for p in target.iterdir()):
            raise ValueError('输出目录已有不同内容，拒绝覆盖')
    target.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = target / name
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(data)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--max-chars', type=int, default=500)
    args = parser.parse_args()
    try:
        result = generate(args.input, args.output_dir, args.max_chars)
    except (ValueError, OSError, UnicodeError) as exc:
        parser.exit(1, f'分段失败：{exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

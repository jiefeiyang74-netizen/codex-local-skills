"""Explicit math-label readings; text provenance only, never audio timestamps."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata


def token_char(char):
    # Chinese prose may directly surround labels; Latin words/subscripts may not.
    return (char == '_' or char.isdigit() or
            'LATIN' in unicodedata.name(char, '') or
            unicodedata.category(char).startswith('M'))


def complete_token(text, start, end):
    return ((start == 0 or not token_char(text[start - 1])) and
            (end == len(text) or not token_char(text[end])))


def prepare(text, spec):
    """Return spoken text and lossless, monotonic code-point span mapping.

    Exactly one mode: {"labels": {label: reading}} or
    {"spans": [{"start": int, "end": int, "label": str, "reading": str}]}.
    A dictionary explicitly marks every complete occurrence of its keys.
    """
    if not isinstance(spec, dict) or set(spec) not in ({'labels'}, {'spans'}):
        raise ValueError('Specify exactly labels or spans')
    replacements = []
    if 'labels' in spec:
        labels = spec['labels']
        if not isinstance(labels, dict):
            raise ValueError('labels must be an object')
        for label, reading in labels.items():
            check_reading(label, reading)
        if labels:
            pattern = '|'.join(re.escape(k) for k in sorted(labels, key=len, reverse=True))
            for match in re.finditer(pattern, text):
                if complete_token(text, match.start(), match.end()):
                    replacements.append((match.start(), match.end(), labels[match.group()]))
    else:
        if not isinstance(spec['spans'], list):
            raise ValueError('spans must be an array')
        for span in spec['spans']:
            if not isinstance(span, dict) or set(span) != {'start', 'end', 'label', 'reading'}:
                raise ValueError('Each span requires start, end, label, reading')
            start, end = span['start'], span['end']
            check_reading(span['label'], span['reading'])
            if (type(start) is not int or type(end) is not int or
                    not 0 <= start < end <= len(text)):
                raise ValueError('Invalid code-point span')
            if text[start:end] != span['label'] or not complete_token(text, start, end):
                raise ValueError('Span must match a complete label')
            replacements.append((start, end, span['reading']))
        replacements.sort()
    previous = 0
    for start, end, _ in replacements:
        if start < previous:
            raise ValueError('Overlapping spans')
        previous = end

    segments, parts = [], []
    source_cursor = spoken_cursor = 0

    def append(start, end, reading, kind):
        nonlocal spoken_cursor
        if start == end:
            return
        segments.append({'display_span': [start, end],
                         'spoken_span': [spoken_cursor, spoken_cursor + len(reading)],
                         'display_text': text[start:end], 'spoken_text': reading,
                         'kind': kind})
        parts.append(reading)
        spoken_cursor += len(reading)

    for start, end, reading in replacements:
        append(source_cursor, start, text[source_cursor:start], 'identity')
        append(start, end, reading, 'label')
        source_cursor = end
    append(source_cursor, len(text), text[source_cursor:], 'identity')
    spoken = ''.join(parts)
    digest = lambda value: hashlib.sha256(value.encode('utf-8')).hexdigest()
    return spoken, {'schema': 'tts-readings-1', 'offset_unit': 'unicode_code_point',
                    'range_convention': 'half_open', 'timing_source': None,
                    'display_sha256': digest(text), 'spoken_sha256': digest(spoken),
                    'display_length': len(text), 'spoken_length': len(spoken),
                    'spec': spec, 'segments': segments}


def check_reading(label, reading):
    if not isinstance(label, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', label):
        raise ValueError('Labels must be ASCII math identifiers, e.g. P, PQ, x_1')
    if not isinstance(reading, str) or not reading.strip():
        raise ValueError('Reading must be a nonempty string')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--readings', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        # Decode bytes directly: preserve CRLF, BOM, combining marks and whitespace.
        text = args.input.read_bytes().decode('utf-8')
        spec = json.loads(args.readings.read_text(encoding='utf-8-sig'),
                          object_pairs_hook=unique_object)
        spoken, mapping = prepare(text, spec)
        outputs = {'spoken.txt': spoken.encode('utf-8'),
                   'reading-map.json': (json.dumps(mapping, ensure_ascii=False, indent=2) + '\n').encode('utf-8')}
        for name, content in outputs.items():
            target = args.output_dir / name
            if target.resolve() in (args.input.resolve(), args.readings.resolve()):
                raise ValueError('Output must not overwrite an input')
            if target.exists() and target.read_bytes() != content:
                raise ValueError('Different output already exists: ' + str(target))
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, content in outputs.items():
            target = args.output_dir / name
            if not target.exists():
                with target.open('xb') as stream:
                    stream.write(content)
    except (ValueError, OSError, UnicodeError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()

"""Attempt-local retention and ordered partial metadata; never auto-splice clips."""
import hashlib
import json
from pathlib import Path


def retain_config(folder):
    path = Path(folder) / 'retain_partials.cfg'
    path.write_text('[CLI]\nmax_files_cached = -1\nflush_cache = False\n', encoding='utf-8')
    return path


def partial_index(media_dir):
    import av
    media_dir = Path(media_dir).resolve()
    sequences = []
    for listing in sorted(media_dir.rglob('partial_movie_file_list.txt')):
        entries, offset = [], 0
        for line in listing.read_text(encoding='utf-8').splitlines():
            if not line.startswith("file 'file:") or not line.endswith("'"):
                continue
            path = Path(line[len("file 'file:"):-1]).resolve()
            if not path.is_relative_to(media_dir) or not path.is_file():
                raise RuntimeError(f'Missing/out-of-attempt partial: {path}')
            with path.open('rb') as source:
                sha = hashlib.file_digest(source, 'sha256').hexdigest()
            with av.open(str(path)) as container:
                stream = container.streams.video[0]
                count, basis = stream.frames, 'container_nb_frames; decode before reuse'
                if not count:
                    count = sum(1 for _ in container.decode(stream))
                    basis = 'decoded_frame_count'
                entry = {'sequence':len(entries), 'path':str(path), 'sha256':sha,
                         'frames':count, 'frame_count_source':basis,
                         'start_frame':offset, 'end_frame_exclusive':offset+count,
                         'fps':str(stream.average_rate), 'time_base':str(stream.time_base),
                         'dimensions':[stream.width, stream.height]}
            entries.append(entry); offset += count
        sequences.append({'directory':str(listing.parent), 'concat_list':str(listing),
                          'total_frames':offset, 'entries':entries})
    result = {'schema_version':1, 'max_files_cached':-1, 'auto_reuse':False,
              'reuse_gate':'Verify source identity, actual decoded frames/cadence and audio clock; review changed native frames/transitions; then run unchanged media validation.',
              'sequences':sequences}
    path = media_dir / 'partial_index.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return path

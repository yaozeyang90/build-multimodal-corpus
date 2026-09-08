#!/usr/bin/env python3
"""Create a clean GitHub-ready repository copy and ZIP, never including corpus data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

NAME = 'build-multimodal-corpus'
TOP = {'SKILL.md', 'README.md', 'LICENSE', '.gitignore'}
DIRS = {'references', 'agents', 'scripts', 'tests', '.github'}
SUFFIXES = {'.md', '.py', '.yaml', '.yml'}


def package(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.is_relative_to(source):
        raise ValueError('Release destination must be outside source skill')
    repo, archive = destination / NAME, destination / (NAME + '-v0.1.0.zip')
    audit = destination / 'package-audit.json'
    if any(p.exists() for p in (repo, archive, audit)):
        raise FileExistsError('Release targets already exist; use a new destination')
    entries = []
    for p in sorted(source.rglob('*')):
        rel = p.relative_to(source)
        if any(part.startswith('._') or part in {'.git', '__pycache__', '.DS_Store'} for part in rel.parts):
            continue
        if p.is_symlink():
            raise ValueError('Symlinks are not accepted for publication')
        if not p.is_file():
            continue
        included = str(rel) in TOP or (rel.parts[0] in DIRS and p.suffix in SUFFIXES)
        if not included:
            continue
        raw = p.read_bytes()
        text = raw.decode('utf-8')
        if len(raw) > 1_000_000:
            raise ValueError('Unexpectedly large code/document file: ' + str(rel))
        if re.search(r'/(?:Users|Volumes|home)/[^\s]+', text):
            raise ValueError('Private absolute path in ' + str(rel))
        if re.search(r'(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{24,}|github_pat_[A-Za-z0-9_]{24,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)', text):
            raise ValueError('Possible credential in ' + str(rel))
        entries.append((p, rel, raw))
    if not TOP <= {str(rel) for _, rel, _ in entries}:
        raise ValueError('Missing required repository files')
    repo.mkdir(parents=True)
    records = []
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for p, rel, raw in entries:
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
            z.writestr(NAME + '/' + rel.as_posix(), raw)
            records.append(dict(path=rel.as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or len(z.namelist()) != len(entries):
            raise ValueError('ZIP validation failed')
    result = dict(version='0.1.0', remote_published=False, files=records,
                  archive=archive.name, archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                  checks=['code_document_allowlist', 'no_private_absolute_paths', 'common_credential_patterns', 'zip_crc'],
                  caveat='Pattern checks do not replace human review of publication rights and secrets.')
    with audit.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    return dict(repository=str(repo), archive=str(archive), files=len(entries), audit=str(audit), remote_published=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, help='New external release directory')
    args = p.parse_args()
    print(json.dumps(package(Path(__file__).resolve().parents[1], args.out), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

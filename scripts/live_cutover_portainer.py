#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import shlex
import ssl
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT = Path('/mnt/synology-rootkeeper/projects/bkw-tariff-proxy')
SECRET = Path('/home/rootkeeper/.secrets/portainer-rootkeeper.env')
OUT_ROOT = Path('/mnt/synology-rootkeeper/reports/bkw-tariff-proxy/live-cutover')
STACK_ID = 22
ENDPOINT_ID = 2
IMAGE_TAG = 'bkw-tariff-proxy:local'
SSL_CONTEXT = ssl._create_unverified_context()

EXCLUDES = {
    '.git', '.pytest_cache', '__pycache__', '.venv', 'venv', 'dist', 'build',
    'src/bkw_tariff_proxy.egg-info',
}


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        out[k.strip()] = shlex.split(v.strip())[0] if v.strip() else ''
    return out


def request_json(method: str, url: str, token: str | None = None, body: Any = None) -> Any:
    data = None
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as r:
        raw = r.read()
        if not raw:
            return None
        return json.loads(raw.decode())


def request_bytes(method: str, url: str, token: str | None = None, body: bytes | None = None, content_type: str | None = None) -> tuple[int, bytes]:
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    if content_type:
        headers['Content-Type'] = content_type
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=300, context=SSL_CONTEXT) as r:
        return r.status, r.read()


def rel_excluded(rel: Path) -> bool:
    s = rel.as_posix()
    parts = set(rel.parts)
    if parts & EXCLUDES:
        return True
    if s.endswith('.pyc') or s.endswith('.pyo'):
        return True
    return False


def build_context() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w') as tar:
        for path in sorted(PROJECT.rglob('*')):
            rel = path.relative_to(PROJECT)
            if rel_excluded(rel):
                continue
            if path.is_file():
                tar.add(path, arcname=rel.as_posix(), recursive=False)
    buf.seek(0)
    return buf.read()


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False), encoding='utf-8')


def main() -> None:
    env = load_env(SECRET)
    base = env['PORTAINER_URL'].rstrip('/')
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = OUT_ROOT / ts
    (out / 'exports').mkdir(parents=True)
    (out / 'logs').mkdir()

    auth = request_json('POST', f'{base}/api/auth', body={'Username': env['PORTAINER_USER'], 'Password': env['PORTAINER_PASSWORD']})
    token = auth['jwt']

    status = request_json('GET', f'{base}/api/status', token)
    stack = request_json('GET', f'{base}/api/stacks/{STACK_ID}', token)
    stack_file = request_json('GET', f'{base}/api/stacks/{STACK_ID}/file', token)
    containers = request_json('GET', f'{base}/api/endpoints/{ENDPOINT_ID}/docker/containers/json?all=1', token)
    write_json(out / 'exports' / 'portainer-status-before.json', status)
    write_json(out / 'exports' / 'stack-before.json', stack)
    write_json(out / 'exports' / 'containers-before.json', containers)
    current_compose = stack_file.get('StackFileContent') or stack_file.get('stackFileContent') or ''
    (out / 'exports' / 'stack-before.yml').write_text(current_compose, encoding='utf-8')

    context = build_context()
    (out / 'logs' / 'build-context.bytes').write_text(str(len(context)), encoding='utf-8')
    build_url = f'{base}/api/endpoints/{ENDPOINT_ID}/docker/build?' + urllib.parse.urlencode({'t': IMAGE_TAG, 'dockerfile': 'Dockerfile', 'rm': '1'})
    code, raw = request_bytes('POST', build_url, token, context, 'application/x-tar')
    (out / 'logs' / 'docker-build.log').write_bytes(raw)
    if code < 200 or code >= 300:
        raise SystemExit(f'build failed HTTP {code}')
    text = raw.decode(errors='replace')
    if 'errorDetail' in text or 'error' in text.lower() and 'Successfully built' not in text:
        # Docker build streams JSON per line; keep this conservative but don't false-fail on harmless text.
        for line in text.splitlines():
            try:
                item=json.loads(line)
            except Exception:
                continue
            if 'errorDetail' in item:
                raise SystemExit(f'docker build failed: {item}')

    new_compose = current_compose.replace('      BKW_TEST_DATA_MODE: synthetic\n', '      BKW_TEST_DATA_MODE: "off"\n')
    if new_compose == current_compose:
        # In case Portainer stored a slightly different file, enforce by removing any BKW_TEST_DATA_MODE line.
        lines=[]
        removed=False
        for line in current_compose.splitlines():
            if line.strip().startswith('BKW_TEST_DATA_MODE:'):
                lines.append('      BKW_TEST_DATA_MODE: "off"')
                removed=True
            else:
                lines.append(line)
        new_compose='\n'.join(lines)+'\n'
        if not removed:
            raise SystemExit('BKW_TEST_DATA_MODE line not found in stack file')
    (out / 'exports' / 'stack-after-requested.yml').write_text(new_compose, encoding='utf-8')

    update_body = {
        'StackFileContent': new_compose,
        'Env': [],
        'Prune': True,
        'PullImage': False,
    }
    try:
        updated = request_json('PUT', f'{base}/api/stacks/{STACK_ID}?endpointId={ENDPOINT_ID}', token, update_body)
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors='replace')
        (out / 'logs' / 'stack-update-error.txt').write_text(err, encoding='utf-8')
        raise
    write_json(out / 'exports' / 'stack-update-response.json', updated)

    # Give Docker/healthcheck time to recreate.
    time.sleep(8)
    stack_after = request_json('GET', f'{base}/api/stacks/{STACK_ID}', token)
    stack_file_after = request_json('GET', f'{base}/api/stacks/{STACK_ID}/file', token)
    containers_after = request_json('GET', f'{base}/api/endpoints/{ENDPOINT_ID}/docker/containers/json?all=1', token)
    write_json(out / 'exports' / 'stack-after.json', stack_after)
    (out / 'exports' / 'stack-after.yml').write_text(stack_file_after.get('StackFileContent') or stack_file_after.get('stackFileContent') or '', encoding='utf-8')
    write_json(out / 'exports' / 'containers-after.json', containers_after)

    print(out)


if __name__ == '__main__':
    main()

"""Exercise the unmodified npm CLI in isolated local Windows/Linux test homes."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    base = os.environ['GENERIC_SMOKE_BASE_URL']
    database = os.environ['SKILLHUB_TEST_DATABASE_URL']
    assert urlsplit(base).hostname in {'127.0.0.1', 'localhost'}
    assert urlsplit(database).hostname in {'127.0.0.1', 'localhost'}
    cli = Path(os.environ['GENERIC_SMOKE_CLI']).resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix='skillhub generic verify '))
    engine = create_async_engine(database)
    token_id = None
    async with httpx.AsyncClient(base_url=base, timeout=30) as client:
        try:
            response = await client.post('/api/v1/auth/local/login', json={'username': os.environ['GENERIC_SMOKE_USERNAME'], 'password': os.environ['GENERIC_SMOKE_PASSWORD']})
            assert response.status_code == 200
            user = response.json()['data']['userId']
            async with engine.connect() as conn:
                skills = (await conn.execute(text("SELECT s.id,n.slug AS namespace,s.slug FROM skill s JOIN namespace n ON n.id=s.namespace_id WHERE s.owner_id=:user AND EXISTS(SELECT 1 FROM skill_version sv WHERE sv.skill_id=s.id AND sv.status='PUBLISHED') ORDER BY s.id LIMIT 2"), {'user': user})).mappings().all()
                before = (await conn.execute(text('SELECT COALESCE(max(id),0) FROM local_skill_download_event'))).scalar_one()
            assert len(skills) == 2
            response = await client.post('/api/v1/tokens', json={'name': 'Generic CLI local verification', 'scopes': ['skill:download'], 'expiresAt': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
            assert response.status_code == 200, response.text
            token = response.json()['data']
            token_id = token['id']
            process_env = dict(os.environ, SKILLHUB_TOKEN=token['token'])
            expected = 0
            for scope in ('user', 'project'):
                target = root / f'windows {scope}'
                target.mkdir()
                # Only child-process homes are isolated; the user's home and Agent folders are untouched.
                env = dict(process_env, HOME=str(target), USERPROFILE=str(target), GENERIC_CLI=str(cli), GENERIC_REGISTRY=base)
                directory = '$HOME/.agents/skills' if scope == 'user' else './.agents/skills'
                for skill in skills:
                    command = f'node "$env:GENERIC_CLI" install @{skill["namespace"]}/{skill["slug"]} --registry "$env:GENERIC_REGISTRY" --dir "{directory}" --force --json'
                    result = await asyncio.to_thread(subprocess.run, ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command], cwd=target, env=env, capture_output=True, text=True, timeout=60)
                    assert result.returncode == 0, (result.stdout, result.stderr)
                    installed = json.loads(result.stdout)['installed'][0]
                    assert installed['agent'] == 'custom'
                    assert Path(installed['dir']).is_relative_to(target)
                    assert (Path(installed['dir']) / 'SKILL.md').is_file()
                    expected += 1
                print(f'PASS Windows PowerShell {scope}: two official CLI installs, isolated space-containing path', flush=True)
            if os.getenv('GENERIC_SMOKE_LINUX') == '1':
                for scope in ('user', 'project'):
                    directory = '$HOME/.agents/skills' if scope == 'user' else './.agents/skills'
                    commands = ['set -eu', 'mkdir -p "/tmp/project with spaces"', 'cd "/tmp/project with spaces"']
                    for skill in skills:
                        commands.append(f'node /cli/index.js install @{skill["namespace"]}/{skill["slug"]} --registry http://skillhub-reviewer-display-server-v2:8080 --dir "{directory}" --force --json')
                    result = await asyncio.to_thread(subprocess.run, ['docker', 'run', '--rm', '--network', 'skillhub-oss-case-smoke_default', '-e', 'SKILLHUB_TOKEN', '-v', f'{cli}:/cli/index.js:ro', 'node:22-bookworm', 'bash', '-c', '\n'.join(commands)], env=process_env, capture_output=True, text=True, timeout=120)
                    assert result.returncode == 0, (result.stdout, result.stderr)
                    installs = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
                    assert len(installs) == 2
                    assert all(item['installed'][0]['agent'] == 'custom' for item in installs)
                    expected += 2
                    print(f'PASS Linux Bash {scope}: two official CLI installs', flush=True)
            # A failed independent line must not undo earlier successes or create an event.
            env = dict(process_env, HOME=str(root), USERPROFILE=str(root))
            failed = await asyncio.to_thread(subprocess.run, ['node', str(cli), 'install', '@global/generic-smoke-does-not-exist', '--registry', base, '--dir', str(root / 'failed'), '--force', '--json'], env=env, capture_output=True, text=True, timeout=60)
            assert failed.returncode != 0
            env.pop('SKILLHUB_TOKEN')
            first = skills[0]
            anonymous = await asyncio.to_thread(subprocess.run, ['node', str(cli), 'install', f'@{first["namespace"]}/{first["slug"]}', '--registry', base, '--dir', str(root / 'anonymous'), '--force', '--json'], env=env, capture_output=True, text=True, timeout=60)
            assert anonymous.returncode != 0
            async with engine.connect() as conn:
                rows = (await conn.execute(text('SELECT skill_id,user_id,source FROM local_skill_download_event WHERE id>:before AND user_id=:user'), {'before': before, 'user': user})).mappings().all()
            assert len(rows) == expected, (expected, len(rows))
            assert {row['skill_id'] for row in rows} == {skill['id'] for skill in skills}
            assert all(row['source'] == 'cli' for row in rows)
            print(f'PASS PostgreSQL tracking: {expected} successes across two skills; failed/missing-auth commands add no events. Test artifacts: {root}', flush=True)
        finally:
            if token_id:
                response = await client.delete(f'/api/v1/tokens/{token_id}')
                assert response.status_code == 204
            await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

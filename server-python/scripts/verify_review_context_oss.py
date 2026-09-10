"""Verify service-token OSS attribution and unchanged platform approval in local smoke."""
import asyncio
import io
import json
import os
import time
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    suffix = os.environ['REVIEW_SMOKE_SUFFIX']
    run = uuid4().hex[:8]
    base = os.environ['REVIEW_SMOKE_BASE_URL']
    assert urlsplit(base).hostname in {'127.0.0.1', 'localhost'}, 'Local smoke only'
    assert urlsplit(os.environ['SKILLHUB_TEST_DATABASE_URL']).hostname in {'127.0.0.1', 'localhost'}, 'Local smoke database only'
    engine = create_async_engine(os.environ['SKILLHUB_TEST_DATABASE_URL'])
    clients = {name: httpx.AsyncClient(base_url=base, timeout=60) for name in ('platform', 'publisher', 'reviewer')}
    service_token_path = None
    try:
        platform = clients['platform']
        response = await platform.post('/api/v1/auth/local/register', json={'username': f'rc_platform_{run}', 'password': 'ReviewSmoke123!', 'email': f'rc_platform_{run}@example.test'})
        assert response.status_code == 200, response.text
        platform_id = response.json()['data']['userId']
        users = {}
        for name in ('publisher', 'reviewer'):
            response = await clients[name].post('/api/v1/auth/local/login', json={'username': f'rc_{name}_{suffix}', 'password': 'ReviewSmoke123!'})
            assert response.status_code == 200, response.text
            users[name] = response.json()['data']['userId']
        async with engine.begin() as conn:
            await conn.execute(text("INSERT INTO user_role_binding(user_id,role_id) SELECT :id,id FROM role WHERE code='SUPER_ADMIN'"), {'id': platform_id})
            for name, ident in users.items():
                await conn.execute(text("INSERT INTO identity_binding(user_id,provider_code,subject,login_name,extra_json) VALUES (:id,'keycloak',:subject,:login,'{}'::jsonb) ON CONFLICT DO NOTHING"), {'id': ident, 'subject': f'rc-{name}-{suffix}', 'login': f'rc_{name}_{suffix}'})
        response = await platform.post('/api/v1/auth/local/login', json={'username': f'rc_platform_{run}', 'password': 'ReviewSmoke123!'})
        assert response.status_code == 200, response.text
        response = await platform.post('/api/v1/admin/service-principals', json={'code': f'rc-import-{run}', 'displayName': 'Review context smoke importer'})
        assert response.status_code == 200, response.text
        principal_id = response.json()['data']['id']
        response = await platform.post(f'/api/v1/admin/service-principals/{principal_id}/tokens', json={'name': 'Review smoke temporary', 'scopes': ['source:import'], 'expiresAt': (datetime.now(UTC) + timedelta(hours=1)).isoformat()})
        assert response.status_code == 200, response.text
        token = response.json()['data']
        service_token_path = f"/api/v1/admin/service-principals/{principal_id}/tokens/{token['id']}"
        headers = {'Authorization': f"Bearer {token['token']}"}
        repository = f'https://github.com/reviewer-smoke/fixture-{run}'
        namespace = f'oss-reviewer-smoke-fixture-{run}'
        response = await platform.put(f'/api/cli/v1/source-imports/namespaces/{namespace}', headers=headers, json={'repositoryUrl': repository, 'displayName': f'OSS-reviewer-smoke-fixture-{run}', 'fallbackOwnerProviderCode': 'keycloak', 'fallbackOwnerLoginName': f'rc_publisher_{suffix}'})
        assert response.status_code == 200, response.text
        for number, initiator in [(1, 'publisher'), (2, 'reviewer')]:
            version = f'{number}.0.0'
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('SKILL.md', f'---\nname: OSS Reviewer\ndescription: Explain user provided text.\nversion: {version}\n---\n# OSS Reviewer\nExplain text clearly. Revision {number}.\n')
            metadata = {'repositoryUrl': repository, 'repositoryRevisionSha': str(number) * 40, 'sourceRefType': 'TAG', 'sourceRef': f'v{version}', 'sourcePath': 'oss-reviewer', 'initiatorProviderCode': 'keycloak', 'initiatorLoginName': f'rc_{initiator}_{suffix}'}
            response = await platform.post(f'/api/cli/v1/source-imports/{namespace}/skills', headers=headers, data={'metadata': json.dumps(metadata)}, files={'file': ('skill.zip', archive.getvalue(), 'application/zip')})
            assert response.status_code == 200, response.text
            imported = response.json()['data']
            assert imported['stableOwner']['displayName'] == f'rc_publisher_{suffix}'
            assert imported['reviewSubmitter']['loginName'] == f'rc_{initiator}_{suffix}'
            path = f"/api/web/reviews/skills/{imported['skillId']}/versions/{imported['version']}/context"
            deadline = time.monotonic() + 150
            while True:
                response = await clients[initiator].get(path)
                assert response.status_code == 200, response.text
                context = response.json()['data']
                if context['waitingReason'] != 'SCANNING':
                    break
                assert time.monotonic() < deadline, context
                await asyncio.sleep(2)
            assert context['waitingReason'] == 'HUMAN_REVIEW', context
            # Existing OSS namespace creation gives fallback user OWNER and platform actor ADMIN.
            assert [p['userId'] for p in context['reviewers']] == [platform_id], context
            if number == 2:
                async with engine.begin() as conn:
                    await conn.execute(text("UPDATE namespace_member SET role='MEMBER' WHERE user_id=:user AND namespace_id=(SELECT id FROM namespace WHERE slug=:slug)"), {'user': platform_id, 'slug': namespace})
                assert (await clients[initiator].get(path)).json()['data']['total'] == 0
            approver = clients['publisher'] if number == 1 else platform
            response = await approver.post(f"/api/web/reviews/{context['reviewTaskId']}/approve", json={'comment': 'OSS reviewer visibility smoke'})
            assert response.status_code == 200, response.text
            completed = (await clients[initiator].get(path)).json()['data']
            assert completed['waitingReason'] == 'APPROVED'
            assert completed['reviewedByName'] == (f'rc_publisher_{suffix}' if number == 1 else f'rc_platform_{run}')
            print(f'PASS OSS v{version}: service auth, stable owner, {initiator} submitter, namespace ADMIN list, real scan and ' + ('unchanged OWNER self approval' if number == 1 else 'unlisted SUPER_ADMIN approval after membership change'), flush=True)
    finally:
        if service_token_path:
            response = await clients['platform'].delete(service_token_path)
            assert response.status_code == 204, 'Failed to revoke smoke service token'
        for client in clients.values():
            await client.aclose()
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

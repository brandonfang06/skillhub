"""Exercise native publish/scan/review using the fixtures from smoke_review_context."""
import asyncio
import io
import os
import time
import zipfile
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    suffix = os.environ['REVIEW_SMOKE_SUFFIX']
    base = os.environ['REVIEW_SMOKE_BASE_URL']
    assert urlsplit(base).hostname in {'127.0.0.1', 'localhost'}, 'Local smoke only'
    assert urlsplit(os.environ['SKILLHUB_TEST_DATABASE_URL']).hostname in {'127.0.0.1', 'localhost'}, 'Local smoke database only'
    engine = create_async_engine(os.environ['SKILLHUB_TEST_DATABASE_URL'])
    namespace = f'review-smoke-{suffix}'
    async with httpx.AsyncClient(base_url=base, timeout=60) as publisher, httpx.AsyncClient(base_url=base, timeout=60) as reviewer:
        for name, client in [('publisher', publisher), ('reviewer', reviewer)]:
            response = await client.post('/api/v1/auth/local/login', json={'username': f'rc_{name}_{suffix}', 'password': 'ReviewSmoke123!'})
            assert response.status_code == 200, response.text
        # Seed only extra local smoke memberships to cover a multi-page roster.
        async with engine.begin() as conn:
            ns = (await conn.execute(text('SELECT id FROM namespace WHERE slug=:slug'), {'slug': namespace})).scalar_one()
            for number in range(6):
                user = f'rc-page-{suffix}-{number}'
                await conn.execute(text("INSERT INTO user_account(id,display_name,status) VALUES (:id,:name,'ACTIVE') ON CONFLICT(id) DO NOTHING"), {'id': user, 'name': f'Review Admin {number + 1}'})
                await conn.execute(text("INSERT INTO namespace_member(namespace_id,user_id,role) VALUES (:ns,:user,'ADMIN') ON CONFLICT(namespace_id,user_id) DO NOTHING"), {'ns': ns, 'user': user})
        for version, action in [('1.0.0', 'approve'), ('2.0.0', 'reject'), ('3.0.0', None)]:
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('SKILL.md', f'---\nname: Reviewer Flow\ndescription: Local smoke skill to verify namespace reviewer display.\nversion: {version}\n---\n# Reviewer Flow\nSummarize the user provided text concisely.\n')
            response = await publisher.post(f'/api/web/skills/{namespace}/publish', files={'file': ('skill.zip', archive.getvalue(), 'application/zip')}, data={'visibility': 'PUBLIC'})
            assert response.status_code == 200, response.text
            slug = response.json()['data']['slug']
            async with engine.connect() as conn:
                row = (await conn.execute(text('SELECT s.id AS skill_id,sv.id AS version_id FROM skill s JOIN skill_version sv ON sv.skill_id=s.id WHERE s.namespace_id=:ns AND s.slug=:slug AND sv.version=:version'), {'ns': ns, 'slug': slug, 'version': version})).mappings().one()
            path = f"/api/web/reviews/skills/{row['skill_id']}/versions/{version}/context"
            deadline = time.monotonic() + 150
            while True:
                response = await publisher.get(path)
                assert response.status_code == 200, response.text
                data = response.json()['data']
                if data['waitingReason'] != 'SCANNING':
                    break
                assert time.monotonic() < deadline, data
                await asyncio.sleep(2)
            print(f"Scanned {version}: {data['versionStatus']} / {data['waitingReason']}", flush=True)
            if data['waitingReason'] == 'NOT_SUBMITTED':
                response = await publisher.post('/api/web/reviews', json={'skillVersionId': row['version_id']})
                assert response.status_code == 200, response.text
                data = (await publisher.get(path)).json()['data']
            assert data['waitingReason'] == 'HUMAN_REVIEW', data
            assert data['total'] == 7, data
            assert len((await publisher.get(path + '?size=5&page=1')).json()['data']['reviewers']) == 2
            if action:
                response = await reviewer.post(f"/api/web/reviews/{data['reviewTaskId']}/{action}", json={'comment': f'Local smoke {action}'})
                assert response.status_code == 200, response.text
                completed = (await publisher.get(path)).json()['data']
                assert completed['waitingReason'] == ('APPROVED' if action == 'approve' else 'REJECTED'), completed
                assert completed['reviewedByName'] == f'rc_reviewer_{suffix}'
                print(f'PASS real namespace ADMIN {action}; actual reviewer retained', flush=True)
            else:
                print(f"Acceptance detail: /space/{namespace}/{slug}; skill={row['skill_id']}; version={version}", flush=True)
    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

"""Create uniquely named fixtures in a disposable local smoke stack; never use production."""
import asyncio
import os
from uuid import uuid4
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    base = os.environ['REVIEW_SMOKE_BASE_URL']
    assert urlsplit(base).hostname in {'127.0.0.1', 'localhost'}, 'Local smoke only'
    assert urlsplit(os.environ['SKILLHUB_TEST_DATABASE_URL']).hostname in {'127.0.0.1', 'localhost'}, 'Local smoke database only'
    engine = create_async_engine(os.environ['SKILLHUB_TEST_DATABASE_URL'])
    suffix = uuid4().hex[:8]
    clients = {name: httpx.AsyncClient(base_url=base) for name in ('publisher', 'reviewer', 'outsider')}
    users = {}
    try:
        for name, client in clients.items():
            response = await client.post('/api/v1/auth/local/register', json={
                'username': f'rc_{name}_{suffix}', 'password': 'ReviewSmoke123!',
                'email': f'rc_{name}_{suffix}@example.test',
            })
            assert response.status_code == 200, (response.status_code, response.text)
            users[name] = response.json()['data']['userId']
        async with engine.begin() as conn:
            ns = (await conn.execute(text("INSERT INTO namespace(slug,display_name,type,created_by) VALUES (:slug,'Reviewer visibility smoke','TEAM',:owner) RETURNING id"), {'slug': f'review-smoke-{suffix}', 'owner': users['publisher']})).scalar_one()
            for name, role in [('publisher', 'OWNER'), ('reviewer', 'ADMIN')]:
                await conn.execute(text('INSERT INTO namespace_member(namespace_id,user_id,role) VALUES (:ns,:user,:role)'), {'ns': ns, 'user': users[name], 'role': role})
            skill = (await conn.execute(text("INSERT INTO skill(namespace_id,slug,display_name,owner_id,visibility,created_by,updated_by) VALUES (:ns,'reviewer-demo','Reviewer Demo',:owner,'PRIVATE',:owner,:owner) RETURNING id"), {'ns': ns, 'owner': users['publisher']})).scalar_one()
            version = (await conn.execute(text("INSERT INTO skill_version(skill_id,version,status,created_by) VALUES (:skill,'1.0.0','PENDING_REVIEW',:author) RETURNING id"), {'skill': skill, 'author': users['publisher']})).scalar_one()
            task = (await conn.execute(text("INSERT INTO review_task(skill_version_id,skill_id,skill_version,namespace_id,status,submitted_by) VALUES (:version,:skill,'1.0.0',:ns,'PENDING',:author) RETURNING id"), {'version': version, 'skill': skill, 'ns': ns, 'author': users['publisher']})).scalar_one()
        path = f'/api/web/reviews/skills/{skill}/versions/1.0.0/context'
        response = await clients['publisher'].get(path)
        assert response.status_code == 200, response.text
        data = response.json()['data']
        assert data['waitingReason'] == 'HUMAN_REVIEW' and data['total'] == 1, data
        assert data['reviewers'][0]['userId'] == users['reviewer']
        assert response.headers['cache-control'] == 'private, no-store'
        assert (await clients['outsider'].get(path)).status_code == 403
        async with httpx.AsyncClient(base_url=base) as anonymous:
            assert (await anonymous.get(path)).status_code == 401
        for query in ['?size=0', '?size=101', '?page=-1']:
            assert (await clients['publisher'].get(path + query)).status_code == 422
        assert (await clients['publisher'].get(path.replace('1.0.0', 'missing'))).status_code == 404
        print(f'PASS real HTTP: publisher/admin list, private ACL, anonymous, pagination, missing version. namespace=review-smoke-{suffix} skill={skill} task={task}')
        print(f'Acceptance login: rc_publisher_{suffix}; disposable password: ReviewSmoke123!')
    finally:
        for client in clients.values():
            await client.aclose()
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

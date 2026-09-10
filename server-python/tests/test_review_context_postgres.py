from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.review.context_repository import read_version_review_context
from app.review.query import ReviewQueryError

URL = os.getenv('SKILLHUB_TEST_DATABASE_URL')
pytestmark = [pytest.mark.anyio, pytest.mark.skipif(not URL, reason='requires real PostgreSQL')]


async def test_publisher_sees_only_active_namespace_admins_without_expanding_access():
    engine = create_async_engine(str(URL))
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            suffix = uuid4().hex[:12]
            users = {role: f'rc-{role}-{suffix}' for role in ('owner', 'submitter', 'admin', 'admin2', 'inactive', 'member', 'super')}
            for role, ident in users.items():
                await conn.execute(text('INSERT INTO user_account (id, display_name, status) VALUES (:id,:name,:status)'),
                                   {'id': ident, 'name': role, 'status': 'DISABLED' if role == 'inactive' else 'ACTIVE'})
            ns = (await conn.execute(text("INSERT INTO namespace (slug,display_name,type,created_by) VALUES (:slug,'Review team','TEAM',:owner) RETURNING id"),
                                     {'slug': f'rc-{suffix}', 'owner': users['owner']})).scalar_one()
            for who, role in [('owner','OWNER'),('admin','ADMIN'),('admin2','ADMIN'),('inactive','ADMIN'),('member','MEMBER')]:
                await conn.execute(text('INSERT INTO namespace_member(namespace_id,user_id,role) VALUES (:ns,:user,:role)'),
                                   {'ns': ns, 'user': users[who], 'role': role})
            await conn.execute(text("INSERT INTO user_role_binding (user_id,role_id) SELECT :user,id FROM role WHERE code='SUPER_ADMIN'"), {'user': users['super']})
            await conn.execute(text("INSERT INTO identity_binding(user_id,provider_code,subject,login_name,extra_json) VALUES (:user,'keycloak',:subject,'readable-login','{}'::jsonb)"), {'user': users['admin'], 'subject': f'review-{suffix}'})
            skill = (await conn.execute(text("INSERT INTO skill(namespace_id,slug,owner_id,visibility,created_by,updated_by) VALUES (:ns,'test',:owner,'PRIVATE',:owner,:owner) RETURNING id"),
                                        {'ns': ns, 'owner': users['owner']})).scalar_one()
            version = (await conn.execute(text("INSERT INTO skill_version(skill_id,version,status,created_by) VALUES (:skill,'1.0.0','PENDING_REVIEW',:author) RETURNING id"),
                                          {'skill': skill, 'author': users['submitter']})).scalar_one()
            await conn.execute(text("INSERT INTO review_task(skill_version_id,skill_id,skill_version,namespace_id,status,submitted_by) VALUES (:version,:skill,'1.0.0',:ns,'PENDING',:author)"),
                               {'version': version, 'skill': skill, 'ns': ns, 'author': users['submitter']})
            async def read(who='submitter', page=0):
                return await read_version_review_context(conn, skill_id=skill, version='1.0.0', user_id=users[who], page=page, size=1)
            data = await read()
            assert data['waitingReason'] == 'HUMAN_REVIEW'
            assert data['total'] == 2
            assert [p['displayName'] for p in data['reviewers']] == ['admin']
            assert data['reviewers'][0]['loginName'] == 'readable-login'
            assert [p['displayName'] for p in (await read(page=1))['reviewers']] == ['admin2']
            assert (await read('owner'))['total'] == 2
            assert (await read('super'))['total'] == 2
            assert (await read('admin'))['total'] == 2
            for requested_version in ('missing', '1.0.1'):
                with pytest.raises(ReviewQueryError) as error:
                    await read_version_review_context(conn, skill_id=skill, version=requested_version, user_id=users['submitter'])
                assert error.value.status_code == 404
            for who in ['member', 'inactive']:
                with pytest.raises(ReviewQueryError) as error:
                    await read(who)
                assert error.value.status_code == 403
            await conn.execute(text("UPDATE user_account SET status='DISABLED' WHERE id=:id"), {'id': users['admin']})
            assert (await read())['total'] == 1
            await conn.execute(text("UPDATE namespace SET status='FROZEN' WHERE id=:id"), {'id': ns})
            assert (await read())['waitingReason'] == 'NAMESPACE_UNAVAILABLE'
            await conn.execute(text("UPDATE namespace SET status='ACTIVE' WHERE id=:id"), {'id': ns})
            audit = (await conn.execute(text("INSERT INTO security_audit(skill_version_id,scanner_type,verdict,is_safe) VALUES (:version,'SKILL_SCANNER','SAFE',true) RETURNING id"), {'version': version})).scalar_one()
            assert (await read())['waitingReason'] == 'SCANNING'
            await conn.execute(text("INSERT INTO local_security_scan_execution(security_audit_id,scan_status) VALUES (:audit,'PARTIAL')"), {'audit': audit})
            assert (await read())['waitingReason'] == 'SCAN_PARTIAL'
            for status, expected in [('FAILED', 'SCAN_FAILED'), ('COMPLETE', 'HUMAN_REVIEW')]:
                await conn.execute(text('UPDATE local_security_scan_execution SET scan_status=:status WHERE security_audit_id=:id'), {'status': status, 'id': audit})
                assert (await read())['waitingReason'] == expected
            await conn.execute(text("UPDATE namespace SET type='GLOBAL' WHERE id=:id"), {'id': ns})
            assert (await read())['reviewers'] == []
            assert (await read('super'))['total'] == 0
            with pytest.raises(ReviewQueryError) as error:
                await read('admin2')
            assert error.value.status_code == 403
            await conn.execute(text("UPDATE namespace SET type='TEAM' WHERE id=:id"), {'id': ns})
            for status, expected in [('SCANNING','SCANNING'), ('SCAN_FAILED','SCAN_FAILED'), ('UPLOADED','NOT_SUBMITTED')]:
                await conn.execute(text('UPDATE skill_version SET status=:status WHERE id=:id'), {'status': status, 'id': version})
                assert (await read())['waitingReason'] == expected
            await conn.execute(text("UPDATE skill_version SET status='PUBLISHED' WHERE id=:id"), {'id': version})
            await conn.execute(text("UPDATE review_task SET status='APPROVED',reviewed_by=:reviewer,reviewed_at=CURRENT_TIMESTAMP WHERE skill_version_id=:id"), {'reviewer': users['admin2'], 'id': version})
            done = await read()
            assert done['waitingReason'] == 'APPROVED'
            assert done['reviewedByName'] == 'admin2'
            assert done['reviewers'] == []
            await conn.execute(text("INSERT INTO skill_version(skill_id,version,status,created_by) VALUES (:skill,'2.0.0','UPLOADED',:author)"), {'skill': skill, 'author': users['member']})
            draft = await read_version_review_context(conn, skill_id=skill, version='2.0.0', user_id=users['member'])
            assert draft['waitingReason'] == 'NOT_SUBMITTED'
            assert draft['reviewers'] == []
            with pytest.raises(ReviewQueryError) as error:
                await read_version_review_context(conn, skill_id=skill, version='2.0.0', user_id=users['submitter'])
            assert error.value.status_code == 403
        finally:
            await transaction.rollback()
    await engine.dispose()

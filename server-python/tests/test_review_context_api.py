from fastapi.testclient import TestClient

from app.main import create_app


def test_review_context_requires_login():
    app = create_app()
    with TestClient(app) as client:
        for prefix in ('/api/v1', '/api/web'):
            response = client.get(f'{prefix}/reviews/skills/1/versions/1.0.0/context')
            assert response.status_code == 401


def test_review_context_openapi_documents_typed_response():
    schema = create_app().openapi()
    path = '/api/web/reviews/skills/{skill_id}/versions/{version}/context'
    assert schema['paths'][path]['get']['responses']['200']['content']['application/json']['schema']['$ref'].endswith('/ReviewContextEnvelope')

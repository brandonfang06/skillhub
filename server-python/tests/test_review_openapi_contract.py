from app.main import create_app


def test_review_detail_openapi_exposes_archive_fields() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/api/web/reviews/{review_task_id}"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"] == "#/components/schemas/ApiResponseReviewTaskResponse"

    review_schema = schema["components"]["schemas"]["ReviewTaskResponse"]
    properties = review_schema["properties"]
    assert properties["superseded"]["type"] == "boolean"
    assert properties["artifactAvailable"]["type"] == "boolean"
    assert properties["replacementVersionId"]["anyOf"][0]["type"] == "integer"
    assert properties["replacementReviewTaskId"]["anyOf"][0]["type"] == "integer"
    assert properties["requestedVisibility"]["anyOf"][0]["type"] == "string"
    assert properties["approvalVisibility"]["anyOf"][0]["type"] == "string"
    assert properties["archivedSnapshot"]["anyOf"][0]["$ref"] == (
        "#/components/schemas/ArchivedReviewSnapshotResponse"
    )

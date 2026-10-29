"""Outside-scholarship uploads return a job id; extraction finishes on GET."""

from types import SimpleNamespace

from api.dependencies import get_azure_client
from outside_scholarships_fakes import (
    BACK,
    FRONT,
    JOB_ROUTE,
    ROUTE,
    FakeLLM,
    await_job,
    build_pdf,
    preview_payload,
    scripted_pages,
)
from utils.auth import get_current_user


def test_upload_returns_202_then_preview_on_get(client, override_auth, app):
    start, llm = _start_job(client, app, [FRONT])
    assert start.status_code == 202, start.text
    body = start.json()
    assert body["status"] == "processing"
    job_id = body["job_id"]
    assert job_id

    finished = client.get(f"{JOB_ROUTE}/{job_id}")
    assert finished.status_code == 200, finished.text
    preview = preview_payload(finished)
    assert len(preview["checks"]) == 1
    assert llm.extraction_calls == 1


def test_job_get_404_for_unknown_id(client, override_auth):
    response = client.get(f"{JOB_ROUTE}/not-a-real-job")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_job_get_404_for_another_user(client, override_auth, app, admin_user):
    start, _ = _start_job(client, app, [FRONT])
    job_id = start.json()["job_id"]

    app.dependency_overrides[get_current_user] = lambda: {
        **admin_user,
        "id": "someone-else",
        "email": "other@unc.edu",
    }
    response = client.get(f"{JOB_ROUTE}/{job_id}")
    assert response.status_code == 404


def test_get_returns_processing_before_complete(client, override_auth, admin_user):
    from services.banking.outside_scholarships.jobs import create_job, job_owner

    job_id = create_job(job_owner(admin_user))
    response = client.get(f"{JOB_ROUTE}/{job_id}")
    assert response.status_code == 200
    assert response.json() == {"job_id": job_id, "status": "processing"}


def test_upload_rejects_when_at_processing_cap(client, override_auth, app, admin_user, monkeypatch):
    from services.banking.outside_scholarships import jobs as jobs_mod

    monkeypatch.setattr(jobs_mod, "MAX_PROCESSING_JOBS", 1)
    jobs_mod.create_job(jobs_mod.job_owner(admin_user))
    start, llm = _start_job(client, app, [FRONT])
    assert start.status_code == 429, start.text
    assert "still extracting" in start.json()["detail"].lower()
    assert llm.extraction_calls == 0


def test_job_owner_prefers_stable_id():
    from services.banking.outside_scholarships.jobs import job_owner

    assert job_owner({"id": "oid-1", "email": "a@unc.edu"}) == "oid-1"
    assert job_owner({"email": "a@unc.edu"}) == "a@unc.edu"


def test_job_error_surfaces_as_http_error(client, override_auth, app):
    start, llm = _start_job(client, app, [FRONT, BACK, BACK])
    assert start.status_code == 202, start.text
    finished = await_job(client, start)
    assert finished.status_code == 400
    assert "Page 3 " in finished.json()["detail"]
    assert llm.extraction_calls == 0


def _start_job(client, app, sides):
    pages = scripted_pages(sides)
    llm = FakeLLM(pages)
    app.dependency_overrides[get_azure_client] = lambda: SimpleNamespace(llm=llm)
    start = client.post(
        ROUTE,
        files={"files": ("checks.pdf", build_pdf(pages), "application/pdf")},
        data={"aid_term": "F"},
    )
    return start, llm

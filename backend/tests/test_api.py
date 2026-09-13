"""
Tests for core API endpoints: health, organizations, projects, prompts, versions.
"""


def test_health_check(client):
    """GET /health should return ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_root_endpoint(client):
    """GET / should return API info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


# ─── Organizations ────────────────────────────────────────────────────

def test_list_organizations_empty(client):
    """GET /organizations/ should return empty list initially."""
    response = client.get("/organizations/")
    assert response.status_code == 200
    assert response.json() == []


# ─── Projects ─────────────────────────────────────────────────────────

def _create_org(client):
    """Helper: create a default organization via the database directly."""
    # We need to create an org first — our API only has list endpoint
    # So we use the session directly via the test client
    from backend.models import Organization
    from backend.database import get_session

    # Access the overridden session
    session = next(client.app.dependency_overrides[get_session]())
    org = Organization(name="Test Org", slug="test-org")
    session.add(org)
    session.commit()
    session.refresh(org)
    return str(org.id)


def test_create_project(client):
    """POST /projects/ should create a new project."""
    org_id = _create_org(client)
    response = client.post("/projects/", json={
        "name": "Test Project",
        "description": "A test project",
        "organization_id": org_id,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Project"
    assert "id" in data


def test_list_projects(client):
    """GET /projects?organization_id= should return projects for that org."""
    org_id = _create_org(client)
    # Create a project
    client.post("/projects/", json={
        "name": "P1", "organization_id": org_id,
    })
    response = client.get(f"/projects?organization_id={org_id}")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_delete_project(client):
    """DELETE /projects/{id} should remove the project."""
    org_id = _create_org(client)
    create_res = client.post("/projects/", json={
        "name": "To Delete", "organization_id": org_id,
    })
    project_id = create_res.json()["id"]
    delete_res = client.delete(f"/projects/{project_id}")
    assert delete_res.status_code == 200
    # Verify it's gone
    get_res = client.get(f"/projects/{project_id}")
    assert get_res.status_code == 404


# ─── Prompts ──────────────────────────────────────────────────────────

def _create_project(client):
    """Helper: create org + project, return project_id."""
    org_id = _create_org(client)
    res = client.post("/projects/", json={
        "name": "Test Project", "organization_id": org_id,
    })
    return res.json()["id"]


def test_create_prompt(client):
    """POST /prompts/ should create a new prompt."""
    project_id = _create_project(client)
    response = client.post("/prompts/", json={
        "name": "Test Prompt",
        "description": "A test",
        "project_id": project_id,
        "tags": ["test", "demo"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Prompt"
    assert data["tags"] == ["test", "demo"]


def test_list_prompts(client):
    """GET /prompts?project_id= should list prompts."""
    project_id = _create_project(client)
    client.post("/prompts/", json={
        "name": "Prompt 1", "project_id": project_id,
    })
    client.post("/prompts/", json={
        "name": "Prompt 2", "project_id": project_id,
    })
    response = client.get(f"/prompts?project_id={project_id}")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_all_prompts(client):
    """GET /prompts/all should return all prompts."""
    project_id = _create_project(client)
    client.post("/prompts/", json={"name": "P1", "project_id": project_id})
    response = client.get("/prompts/all")
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_update_prompt(client):
    """PUT /prompts/{id} should update prompt fields."""
    project_id = _create_project(client)
    create_res = client.post("/prompts/", json={
        "name": "Original", "project_id": project_id,
    })
    prompt_id = create_res.json()["id"]
    update_res = client.put(f"/prompts/{prompt_id}", json={
        "name": "Updated Name", "tags": ["new-tag"],
    })
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Updated Name"


def test_delete_prompt(client):
    """DELETE /prompts/{id} should remove the prompt."""
    project_id = _create_project(client)
    create_res = client.post("/prompts/", json={
        "name": "To Delete", "project_id": project_id,
    })
    prompt_id = create_res.json()["id"]
    delete_res = client.delete(f"/prompts/{prompt_id}")
    assert delete_res.status_code == 200


def test_copy_prompt(client):
    """POST /prompts/{id}/copy should duplicate the prompt."""
    project_id = _create_project(client)
    create_res = client.post("/prompts/", json={
        "name": "Original", "project_id": project_id,
    })
    prompt_id = create_res.json()["id"]
    copy_res = client.post(f"/prompts/{prompt_id}/copy")
    assert copy_res.status_code == 200
    assert copy_res.json()["name"] == "Copy of Original"


# ─── Versions ─────────────────────────────────────────────────────────

def test_create_version(client):
    """POST /prompts/{id}/versions should create a new version."""
    project_id = _create_project(client)
    prompt_res = client.post("/prompts/", json={
        "name": "Versioned", "project_id": project_id,
    })
    prompt_id = prompt_res.json()["id"]
    version_res = client.post(f"/prompts/{prompt_id}/versions", json={
        "prompt_id": prompt_id,
        "content": "Hello {{name}}, welcome to {{company}}!",
        "commit_message": "Initial version",
    })
    assert version_res.status_code == 200
    data = version_res.json()
    assert data["version_number"] == 1
    assert "name" in data["variables"]
    assert "company" in data["variables"]


def test_list_versions(client):
    """GET /prompts/{id}/versions should return all versions."""
    project_id = _create_project(client)
    prompt_res = client.post("/prompts/", json={
        "name": "Multi-version", "project_id": project_id,
    })
    prompt_id = prompt_res.json()["id"]
    # Create 2 versions
    client.post(f"/prompts/{prompt_id}/versions", json={
        "prompt_id": prompt_id, "content": "v1 content",
    })
    client.post(f"/prompts/{prompt_id}/versions", json={
        "prompt_id": prompt_id, "content": "v2 content",
    })
    response = client.get(f"/prompts/{prompt_id}/versions")
    assert response.status_code == 200
    versions = response.json()
    assert len(versions) == 2
    # Should be ordered desc
    assert versions[0]["version_number"] == 2


# ─── Stats ────────────────────────────────────────────────────────────

def test_stats_endpoint(client):
    """GET /stats should return counts."""
    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert "prompts" in data
    assert "projects" in data
    assert "versions" in data
    assert "evaluations" in data


# ─── Playground ───────────────────────────────────────────────────────

def test_playground_run(client, monkeypatch):
    """POST /playground/run should substitute variables and return response."""
    def mock_run_llm(*args, **kwargs):
        return {
            "rendered_prompt": "Hello Alice, welcome to Acme!",
            "response": "Hello!",
            "model": "gpt-5.5",
            "provider": "openai",
            "prompt_tokens": 10,
            "completion_tokens": 10,
            "total_tokens": 20,
            "estimated_cost_usd": 0.01,
            "latency_ms": 100,
        }
    monkeypatch.setattr("backend.api.routers.utilities.run_llm", mock_run_llm)

    response = client.post("/playground/run", json={
        "content": "Hello {{name}}, welcome to {{company}}!",
        "variables": {"name": "Alice", "company": "Acme"},
    })
    assert response.status_code == 200
    data = response.json()
    assert "Alice" in data["rendered_prompt"]
    assert "Acme" in data["rendered_prompt"]
    assert "response" in data


# ─── Export ───────────────────────────────────────────────────────────

def test_export_prompt(client):
    """GET /prompts/{id}/export should return full prompt JSON."""
    project_id = _create_project(client)
    prompt_res = client.post("/prompts/", json={
        "name": "Exportable", "project_id": project_id, "tags": ["export"],
    })
    prompt_id = prompt_res.json()["id"]
    client.post(f"/prompts/{prompt_id}/versions", json={
        "prompt_id": prompt_id, "content": "Hello {{name}}",
    })
    export_res = client.get(f"/prompts/{prompt_id}/export")
    assert export_res.status_code == 200
    data = export_res.json()
    assert data["format"] == "assay/v2"
    assert data["prompt"]["name"] == "Exportable"
    assert len(data["versions"]) == 1


def test_export_project(client):
    """GET /projects/{id}/export should return all prompts."""
    project_id = _create_project(client)
    client.post("/prompts/", json={"name": "P1", "project_id": project_id})
    client.post("/prompts/", json={"name": "P2", "project_id": project_id})
    export_res = client.get(f"/projects/{project_id}/export")
    assert export_res.status_code == 200
    data = export_res.json()
    assert len(data["prompts"]) == 2

# ─── Models Registry ──────────────────────────────────────────────────

def test_list_models(client):
    """GET /models/ should return active models."""
    response = client.get("/models/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_and_delete_model(client):
    """POST /models/ and DELETE /models/{id}."""
    res = client.post("/models/", json={
        "id": "test-model-1",
        "name": "Test Model",
        "provider": "test_provider"
    })
    assert res.status_code == 200
    
    del_res = client.delete("/models/test-model-1")
    assert del_res.status_code == 200

# ─── Library ──────────────────────────────────────────────────────────

def test_library_categories(client):
    """GET /library/categories should return the curated list."""
    response = client.get("/library/categories")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

# ─── Chains ───────────────────────────────────────────────────────────

def test_create_chain(client):
    """POST /chains/ should create a prompt chain."""
    project_id = _create_project(client)
    res = client.post("/chains/", json={
        "project_id": project_id,
        "name": "Test Chain",
        "description": "A workflow"
    })
    assert res.status_code == 200
    assert res.json()["name"] == "Test Chain"

# ─── Licensing & Premium Features ─────────────────────────────────────


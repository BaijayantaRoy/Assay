"""Provider status is useful without ever exposing credential material."""


def test_provider_status_reports_presence_only(client, monkeypatch):
    variables = (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
        "DEEPSEEK_API_KEY", "XAI_API_KEY", "MOONSHOT_API_KEY",
        "MISTRAL_API_KEY", "OLLAMA_BASE_URL",
    )
    for variable in variables:
        monkeypatch.delenv(variable, raising=False)
    secret = "must-never-cross-the-api-boundary"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    response = client.get("/v1/integrations/provider-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] == 1
    assert payload["total"] == len(variables)
    assert next(p for p in payload["providers"] if p["id"] == "openai")["configured"] is True
    assert secret not in response.text
    assert "OPENAI_API_KEY" not in response.text

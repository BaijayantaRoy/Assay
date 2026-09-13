"""Observability status must distinguish configuration from delivered evidence."""


def test_observability_status_never_claims_export_delivery(client, monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("ASSAY_OTEL_LOG_CONTENT", raising=False)

    response = client.get("/v1/observability")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tracer_registered"] is True
    assert payload["otel_api_available"] is True
    assert payload["otlp_endpoint_declared"] is False
    assert payload["content_capture"] is False
    assert payload["export_verified"] is None
    assert "not checked" in payload["note"].lower()


def test_declared_endpoint_is_still_not_delivery_evidence(client, monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.invalid/v1/traces")
    monkeypatch.setenv("ASSAY_OTEL_LOG_CONTENT", "true")

    payload = client.get("/v1/observability").json()

    assert payload["otlp_endpoint_declared"] is True
    assert payload["content_capture"] is True
    assert payload["export_verified"] is None


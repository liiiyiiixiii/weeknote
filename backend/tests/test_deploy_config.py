from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_example_nginx_config_uses_only_documentation_domain():
    nginx = (PROJECT_ROOT / "deploy" / "nginx-weeknote.example.conf").read_text()

    assert "server_name example.com;" in nginx
    assert "return 308 https://example.com$request_uri;" in nginx


def test_persistent_runtime_release_uses_two_bounded_workers():
    service = (PROJECT_ROOT / "deploy" / "weeknote.service.example").read_text()

    assert "WorkingDirectory=/opt/weeknote/backend" in service
    assert "EnvironmentFile=/etc/weeknote.env" in service
    assert "ReadWritePaths=/var/lib/weeknote" in service
    assert "--workers 2" in service


def test_voice_handshake_rate_limit_is_isolated_from_api_bursts():
    nginx = (PROJECT_ROOT / "deploy" / "nginx-weeknote.example.conf").read_text()

    assert "zone=ask_ws_req_per_ip:10m rate=1r/s" in nginx
    assert "location = /ask/ws/asr" in nginx
    voice_location = nginx.split("location = /ask/ws/asr", 1)[1].split("}", 1)[0]
    assert "limit_req zone=ask_ws_req_per_ip burst=2 nodelay;" in voice_location
    assert "limit_conn ask_conn_per_ip 2;" in voice_location
    assert "limit_req zone=ask_req_per_ip" not in voice_location


def test_public_deploy_templates_do_not_contain_private_material():
    public_files = {path.name for path in (PROJECT_ROOT / "deploy").iterdir() if path.is_file()}

    assert public_files == {"README.md", "nginx-weeknote.example.conf", "weeknote.service.example"}

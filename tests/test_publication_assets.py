from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

PUBLIC_TEXT_FILES = (
    ROOT / "README.md",
    ROOT / "RUNBOOK.md",
    ROOT / "docs" / "bkw-api-observations.md",
    ROOT / "docs" / "loxone-endpoints.md",
    ROOT / "docs" / "library" / "library-entry.md",
    ROOT / "docs" / "library" / "docker-to-loxone.md",
    ROOT / "docs" / "library" / "export-checklist.md",
    ROOT / "examples" / "docker-compose.yml",
    ROOT / "examples" / "portainer-production-stack.template.yml",
)

REMOVED_PRIVATE_OPERATIONS_FILES = (
    ROOT / "manifest.yaml",
    ROOT / "docs" / "go-live-and-naming-plan.md",
    ROOT / "docs" / "portainer-test-deployment.md",
    ROOT / "examples" / "portainer-test-stack.yml",
    ROOT / "scripts" / "live_cutover_portainer.py",
)

PRIVATE_MARKERS = (
    ".".join(("192", "168", "5")) + ".",
    "/mnt/synology-" + "root" + "keeper",
    "/home/" + "root" + "keeper",
    "Stack ID: " + "22",
    "STACK_ID = " + "22",
)


def read(path: Path) -> str:
    assert path.is_file(), f"missing publication asset: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def test_publication_assets_exist_and_private_operations_files_are_removed():
    for path in PUBLIC_TEXT_FILES:
        assert path.is_file(), f"missing publication asset: {path.relative_to(ROOT)}"
    for path in REMOVED_PRIVATE_OPERATIONS_FILES:
        assert not path.exists(), f"private operations artifact remains public: {path.relative_to(ROOT)}"


def test_publication_assets_do_not_contain_private_environment_markers():
    for path in PUBLIC_TEXT_FILES:
        text = read(path)
        for marker in PRIVATE_MARKERS:
            assert marker not in text, f"{marker!r} leaked into {path.relative_to(ROOT)}"


def test_compose_examples_target_v020_and_current_environment_names():
    for relative in (
        Path("examples/docker-compose.yml"),
        Path("examples/portainer-production-stack.template.yml"),
    ):
        text = read(ROOT / relative)
        assert "ghcr.io/4fingereddy/bkw-tariff-proxy:0.2.0" in text
        assert 'UPSTREAM_WARN_AGE_SECONDS: "7200"' in text
        assert 'REQUIRE_COMPLETE_DAY: "true"' in text
        assert "CACHE_MAX_AGE_SECONDS" not in text
        assert "REQUIRE_FULL_HORIZON" not in text
        assert 'BKW_TEST_DATA_MODE: "off"' in text
        assert "bkw-tariff-proxy-data:/data" in text


def test_readme_has_community_support_and_non_affiliation_boundaries():
    text = read(ROOT / "README.md")
    assert "## Community support" in text
    assert "GitHub Issues" in text
    assert "## Non-affiliation" in text
    assert "not affiliated with, endorsed by, or supported by BKW Energie AG or Loxone Electronics GmbH" in text
    assert "v0.2.0" in text


def test_library_entry_uses_absolute_mode_and_only_productive_recognitions():
    text = read(ROOT / "docs" / "library" / "library-entry.md")
    assert "BKW Dynamic Feed-in Tariff Switzerland" in text
    assert "Community Network Template" in text
    assert "Absolute mode" in text
    assert "status_code == 0" in text
    assert "status_code == 10" in text
    assert "Independent community project" in text
    assert "WWLX" not in text

    recognition_names = re.findall(r"^\| `(status-code|h\d{2})` \|", text, flags=re.MULTILINE)
    assert recognition_names == ["status-code", *[f"h{hour:02d}" for hour in range(24)]]
    assert "feedin_current_mchf_kwh" not in text
    assert "missing_hour" not in text
    assert "/v1/feedin/relative" not in text


def test_export_checklist_requires_real_config_export_and_no_submission():
    text = read(ROOT / "docs" / "library" / "export-checklist.md")
    assert "real Loxone Config export" in text
    assert "REPLACE_WITH_PROXY_HOST" in text
    assert "25 command recognitions" in text
    assert "Do not submit" in text
    assert "No push, release, or Library upload is authorized by this checklist" in text

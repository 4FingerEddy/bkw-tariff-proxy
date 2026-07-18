from pathlib import Path
import hashlib
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
LOXONE_DIR = ROOT / "data" / "loxone"
LOXONE_TEMPLATE = LOXONE_DIR / "bkw-tariff-proxy.xml"
LOXONE_EXAMPLE = LOXONE_DIR / "bkw-tariff-proxy-example.Loxone"

PUBLIC_TEXT_FILES = (
    ROOT / "README.md",
    ROOT / "RUNBOOK.md",
    ROOT / "docs" / "bkw-api-observations.md",
    ROOT / "docs" / "loxone-endpoints.md",
    ROOT / "docs" / "library" / "library-entry.md",
    ROOT / "docs" / "library" / "docker-to-loxone.md",
    ROOT / "docs" / "library" / "export-checklist.md",
    LOXONE_DIR / "README.md",
    LOXONE_TEMPLATE,
    LOXONE_EXAMPLE,
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
    return path.read_text(encoding="utf-8-sig")


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


def test_loxone_template_is_real_round_trip_export_with_25_safe_inputs():
    root = ET.parse(LOXONE_TEMPLATE).getroot()
    assert root.tag == "VirtualInHttp"
    assert root.attrib["Address"] == "http://REPLACE_WITH_PROXY_HOST:8785/v1/loxone.json"
    assert root.attrib["PollingTime"] == "900"
    assert root.attrib["Comment"] == ""
    assert 0 < len(root.attrib["HintText"]) <= 500

    info = root.find("Info")
    assert info is not None
    assert info.attrib == {"templateType": "2", "minVersion": "17010630"}

    commands = root.findall("VirtualInHttpCmd")
    assert len(commands) == 25
    assert [command.attrib["Title"] for command in commands] == [
        "BKW Status Code",
        *[f"BKW h{hour:02d}" for hour in range(24)],
    ]

    status = commands[0]
    assert status.attrib["Check"] == '\\i"status_code":\\i\\v'
    assert status.attrib["DefVal"] == "99"
    assert status.attrib["Comment"] == ""
    assert 0 < len(status.attrib["HintText"]) <= 500

    for hour, command in enumerate(commands[1:]):
        assert command.attrib["Check"] == f'\\i"feedin_h{hour:02d}_mchf_kwh":\\i\\v'
        assert command.attrib["Signed"] == "true"
        assert command.attrib["Analog"] == "true"
        assert command.attrib["SourceValLow"] == "0"
        assert command.attrib["DestValLow"] == "0"
        assert command.attrib["SourceValHigh"] == "1000"
        assert command.attrib["DestValHigh"] == "1"
        assert command.attrib["Unit"] == "<v.3>CHF"
        assert command.attrib["Comment"] == ""
        assert 0 < len(command.attrib["HintText"]) <= 500


def test_loxone_example_wiring_and_guard_are_fail_safe():
    template = ET.parse(LOXONE_TEMPLATE).getroot()
    root = ET.parse(LOXONE_EXAMPLE).getroot()
    assert root.tag == "ControlList"

    objects = list(root.iter("C"))
    parents = [
        obj
        for obj in objects
        if obj.attrib.get("Type") == "VirtualHttpIn"
        and obj.attrib.get("Address") == template.attrib["Address"]
    ]
    assert len(parents) == 1
    parent = parents[0]

    template_commands = template.findall("VirtualInHttpCmd")
    config_commands = [
        obj for obj in parent.findall("./C") if obj.attrib.get("Type") == "VirtualHttpInCmd"
    ]
    assert len(config_commands) == 25
    for template_command, config_command in zip(template_commands, config_commands, strict=True):
        assert config_command.attrib["Title"] == template_command.attrib["Title"]
        assert config_command.attrib["Check"] == template_command.attrib["Check"]
        assert config_command.attrib["NTXT"] == template_command.attrib["HintText"]

    connector_owner = {}
    for obj in objects:
        for connector in obj.findall("./Co"):
            if connector.attrib.get("U"):
                connector_owner[connector.attrib["U"]] = (obj, connector)

    edges = []
    for destination in objects:
        for destination_connector in destination.findall("./Co"):
            for incoming in destination_connector.findall("./In"):
                source = connector_owner.get(incoming.attrib.get("Input"))
                if source:
                    source_object, source_connector = source
                    edges.append(
                        (
                            source_object,
                            source_connector.attrib.get("K"),
                            destination,
                            destination_connector.attrib.get("K"),
                        )
                    )

    spot_optimizers = [obj for obj in objects if obj.attrib.get("Type") == "SpotOpt"]
    assert len(spot_optimizers) == 1
    spot_optimizer = spot_optimizers[0]
    assert spot_optimizer.attrib["Mod"] == "1"
    assert spot_optimizer.attrib["Un"] == "<v.3>CHF/kWh"

    for hour in range(24):
        refs = [
            obj
            for obj in objects
            if obj.attrib.get("Type") == "InputRef"
            and obj.attrib.get("Title") == f"BKW h{hour:02d}"
        ]
        assert len(refs) == 1
        assert any(
            source is refs[0]
            and source_port == "AQ"
            and destination is spot_optimizer
            and destination_port == f"U{hour}"
            for source, source_port, destination, destination_port in edges
        )

    states = [
        obj
        for obj in objects
        if obj.attrib.get("Type") == "State" and obj.attrib.get("Title") == "BKW Status Code"
    ]
    assert len(states) == 1
    state = states[0]
    state_texts = state.find("StateTexts")
    assert state_texts is not None
    rows = state_texts.findall("StateText")

    assert rows[0].attrib["Input0"] == "2"
    assert rows[0].attrib["CondV0"] == rows[0].attrib["CondT0"] == "1"
    assert rows[0].attrib["TextV"] == "0"
    assert rows[1].attrib["Input0"] == "3"
    assert rows[1].attrib["CondT0"] == "0"
    assert rows[1].attrib["TextV"] == "1"

    catch_all = [
        row
        for row in rows
        if row.attrib.get("Input0") == "1"
        and row.attrib.get("Cond0") == "5"
        and row.attrib.get("CondT0") == "0"
    ]
    assert len(catch_all) == 1
    assert catch_all[0].attrib["TextV"] == "1"
    assert catch_all[0].attrib["Text"] == "Unknown status code - Dynamic optimization blocked."
    assert rows.index(catch_all[0]) == len(rows) - 2

    online = [obj for obj in parent.findall("./C") if obj.attrib.get("Type") == "Online"]
    assert len(online) == 1
    online_refs = [
        obj
        for obj in objects
        if obj.attrib.get("Type") == "InputRef" and obj.attrib.get("Ref") == online[0].attrib["U"]
    ]
    assert len(online_refs) == 1
    assert any(
        source is online_refs[0]
        and source_port == "AQ"
        and destination is state
        and destination_port == "I3"
        for source, source_port, destination, destination_port in edges
    )

    metadata = read(LOXONE_DIR / "README.md")
    assert "Loxone Config 17.1.16.30" in metadata
    assert "minVersion=17010630" in metadata


def test_loxone_artifact_hashes_match_reviewed_metadata():
    metadata = read(LOXONE_DIR / "README.md")
    expected = {
        LOXONE_TEMPLATE: "52ae8f90b2894a31a287bf7ba0572562aeed8edfd5304068288a8f1c91ca6c80",
        LOXONE_EXAMPLE: "6a4ee6df5f513367cd8f83b25c88720547500a8219db778df914e66af1c95965",
    }
    for path, digest in expected.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert f"{digest}  {path.name}" in metadata


def test_public_docs_use_corrected_chf_scale_before_optimizer():
    paths = (
        ROOT / "README.md",
        ROOT / "docs" / "loxone-endpoints.md",
        ROOT / "docs" / "library" / "library-entry.md",
        ROOT / "docs" / "library" / "docker-to-loxone.md",
        ROOT / "docs" / "library" / "export-checklist.md",
    )
    for path in paths:
        text = read(path)
        assert "0..1000 -> 0..1" in text
        assert "integer values directly" not in text
        assert "raw integer scale for optimizer ordering" not in text

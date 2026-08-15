from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def active_identity_files() -> list[Path]:
    files = [ROOT / "README.md", ROOT / "README_EN.md"]
    files.extend((ROOT / "scripts").glob("*.py"))
    files.extend((ROOT / "docs/phases").glob("*.md"))
    files.append(ROOT / "docs/status/bringup_checklist.md")
    return files


def test_active_linkerhand_paths_use_wrapper_identity() -> None:
    old_slug = "linkerhand_" + "sdk"
    old_url = "LV-Robotics-Lab/" + old_slug
    old_local_path = "upstream/" + old_slug

    for path in active_identity_files():
        text = path.read_text(encoding="utf-8")
        assert old_url not in text, path
        assert old_local_path not in text, path
        assert f"`{old_slug}`" not in text, path
        if path.suffix == ".py":
            assert old_slug not in text, path


def test_archive_explains_why_historical_identity_is_preserved() -> None:
    archive_readme = (ROOT / "docs/archive/README.md").read_text(encoding="utf-8")
    assert "Historical snapshots" in archive_readme
    assert "LV-Robotics-Lab/linkerhand_wrapper" in archive_readme
    assert "upstream/linkerhand_wrapper" in archive_readme


def test_nero_documents_cross_group_consumption_not_primary_ownership() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_en = (ROOT / "README_EN.md").read_text(encoding="utf-8")
    assert "主归属 Piper" in readme
    assert "owned by the Piper route" in readme_en
    assert "not as a default runtime dependency" in readme_en

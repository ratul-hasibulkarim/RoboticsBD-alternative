"""W7: the ads-policy checker passes on the repo and catches injected violations."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import scripts.check_ads_policy as chk

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for sub in ("web/app", "web/components", "web/lib", "ads"):
        shutil.copytree(ROOT / sub, tmp_path / sub)
    monkeypatch.setattr(chk, "ROOT", tmp_path)
    monkeypatch.setattr(chk, "WEB", tmp_path / "web")
    monkeypatch.setattr(chk, "POLICY_FILE", tmp_path / "ads" / "placement_policy.yaml")
    monkeypatch.setattr(chk, "ADSLOT", tmp_path / "web" / "components" / "ads" / "AdSlot.tsx")
    return tmp_path


def test_repo_passes() -> None:
    assert chk.main() == 0


def _inject(path: Path, before: str, snippet: str) -> None:
    src = path.read_text()
    assert before in src
    path.write_text(src.replace(before, snippet + before, 1))


def test_ad_above_the_fold_fails(repo_copy: Path) -> None:
    page = repo_copy / "web/app/component/[slug]/page.tsx"
    _inject(
        page,
        "<ComponentTabs",
        '<AdSlot id="top" placement="below_offers" template="component" client="x" slot="y" />\n',
    )
    assert chk.main() == 1


def test_ad_on_home_fails(repo_copy: Path) -> None:
    page = repo_copy / "web/app/page.tsx"
    src = page.read_text().replace(
        "</>\n  );\n}",
        '<AdSlot id="h" placement="in_feed_native" template="search" client="x" slot="y" />\n    </>\n  );\n}',
    )
    page.write_text(src)
    assert chk.main() == 1


def test_too_many_slots_fails(repo_copy: Path) -> None:
    page = repo_copy / "web/app/component/[slug]/prices/page.tsx"
    extra = '<AdSlot id="a" placement="below_offers" template="prices" client="x" slot="y" />\n' * 3
    _inject(page, "    </article>", extra)
    assert chk.main() == 1


def test_wrong_template_fails(repo_copy: Path) -> None:
    page = repo_copy / "web/app/component/[slug]/prices/page.tsx"
    page.write_text(page.read_text().replace('template="prices"', 'template="search"'))
    assert chk.main() == 1


def test_auto_ads_code_fails(repo_copy: Path) -> None:
    (repo_copy / "web/components/Sneaky.tsx").write_text('export const x = "enable_page_level_ads";\n')
    assert chk.main() == 1


def test_policy_drift_fails(repo_copy: Path) -> None:
    pol = repo_copy / "ads/placement_policy.yaml"
    pol.write_text(pol.read_text().replace("max_slots_per_page: 3", "max_slots_per_page: 5"))
    assert chk.main() == 1

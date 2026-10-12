"""R1 (precision ≥ 0.98, recall ≥ 0.95), R2 (package rule), R3 (audit completeness)."""

from __future__ import annotations

import itertools
import json
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from crawler.normalizer.gtin import normalize_gtin
from resolver.embedder import HashingEmbedder
from resolver.matcher import Action, Candidate, ListingFeatures, match
from resolver.service import ResolvableListing, Resolver
from resolver.tests.memory_index import MemoryIndex

FIXTURE = Path(__file__).parent / "fixtures" / "listings_200.json"


def _load() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(FIXTURE.read_text())["listings"]
    return data


def _item(row: dict[str, Any]) -> ResolvableListing:
    return ResolvableListing(
        id=uuid.UUID(row["id"]),
        title=row["title"],
        mpn=row["mpn"],
        mpn_trusted=row["mpn_trusted"],
        manufacturer=row["manufacturer"],
        gtin=normalize_gtin(row["gtin"]),
        package=row["package"],
        specs=row["specs"],
    )


def _pairs(groups: dict[Any, list[str]]) -> set[frozenset[str]]:
    out: set[frozenset[str]] = set()
    for members in groups.values():
        for a, b in itertools.combinations(sorted(members), 2):
            out.add(frozenset((a, b)))
    return out


async def _run() -> tuple[list[dict[str, Any]], MemoryIndex]:
    rows = _load()
    index = MemoryIndex()
    resolver = Resolver(index, HashingEmbedder())
    # Pass 1 = first crawl (title-only listings without a match are deferred);
    # pass 2 = the deferred retry, where they may create components.
    deferred = []
    for row in rows:
        d = await resolver.resolve(_item(row), allow_untrusted_create=False)
        if d.action is Action.DEFER:
            deferred.append(row)
    for row in deferred:
        await resolver.resolve(_item(row), allow_untrusted_create=True)
    return rows, index


async def test_r1_precision_recall() -> None:
    rows, index = await _run()
    truth: dict[str, list[str]] = defaultdict(list)
    predicted: dict[uuid.UUID, list[str]] = defaultdict(list)
    for r in rows:
        truth[r["truth"]].append(r["id"])
        cid = index.assignments.get(uuid.UUID(r["id"]))
        if cid is not None:
            predicted[cid].append(r["id"])
    true_pairs, pred_pairs = _pairs(truth), _pairs(predicted)
    tp = len(true_pairs & pred_pairs)
    precision = tp / len(pred_pairs) if pred_pairs else 1.0
    recall = tp / len(true_pairs)

    # Diagnostics on failure: which predicted clusters mix truths, which truths are split.
    mixed = {
        str(cid): sorted({r["truth"] for r in rows if r["id"] in ids})
        for cid, ids in predicted.items()
        if len({r["truth"] for r in rows if r["id"] in ids}) > 1
    }
    print(
        f"pairs true={len(true_pairs)} predicted={len(pred_pairs)} tp={tp} "
        f"precision={precision:.4f} recall={recall:.4f} reviewed={len(index.reviews)} mixed={mixed}"
    )
    assert precision >= 0.98, mixed
    assert recall >= 0.95


async def test_r2_never_merge_across_packages_without_exact_mpn() -> None:
    rows, index = await _run()
    by_component: dict[uuid.UUID, set[str]] = defaultdict(set)
    for r in rows:
        cid = index.assignments.get(uuid.UUID(r["id"]))
        if cid is not None and r["package"]:
            by_component[cid].add(r["package"])
    for cid, packages in by_component.items():
        if len(packages) > 1:
            # allowed only if every listing on the component has the same exact MPN key
            keys = {r["truth"] for r in rows if index.assignments.get(uuid.UUID(r["id"])) == cid}
            assert len(keys) == 1, (cid, packages, keys)


def test_r2_rule_directly() -> None:
    emb = HashingEmbedder().embed(["Infineon IRFZ44N MOSFET"])[0]
    base: dict[str, Any] = dict(manufacturer="Infineon", gtin=None, specs_norm={}, embedding=emb)
    cand = Candidate(id=uuid.uuid4(), mpn="IRFZ44N", package="TO-220", **base)
    # Fuzzy MPN (1 edit) on a different package → never attached
    lf = ListingFeatures(mpn="IRFZ44NS", mpn_trusted=True, package="D2PAK", title="IRFZ44NS", **base)
    d = match(lf, [cand])
    assert d.component_id != cand.id or d.action is not Action.ATTACH
    # Embedding-only path on a different package → never suggested
    lf2 = ListingFeatures(mpn=None, mpn_trusted=False, package="D2PAK", title="Infineon IRFZ44N MOSFET", **base)
    assert match(lf2, [cand]).component_id is None
    # Exact MPN across packages is allowed (distributor package naming differs)
    lf3 = ListingFeatures(mpn="IRFZ44N", mpn_trusted=True, package="TO-220AB", title="IRFZ44N", **base)
    assert match(lf3, [cand]).action is Action.ATTACH


def test_never_merge_across_manufacturers_without_gtin() -> None:
    a = Candidate(id=uuid.uuid4(), mpn="LM7805CT", manufacturer="onsemi")
    lf = ListingFeatures(
        mpn="LM7805CT",
        mpn_trusted=True,
        manufacturer="STMicroelectronics",
        gtin=None,
        package=None,
        title="LM7805CT",
        specs_norm={},
        embedding=None,
    )
    assert match(lf, [a]).component_id != a.id
    b = Candidate(id=uuid.uuid4(), mpn="X", manufacturer="onsemi", gtin="00012345678905")
    lf_gtin = ListingFeatures(
        mpn=None,
        mpn_trusted=False,
        manufacturer="Other",
        gtin="00012345678905",
        package=None,
        title="x",
        specs_norm={},
        embedding=None,
    )
    assert match(lf_gtin, [b]).component_id == b.id


async def test_r3_every_attach_has_audit_row() -> None:
    _rows, index = await _run()
    attached = set(index.assignments)
    audited = {r["listing_id"] for r in index.audit_rows if r["action"] == "attach"}
    assert attached <= audited
    created = {r["to_component"] for r in index.audit_rows if r["action"] == "create"}
    assert created == set(index.components)


@pytest.mark.parametrize(
    "trap",
    [
        ("esp32-wroom-32", "esp32-wroom-32d"),
        ("ams1117-3.3", "ams1117-5.0"),
        ("irfz44n", "irlz44n"),
        ("atmega328p-pu", "atmega328-pu"),
        ("lm7805ct", "l7805cv"),
        ("dht11", "dht22"),
    ],
)
async def test_lookalikes_stay_apart(trap: tuple[str, str]) -> None:
    rows, index = await _run()
    comps = {t: {index.assignments.get(uuid.UUID(r["id"])) for r in rows if r["truth"] == t} - {None} for t in trap}
    assert not (comps[trap[0]] & comps[trap[1]]), trap

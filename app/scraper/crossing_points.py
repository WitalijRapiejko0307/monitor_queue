"""Static reference list of border crossing points.

Slugs match the URL segments used on https://gpk.gov.by/situation-at-the-border/
(e.g. /situation-at-the-border/punkty-propuska/<slug>/) so they double as the
anchor text key used to locate rows inside the parsed tables.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrossingPointDef:
    slug: str
    name: str
    has_electronic_queue: bool
    is_active_for_sale: bool


# Full list as shown on the GPK page, in the order they appear in the tables.
CROSSING_POINTS: list[CrossingPointDef] = [
    CrossingPointDef("grigorov", "Григоровщина", True, True),
    CrossingPointDef("urbana", "Урбаны", True, True),
    CrossingPointDef("vidzy", "Видзы", False, False),
    CrossingPointDef("kotlovka", "Котловка", True, True),
    CrossingPointDef("losha", "Лоша", False, False),
    CrossingPointDef("stone_log", "Каменный Лог", True, True),
    CrossingPointDef("benekainys", "Бенякони", True, True),
    CrossingPointDef("privalka", "Привалка", False, False),
    CrossingPointDef("bruzgi", "Брузги", True, True),
    CrossingPointDef("berestovitsa", "Берестовица", True, True),
    CrossingPointDef("peschatka", "Песчатка", False, False),
    CrossingPointDef("kozlovichi", "Козловичи", True, True),
    CrossingPointDef("brest", "Брест", True, True),
    CrossingPointDef("domachevo", "Домачево", False, False),
    CrossingPointDef("tomashovka", "Томашовка", False, False),
    CrossingPointDef("oltush", "Олтуш", False, False),
    CrossingPointDef("mokrany", "Мокраны", False, False),
    CrossingPointDef("mohr", "Мохро", False, False),
    CrossingPointDef("nevel", "Невель", False, False),
    CrossingPointDef("up_terebezhov", "Верхний Теребежов", False, False),
    CrossingPointDef("glushkevichi", "Глушкевичи", False, False),
    CrossingPointDef("new_rudnia", "Новая Рудня", False, False),
    CrossingPointDef("oleksandrivka", "Александровка", False, False),
    CrossingPointDef("komarin", "Комарин", False, False),
    CrossingPointDef("nova_huta", "Новая Гута", False, False),
    CrossingPointDef("veselivka", "Веселовка", False, False),
]

# Points sold in the MVP: electronic-queue points only (see docs/implementation-plan.md §1,2).
SELLABLE_CROSSING_POINTS: list[CrossingPointDef] = [
    cp for cp in CROSSING_POINTS if cp.is_active_for_sale
]

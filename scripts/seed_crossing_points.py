"""Insert/update the static crossing-point reference list into the DB.

Run after migrations: `python -m scripts.seed_crossing_points`
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.models import CrossingPoint
from app.db.session import get_session
from app.scraper.crossing_points import CROSSING_POINTS


async def seed() -> None:
    async with get_session() as session:
        result = await session.execute(select(CrossingPoint))
        existing = {cp.slug: cp for cp in result.scalars().all()}

        for cp_def in CROSSING_POINTS:
            if cp_def.slug in existing:
                row = existing[cp_def.slug]
                row.name = cp_def.name
                row.has_electronic_queue = cp_def.has_electronic_queue
                row.is_active_for_sale = cp_def.is_active_for_sale
            else:
                session.add(
                    CrossingPoint(
                        slug=cp_def.slug,
                        name=cp_def.name,
                        has_electronic_queue=cp_def.has_electronic_queue,
                        is_active_for_sale=cp_def.is_active_for_sale,
                    )
                )
        await session.commit()
    print(f"Seeded {len(CROSSING_POINTS)} crossing points.")


if __name__ == "__main__":
    asyncio.run(seed())

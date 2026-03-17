"""CLI: 加载HR知识库种子数据

运行方式：
    cd apps/api-gateway
    python -m src.cli.seed_hr_knowledge
    python -m src.cli.seed_hr_knowledge --force   # 强制重新导入（忽略已存在检查）
"""
import asyncio
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _run(force: bool) -> None:
    from src.core.database import AsyncSessionLocal
    from src.services.hr.seed_service import HrSeedService

    async with AsyncSessionLocal() as session:
        service = HrSeedService(session)
        skip = not force

        rules_count = await service.load_rules(skip_if_exists=skip)
        skills_count = await service.load_skills(skip_if_exists=skip)

        logger.info(
            "Seed complete. Rules inserted: %d, Skills inserted: %d",
            rules_count,
            skills_count,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Load HR knowledge seed data")
    parser.add_argument("--force", action="store_true",
                        help="Re-insert even if data already exists")
    args = parser.parse_args()
    asyncio.run(_run(force=args.force))


if __name__ == "__main__":
    main()

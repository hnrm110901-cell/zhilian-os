"""
智链OS 本体层 Bootstrap
对标 Palantir Gotham 五层架构，初始化 Neo4j 11个本体对象、15个关系类型、约束和索引

运行方式：
    python -m src.ontology.bootstrap

环境变量：
    NEO4J_URI       Neo4j Bolt 地址，默认 bolt://localhost:7687
    NEO4J_USER      用户名，默认 neo4j
    NEO4J_PASSWORD  密码（必须设置）
"""

import os
import structlog
from neo4j import GraphDatabase, exceptions as neo4j_exc

logger = structlog.get_logger()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


# ── 唯一性约束 ─────────────────────────────────────────────────────────────────
CONSTRAINTS = [
    # 门店
    "CREATE CONSTRAINT unique_store_id IF NOT EXISTS FOR (s:Store) REQUIRE s.store_id IS UNIQUE",
    # 菜品
    "CREATE CONSTRAINT unique_dish_id IF NOT EXISTS FOR (d:Dish) REQUIRE d.dish_id IS UNIQUE",
    # 食材
    "CREATE CONSTRAINT unique_ingredient_id IF NOT EXISTS FOR (i:Ingredient) REQUIRE i.ing_id IS UNIQUE",
    # 供应商
    "CREATE CONSTRAINT unique_supplier_id IF NOT EXISTS FOR (s:Supplier) REQUIRE s.supplier_id IS UNIQUE",
    # 员工
    "CREATE CONSTRAINT unique_staff_id IF NOT EXISTS FOR (s:Staff) REQUIRE s.staff_id IS UNIQUE",
    # 订单
    "CREATE CONSTRAINT unique_order_id IF NOT EXISTS FOR (o:Order) REQUIRE o.order_id IS UNIQUE",
    # 损耗事件
    "CREATE CONSTRAINT unique_waste_event_id IF NOT EXISTS FOR (w:WasteEvent) REQUIRE w.event_id IS UNIQUE",
    # 设备
    "CREATE CONSTRAINT unique_equipment_id IF NOT EXISTS FOR (e:Equipment) REQUIRE e.equipment_id IS UNIQUE",
    # 公司（连锁总部）
    "CREATE CONSTRAINT unique_company_id IF NOT EXISTS FOR (c:Company) REQUIRE c.company_id IS UNIQUE",
    # BOM 复合主键：同一菜品同一版本唯一
    "CREATE CONSTRAINT unique_bom_key IF NOT EXISTS FOR (b:BOM) REQUIRE (b.dish_id, b.version) IS NODE KEY",
    # 库存快照
    "CREATE CONSTRAINT unique_snapshot_id IF NOT EXISTS FOR (n:InventorySnapshot) REQUIRE n.snapshot_id IS UNIQUE",
]

# ── 性能索引 ──────────────────────────────────────────────────────────────────
INDEXES = [
    # 库存快照时间索引（时间窗口查询核心）
    "CREATE INDEX inventory_snapshot_ts IF NOT EXISTS FOR (n:InventorySnapshot) ON (n.timestamp)",
    # 损耗事件时间索引
    "CREATE INDEX waste_event_ts IF NOT EXISTS FOR (w:WasteEvent) ON (w.occurred_at)",
    # 损耗事件食材+时间复合索引（根因查询）
    "CREATE INDEX waste_event_ing IF NOT EXISTS FOR (w:WasteEvent) ON (w.ingredient_id, w.occurred_at)",
    # 员工企业微信 ID（企微推送查询）
    "CREATE INDEX staff_wechat_id IF NOT EXISTS FOR (s:Staff) ON (s.wechat_id)",
    # 菜品分类索引
    "CREATE INDEX dish_category IF NOT EXISTS FOR (d:Dish) ON (d.category)",
    # BOM 生效日期索引（时间旅行查询）
    "CREATE INDEX bom_effective_date IF NOT EXISTS FOR (b:BOM) ON (b.effective_date)",
    # 订单时间索引
    "CREATE INDEX order_ts IF NOT EXISTS FOR (o:Order) ON (o.placed_at)",
]

# ── 关系类型说明（文档用途，Neo4j 关系类型无需预声明） ──────────────────────────
RELATION_TYPES = """
层级关系：
  (Company)-[:HAS_STORE]->(Store)
  (Store)-[:HAS_DISH]->(Dish)
  (Dish)-[:HAS_BOM]->(BOM)
  (BOM)-[:REQUIRES {qty, unit}]->(Ingredient)
  (BOM)-[:SUCCEEDED_BY]->(BOM)         # 配方版本演变链

操作关系：
  (Order)-[:CONTAINS {qty, unit_price}]->(Dish)
  (Order)-[:PLACED_BY]->(Staff)
  (Order)-[:PLACED_AT]->(Store)

库存关系：
  (InventorySnapshot)-[:SNAPSHOT_OF]->(Ingredient)
  (Ingredient)-[:SUPPLIED_BY {lead_time, reliability, quality_score}]->(Supplier)
  (Equipment)-[:STORES]->(Ingredient)

损耗推理关系（推理层写入）：
  (WasteEvent)-[:INVOLVES]->(Ingredient)
  (WasteEvent)-[:HAPPENED_DURING]->(Shift)
  (WasteEvent)-[:ROOT_CAUSE {confidence, evidence}]->(Staff)
  (WasteEvent)-[:ROOT_CAUSE {confidence, evidence}]->(Ingredient)
  (WasteEvent)-[:ROOT_CAUSE {confidence, evidence}]->(Equipment)
"""


def _run_schema(tx, statements: list[str]) -> list[str]:
    """执行一批 DDL 语句，返回成功执行的语句列表"""
    executed = []
    for stmt in statements:
        tx.run(stmt)
        executed.append(stmt.split("FOR")[0].strip())
    return executed


def bootstrap(uri: str = NEO4J_URI, user: str = NEO4J_USER, password: str = NEO4J_PASSWORD) -> None:
    """
    初始化智链OS本体 Schema

    멱等性：多次执行安全（IF NOT EXISTS 保证）
    """
    if not password:
        raise EnvironmentError(
            "NEO4J_PASSWORD 未设置。请在 .env 中配置 NEO4J_PASSWORD=<密码>"
        )

    logger.info("正在连接 Neo4j", uri=uri, user=user)

    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        driver.verify_connectivity()
        logger.info("Neo4j 连接成功")

        with driver.session() as session:
            # 约束
            executed = session.execute_write(_run_schema, CONSTRAINTS)
            logger.info("本体约束创建完成", count=len(executed), items=executed)

            # 索引
            executed = session.execute_write(_run_schema, INDEXES)
            logger.info("本体索引创建完成", count=len(executed), items=executed)

        logger.info(
            "智链OS本体 Schema 初始化完成",
            objects=11,
            relations=15,
            constraints=len(CONSTRAINTS),
            indexes=len(INDEXES),
        )


def seed_demo_store(
    uri: str = NEO4J_URI,
    user: str = NEO4J_USER,
    password: str = NEO4J_PASSWORD,
    store_id: str = "XJ-CHANGSHA-001",
    store_name: str = "徐记海鲜（长沙旗舰店）",
) -> None:
    """
    写入演示门店节点（用于 POC 开发）

    멱등：MERGE 保证不重复创建
    """
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session() as session:
            session.run(
                """
                MERGE (s:Store {store_id: $store_id})
                ON CREATE SET
                    s.name       = $name,
                    s.tier       = 'premium',
                    s.address    = '长沙市天心区',
                    s.capacity   = 150,
                    s.created_at = timestamp()
                ON MATCH SET
                    s.name       = $name
                """,
                store_id=store_id,
                name=store_name,
            )
            logger.info("演示门店节点写入完成", store_id=store_id, name=store_name)


if __name__ == "__main__":
    bootstrap()
    seed_demo_store()

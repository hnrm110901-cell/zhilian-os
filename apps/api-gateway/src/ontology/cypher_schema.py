"""
本体图谱 Cypher：约束与索引（用于 Neo4j 初始化）
"""
from .schema import NodeLabel, NODE_ID_PROP, ExtensionNodeLabel, EXTENSION_ID_PROP

# 创建唯一性约束（保证节点唯一，便于 MERGE）
def constraints_cypher() -> list[str]:
    statements = []
    for label in NodeLabel:
        prop = NODE_ID_PROP.get(label.value)
        if prop:
            # Neo4j 5.x: CREATE CONSTRAINT ... FOR (n:Label) REQUIRE n.prop IS UNIQUE
            name = f"constraint_{label.value}_{prop}_unique"
            statements.append(
                f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                f"FOR (n:{label.value}) REQUIRE n.{prop} IS UNIQUE"
            )
    return statements


# 徐记 POC 扩展约束（可选，init_schema 时一并创建）
def extension_constraints_cypher() -> list[str]:
    statements = []
    for label in ExtensionNodeLabel:
        prop = EXTENSION_ID_PROP.get(label.value)
        if prop:
            name = f"constraint_{label.value}_{prop}_unique"
            statements.append(
                f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                f"FOR (n:{label.value}) REQUIRE n.{prop} IS UNIQUE"
            )
    return statements


# 可选：索引以加速按属性查询
def indexes_cypher() -> list[str]:
    return [
        f"CREATE INDEX index_Store_tenant IF NOT EXISTS FOR (n:Store) ON (n.tenant_id)",
        f"CREATE INDEX index_Dish_store IF NOT EXISTS FOR (n:Dish) ON (n.store_id)",
        f"CREATE INDEX index_Order_store IF NOT EXISTS FOR (n:Order) ON (n.store_id)",
        f"CREATE INDEX index_Order_ts IF NOT EXISTS FOR (n:Order) ON (n.timestamp)",
        f"CREATE INDEX index_InventorySnapshot_ts IF NOT EXISTS FOR (n:InventorySnapshot) ON (n.ts)",
        f"CREATE INDEX index_BOM_dish_version IF NOT EXISTS FOR (n:BOM) ON (n.dish_id, n.version)",
        f"CREATE INDEX index_Action_status IF NOT EXISTS FOR (n:Action) ON (n.status)",
        f"CREATE INDEX index_Equipment_store IF NOT EXISTS FOR (n:Equipment) ON (n.store_id)",
        f"CREATE INDEX index_TrainingModule_skill IF NOT EXISTS FOR (n:TrainingModule) ON (n.skill_gap)",
        # 徐记扩展
        "CREATE INDEX index_LiveSeafood_store IF NOT EXISTS FOR (n:LiveSeafood) ON (n.store_id)",
        "CREATE INDEX index_SeafoodPool_store IF NOT EXISTS FOR (n:SeafoodPool) ON (n.store_id)",
    ]

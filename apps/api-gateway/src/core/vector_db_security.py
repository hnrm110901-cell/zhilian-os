"""
向量数据库安全防护
Vector Database Security

核心功能：
1. 租户级Collection物理隔离
2. Payload Filter强制校验
3. 中间件层拦截验证
4. 防止跨租户数据泄露

安全等级：P0 CRITICAL
"""

from typing import Dict, List, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import logging

logger = logging.getLogger(__name__)


class VectorDBSecurityException(Exception):
    """向量数据库安全异常"""
    pass


class VectorDBSecurity:
    """向量数据库安全防护"""

    def __init__(self, qdrant_client: QdrantClient):
        self.client = qdrant_client
        self.tenant_collections = {}  # 租户Collection映射

    def get_tenant_collection(self, tenant_id: str, base_collection: str) -> str:
        """
        获取租户专属Collection名称

        每个租户使用独立的Collection，实现物理级隔离

        Args:
            tenant_id: 租户ID
            base_collection: 基础Collection名称

        Returns:
            租户专属Collection名称
        """
        if not tenant_id:
            raise VectorDBSecurityException("tenant_id不能为空")

        collection_name = f"tenant_{tenant_id}_{base_collection}"

        logger.info(f"Tenant {tenant_id} using collection: {collection_name}")

        return collection_name

    def enforce_tenant_filter(
        self,
        tenant_id: str,
        query_filter: Optional[Filter] = None
    ) -> Filter:
        """
        强制租户过滤

        在所有查询中强制添加tenant_id过滤条件

        Args:
            tenant_id: 租户ID
            query_filter: 原始查询过滤器

        Returns:
            增强后的过滤器
        """
        if not tenant_id:
            raise VectorDBSecurityException("tenant_id不能为空")

        # 创建租户过滤条件
        tenant_condition = FieldCondition(
            key="tenant_id",
            match=MatchValue(value=tenant_id)
        )

        # 如果已有过滤器，合并
        if query_filter:
            if query_filter.must:
                query_filter.must.append(tenant_condition)
            else:
                query_filter.must = [tenant_condition]
        else:
            query_filter = Filter(must=[tenant_condition])

        logger.debug(f"Enforced tenant filter for tenant {tenant_id}")

        return query_filter

    def validate_tenant_access(
        self,
        tenant_id: str,
        collection_name: str
    ) -> bool:
        """
        验证租户是否有权访问指定Collection

        Args:
            tenant_id: 租户ID
            collection_name: Collection名称

        Returns:
            是否有权访问
        """
        # 检查Collection名称是否包含租户ID
        expected_prefix = f"tenant_{tenant_id}_"

        if not collection_name.startswith(expected_prefix):
            logger.error(
                f"Tenant {tenant_id} attempted to access "
                f"unauthorized collection: {collection_name}"
            )
            raise VectorDBSecurityException(
                f"租户{tenant_id}无权访问Collection: {collection_name}"
            )

        return True

    async def create_tenant_collection(
        self,
        tenant_id: str,
        base_collection: str,
        vector_size: int,
        distance: str = "Cosine"
    ):
        """
        创建租户专属Collection

        Args:
            tenant_id: 租户ID
            base_collection: 基础Collection名称
            vector_size: 向量维度
            distance: 距离度量方式
        """
        collection_name = self.get_tenant_collection(tenant_id, base_collection)

        # 检查Collection是否已存在
        collections = self.client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)

        if not exists:
            # 创建Collection
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "size": vector_size,
                    "distance": distance
                }
            )

            logger.info(f"Created tenant collection: {collection_name}")

        # 记录租户Collection映射
        if tenant_id not in self.tenant_collections:
            self.tenant_collections[tenant_id] = []

        if collection_name not in self.tenant_collections[tenant_id]:
            self.tenant_collections[tenant_id].append(collection_name)

    async def search_with_security(
        self,
        tenant_id: str,
        base_collection: str,
        query_vector: List[float],
        limit: int = 10,
        query_filter: Optional[Filter] = None
    ) -> List[Dict]:
        """
        安全的向量搜索

        Args:
            tenant_id: 租户ID
            base_collection: 基础Collection名称
            query_vector: 查询向量
            limit: 返回数量
            query_filter: 查询过滤器

        Returns:
            搜索结果
        """
        # 1. 获取租户专属Collection
        collection_name = self.get_tenant_collection(tenant_id, base_collection)

        # 2. 验证访问权限
        self.validate_tenant_access(tenant_id, collection_name)

        # 3. 强制租户过滤
        secure_filter = self.enforce_tenant_filter(tenant_id, query_filter)

        # 4. 执行搜索
        try:
            results = self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                query_filter=secure_filter
            )

            logger.info(
                f"Secure search for tenant {tenant_id}: "
                f"{len(results)} results"
            )

            return [
                {
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload
                }
                for result in results
            ]

        except Exception as e:
            logger.error(f"Secure search failed: {e}")
            raise VectorDBSecurityException(f"搜索失败: {e}")

    async def upsert_with_security(
        self,
        tenant_id: str,
        base_collection: str,
        points: List[Dict]
    ):
        """
        安全的向量插入/更新

        Args:
            tenant_id: 租户ID
            base_collection: 基础Collection名称
            points: 数据点列表
        """
        # 1. 获取租户专属Collection
        collection_name = self.get_tenant_collection(tenant_id, base_collection)

        # 2. 验证访问权限
        self.validate_tenant_access(tenant_id, collection_name)

        # 3. 强制添加tenant_id到payload
        for point in points:
            if "payload" not in point:
                point["payload"] = {}

            # 强制设置tenant_id（防止伪造）
            point["payload"]["tenant_id"] = tenant_id

        # 4. 执行插入
        try:
            self.client.upsert(
                collection_name=collection_name,
                points=points
            )

            logger.info(
                f"Secure upsert for tenant {tenant_id}: "
                f"{len(points)} points"
            )

        except Exception as e:
            logger.error(f"Secure upsert failed: {e}")
            raise VectorDBSecurityException(f"插入失败: {e}")

    async def delete_with_security(
        self,
        tenant_id: str,
        base_collection: str,
        point_ids: List[str]
    ):
        """
        安全的向量删除

        Args:
            tenant_id: 租户ID
            base_collection: 基础Collection名称
            point_ids: 要删除的点ID列表
        """
        # 1. 获取租户专属Collection
        collection_name = self.get_tenant_collection(tenant_id, base_collection)

        # 2. 验证访问权限
        self.validate_tenant_access(tenant_id, collection_name)

        # 3. 执行删除
        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=point_ids
            )

            logger.info(
                f"Secure delete for tenant {tenant_id}: "
                f"{len(point_ids)} points"
            )

        except Exception as e:
            logger.error(f"Secure delete failed: {e}")
            raise VectorDBSecurityException(f"删除失败: {e}")

    def audit_tenant_access(
        self,
        tenant_id: str,
        operation: str,
        collection_name: str,
        details: Optional[Dict] = None
    ):
        """
        审计租户访问

        Args:
            tenant_id: 租户ID
            operation: 操作类型（search/upsert/delete）
            collection_name: Collection名称
            details: 操作详情
        """
        audit_log = {
            "timestamp": logger.handlers[0].formatter.formatTime(
                logging.LogRecord(
                    name="audit",
                    level=logging.INFO,
                    pathname="",
                    lineno=0,
                    msg="",
                    args=(),
                    exc_info=None
                )
            ),
            "tenant_id": tenant_id,
            "operation": operation,
            "collection_name": collection_name,
            "details": details or {}
        }

        logger.info(f"Vector DB Audit: {audit_log}")

        # TODO: 写入专门的审计日志系统

    def get_tenant_statistics(self, tenant_id: str) -> Dict[str, Any]:
        """
        获取租户统计信息

        Args:
            tenant_id: 租户ID

        Returns:
            统计信息
        """
        collections = self.tenant_collections.get(tenant_id, [])

        stats = {
            "tenant_id": tenant_id,
            "total_collections": len(collections),
            "collections": []
        }

        for collection_name in collections:
            try:
                info = self.client.get_collection(collection_name)
                stats["collections"].append({
                    "name": collection_name,
                    "vectors_count": info.vectors_count,
                    "points_count": info.points_count
                })
            except Exception as e:
                logger.error(f"Failed to get collection info: {e}")

        return stats


# 全局实例（需要在应用启动时初始化）
_vector_db_security = None


def init_vector_db_security(qdrant_client: QdrantClient):
    """初始化向量数据库安全服务"""
    global _vector_db_security
    _vector_db_security = VectorDBSecurity(qdrant_client)
    logger.info("Vector DB Security initialized")


def get_vector_db_security() -> VectorDBSecurity:
    """获取向量数据库安全服务实例"""
    if _vector_db_security is None:
        raise VectorDBSecurityException(
            "Vector DB Security not initialized. "
            "Call init_vector_db_security() first."
        )
    return _vector_db_security

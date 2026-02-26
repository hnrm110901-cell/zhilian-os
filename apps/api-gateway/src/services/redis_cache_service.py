"""
Redis缓存服务
Redis Cache Service

提供统一的缓存接口，支持多种数据类型和过期策略
"""
import os
import redis.asyncio as redis
import json
import structlog
from typing import Any, Optional, Union, List
from datetime import timedelta
from ..core.config import settings

logger = structlog.get_logger()


class RedisCacheService:
    """Redis缓存服务"""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._initialized = False

    async def initialize(self):
        """初始化Redis连接"""
        if self._initialized:
            return

        try:
            self._redis = await redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
            )
            # 测试连接
            await self._redis.ping()
            self._initialized = True
            logger.info("Redis缓存服务初始化成功")
        except redis.AuthenticationError as e:
            logger.error("Redis认证失败，请检查密码配置", error=str(e))
            raise
        except redis.ConnectionError as e:
            logger.error("Redis连接失败，请检查地址和端口", error=str(e))
            raise
        except Exception as e:
            logger.error("Redis缓存服务初始化失败", error=str(e))
            raise

    async def close(self):
        """关闭Redis连接"""
        if self._redis:
            await self._redis.close()
            self._initialized = False
            logger.info("Redis缓存服务已关闭")

    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，如果不存在返回None
        """
        try:
            if not self._initialized:
                await self.initialize()

            value = await self._redis.get(key)
            if value is None:
                return None

            # 尝试解析JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning("Redis连接/超时，缓存读取降级", key=key, error=str(e))
            return None
        except Exception as e:
            logger.error("获取缓存失败", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[Union[int, timedelta]] = None
    ) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            expire: 过期时间（秒或timedelta对象）

        Returns:
            是否设置成功
        """
        try:
            if not self._initialized:
                await self.initialize()

            # 序列化值
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            elif not isinstance(value, str):
                value = str(value)

            # 设置过期时间
            if isinstance(expire, timedelta):
                expire = int(expire.total_seconds())

            if expire:
                await self._redis.setex(key, expire, value)
            else:
                await self._redis.set(key, value)

            return True

        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning("Redis连接/超时，缓存写入降级", key=key, error=str(e))
            return False
        except Exception as e:
            logger.error("设置缓存失败", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """
        删除缓存

        Args:
            key: 缓存键

        Returns:
            是否删除成功
        """
        try:
            if not self._initialized:
                await self.initialize()

            await self._redis.delete(key)
            return True

        except Exception as e:
            logger.error("删除缓存失败", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """
        检查缓存是否存在

        Args:
            key: 缓存键

        Returns:
            是否存在
        """
        try:
            if not self._initialized:
                await self.initialize()

            return await self._redis.exists(key) > 0

        except Exception as e:
            logger.error("检查缓存存在失败", key=key, error=str(e))
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        """
        设置缓存过期时间

        Args:
            key: 缓存键
            seconds: 过期秒数

        Returns:
            是否设置成功
        """
        try:
            if not self._initialized:
                await self.initialize()

            return await self._redis.expire(key, seconds)

        except Exception as e:
            logger.error("设置缓存过期时间失败", key=key, error=str(e))
            return False

    async def ttl(self, key: str) -> int:
        """
        获取缓存剩余时间

        Args:
            key: 缓存键

        Returns:
            剩余秒数，-1表示永不过期，-2表示不存在
        """
        try:
            if not self._initialized:
                await self.initialize()

            return await self._redis.ttl(key)

        except Exception as e:
            logger.error("获取缓存TTL失败", key=key, error=str(e))
            return -2

    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """
        递增计数器

        Args:
            key: 缓存键
            amount: 递增量

        Returns:
            递增后的值
        """
        try:
            if not self._initialized:
                await self.initialize()

            return await self._redis.incrby(key, amount)

        except Exception as e:
            logger.error("递增计数器失败", key=key, error=str(e))
            return None

    async def decr(self, key: str, amount: int = 1) -> Optional[int]:
        """
        递减计数器

        Args:
            key: 缓存键
            amount: 递减量

        Returns:
            递减后的值
        """
        try:
            if not self._initialized:
                await self.initialize()

            return await self._redis.decrby(key, amount)

        except Exception as e:
            logger.error("递减计数器失败", key=key, error=str(e))
            return None

    async def hget(self, name: str, key: str) -> Optional[Any]:
        """
        获取哈希表字段值

        Args:
            name: 哈希表名
            key: 字段名

        Returns:
            字段值
        """
        try:
            if not self._initialized:
                await self.initialize()

            value = await self._redis.hget(name, key)
            if value is None:
                return None

            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            logger.error("获取哈希表字段失败", name=name, key=key, error=str(e))
            return None

    async def hset(self, name: str, key: str, value: Any) -> bool:
        """
        设置哈希表字段值

        Args:
            name: 哈希表名
            key: 字段名
            value: 字段值

        Returns:
            是否设置成功
        """
        try:
            if not self._initialized:
                await self.initialize()

            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            elif not isinstance(value, str):
                value = str(value)

            await self._redis.hset(name, key, value)
            return True

        except Exception as e:
            logger.error("设置哈希表字段失败", name=name, key=key, error=str(e))
            return False

    async def hgetall(self, name: str) -> dict:
        """
        获取哈希表所有字段

        Args:
            name: 哈希表名

        Returns:
            所有字段的字典
        """
        try:
            if not self._initialized:
                await self.initialize()

            data = await self._redis.hgetall(name)
            result = {}

            for key, value in data.items():
                try:
                    result[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[key] = value

            return result

        except Exception as e:
            logger.error("获取哈希表所有字段失败", name=name, error=str(e))
            return {}

    async def hdel(self, name: str, *keys: str) -> bool:
        """
        删除哈希表字段

        Args:
            name: 哈希表名
            keys: 字段名列表

        Returns:
            是否删除成功
        """
        try:
            if not self._initialized:
                await self.initialize()

            await self._redis.hdel(name, *keys)
            return True

        except Exception as e:
            logger.error("删除哈希表字段失败", name=name, keys=keys, error=str(e))
            return False

    async def lpush(self, key: str, *values: Any) -> Optional[int]:
        """
        从列表左侧推入元素

        Args:
            key: 列表键
            values: 要推入的值

        Returns:
            列表长度
        """
        try:
            if not self._initialized:
                await self.initialize()

            serialized_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    serialized_values.append(json.dumps(value, ensure_ascii=False))
                else:
                    serialized_values.append(str(value))

            return await self._redis.lpush(key, *serialized_values)

        except Exception as e:
            logger.error("列表左推失败", key=key, error=str(e))
            return None

    async def rpush(self, key: str, *values: Any) -> Optional[int]:
        """
        从列表右侧推入元素

        Args:
            key: 列表键
            values: 要推入的值

        Returns:
            列表长度
        """
        try:
            if not self._initialized:
                await self.initialize()

            serialized_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    serialized_values.append(json.dumps(value, ensure_ascii=False))
                else:
                    serialized_values.append(str(value))

            return await self._redis.rpush(key, *serialized_values)

        except Exception as e:
            logger.error("列表右推失败", key=key, error=str(e))
            return None

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """
        获取列表范围内的元素

        Args:
            key: 列表键
            start: 起始索引
            end: 结束索引

        Returns:
            元素列表
        """
        try:
            if not self._initialized:
                await self.initialize()

            values = await self._redis.lrange(key, start, end)
            result = []

            for value in values:
                try:
                    result.append(json.loads(value))
                except (json.JSONDecodeError, TypeError):
                    result.append(value)

            return result

        except Exception as e:
            logger.error("获取列表范围失败", key=key, error=str(e))
            return []

    async def clear_pattern(self, pattern: str) -> int:
        """
        清除匹配模式的所有键

        Args:
            pattern: 键模式（支持*通配符）

        Returns:
            删除的键数量
        """
        try:
            if not self._initialized:
                await self.initialize()

            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self._redis.delete(*keys)

            logger.info("清除缓存模式", pattern=pattern, count=len(keys))
            return len(keys)

        except Exception as e:
            logger.error("清除缓存模式失败", pattern=pattern, error=str(e))
            return 0


# 创建全局实例
redis_cache = RedisCacheService()

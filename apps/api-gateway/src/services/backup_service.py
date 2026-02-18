"""
数据备份与恢复服务
"""
import os
import gzip
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import structlog
import asyncio
from sqlalchemy import text

from src.core.database import engine, AsyncSessionLocal
from src.core.config import settings

logger = structlog.get_logger()


class BackupService:
    """数据备份服务"""

    def __init__(self):
        self.backup_dir = Path(settings.BACKUP_DIR if hasattr(settings, 'BACKUP_DIR') else './backups')
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.max_backups = getattr(settings, 'MAX_BACKUPS', 30)  # 保留最近30个备份

    async def create_backup(self, backup_type: str = "manual") -> Dict[str, Any]:
        """创建数据库备份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{backup_type}_{timestamp}.sql"
        backup_path = self.backup_dir / backup_name
        compressed_path = self.backup_dir / f"{backup_name}.gz"

        try:
            logger.info("backup_started", backup_name=backup_name)

            # 使用pg_dump创建备份
            db_url = str(settings.DATABASE_URL)

            # 解析数据库连接信息
            # postgresql+asyncpg://user:pass@host:port/dbname
            if "postgresql" in db_url:
                # 提取连接信息
                parts = db_url.replace("postgresql+asyncpg://", "").replace("postgresql://", "")
                if "@" in parts:
                    auth, host_db = parts.split("@")
                    if ":" in auth:
                        user, password = auth.split(":")
                    else:
                        user = auth
                        password = ""

                    if "/" in host_db:
                        host_port, dbname = host_db.split("/")
                        if ":" in host_port:
                            host, port = host_port.split(":")
                        else:
                            host = host_port
                            port = "5432"
                    else:
                        host = host_db
                        port = "5432"
                        dbname = "zhilian_os"
                else:
                    # 简化的连接字符串
                    host = "localhost"
                    port = "5432"
                    dbname = "zhilian_os"
                    user = "postgres"
                    password = ""

                # 设置环境变量以避免密码提示
                env = os.environ.copy()
                if password:
                    env['PGPASSWORD'] = password

                # 执行pg_dump
                cmd = f'pg_dump -h {host} -p {port} -U {user} -d {dbname} -F p -f {backup_path}'

                process = await asyncio.create_subprocess_shell(
                    cmd,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    logger.error("backup_failed", error=error_msg)
                    raise Exception(f"Backup failed: {error_msg}")

                # 压缩备份文件
                with open(backup_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)

                # 删除未压缩的文件
                backup_path.unlink()

                # 获取文件大小
                file_size = compressed_path.stat().st_size

                logger.info("backup_completed",
                           backup_name=f"{backup_name}.gz",
                           size_bytes=file_size)

                # 清理旧备份
                await self._cleanup_old_backups()

                return {
                    "success": True,
                    "backup_name": f"{backup_name}.gz",
                    "backup_path": str(compressed_path),
                    "size_bytes": file_size,
                    "size_mb": round(file_size / 1024 / 1024, 2),
                    "created_at": datetime.now().isoformat(),
                    "type": backup_type,
                }
            else:
                raise Exception("Unsupported database type")

        except Exception as e:
            logger.error("backup_error", error=str(e))
            # 清理失败的备份文件
            if backup_path.exists():
                backup_path.unlink()
            if compressed_path.exists():
                compressed_path.unlink()
            raise

    async def list_backups(self) -> List[Dict[str, Any]]:
        """列出所有备份"""
        backups = []

        for backup_file in sorted(self.backup_dir.glob("backup_*.sql.gz"), reverse=True):
            stat = backup_file.stat()

            # 从文件名解析信息
            name = backup_file.stem.replace(".sql", "")  # 移除.sql后缀
            parts = name.split("_")

            backup_type = parts[1] if len(parts) > 1 else "unknown"
            timestamp_str = "_".join(parts[2:]) if len(parts) > 2 else ""

            try:
                created_at = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            except:
                created_at = datetime.fromtimestamp(stat.st_mtime)

            backups.append({
                "name": backup_file.name,
                "path": str(backup_file),
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created_at": created_at.isoformat(),
                "type": backup_type,
                "age_days": (datetime.now() - created_at).days,
            })

        return backups

    async def restore_backup(self, backup_name: str) -> Dict[str, Any]:
        """恢复数据库备份"""
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_name}")

        try:
            logger.info("restore_started", backup_name=backup_name)

            # 解压备份文件
            sql_path = backup_path.with_suffix('')  # 移除.gz后缀

            with gzip.open(backup_path, 'rb') as f_in:
                with open(sql_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # 解析数据库连接信息
            db_url = str(settings.DATABASE_URL)

            if "postgresql" in db_url:
                parts = db_url.replace("postgresql+asyncpg://", "").replace("postgresql://", "")
                if "@" in parts:
                    auth, host_db = parts.split("@")
                    if ":" in auth:
                        user, password = auth.split(":")
                    else:
                        user = auth
                        password = ""

                    if "/" in host_db:
                        host_port, dbname = host_db.split("/")
                        if ":" in host_port:
                            host, port = host_port.split(":")
                        else:
                            host = host_port
                            port = "5432"
                    else:
                        host = host_db
                        port = "5432"
                        dbname = "zhilian_os"
                else:
                    host = "localhost"
                    port = "5432"
                    dbname = "zhilian_os"
                    user = "postgres"
                    password = ""

                # 设置环境变量
                env = os.environ.copy()
                if password:
                    env['PGPASSWORD'] = password

                # 执行psql恢复
                cmd = f'psql -h {host} -p {port} -U {user} -d {dbname} -f {sql_path}'

                process = await asyncio.create_subprocess_shell(
                    cmd,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    logger.error("restore_failed", error=error_msg)
                    raise Exception(f"Restore failed: {error_msg}")

                # 删除解压的SQL文件
                sql_path.unlink()

                logger.info("restore_completed", backup_name=backup_name)

                return {
                    "success": True,
                    "backup_name": backup_name,
                    "restored_at": datetime.now().isoformat(),
                }
            else:
                raise Exception("Unsupported database type")

        except Exception as e:
            logger.error("restore_error", error=str(e))
            # 清理解压的文件
            if sql_path.exists():
                sql_path.unlink()
            raise

    async def delete_backup(self, backup_name: str) -> Dict[str, Any]:
        """删除备份文件"""
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_name}")

        try:
            backup_path.unlink()
            logger.info("backup_deleted", backup_name=backup_name)

            return {
                "success": True,
                "backup_name": backup_name,
                "deleted_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error("delete_backup_error", error=str(e))
            raise

    async def _cleanup_old_backups(self):
        """清理旧备份，只保留最近的N个"""
        backups = await self.list_backups()

        if len(backups) > self.max_backups:
            # 删除最旧的备份
            backups_to_delete = backups[self.max_backups:]

            for backup in backups_to_delete:
                try:
                    await self.delete_backup(backup["name"])
                    logger.info("old_backup_cleaned", backup_name=backup["name"])
                except Exception as e:
                    logger.error("cleanup_error", backup_name=backup["name"], error=str(e))

    async def verify_backup(self, backup_name: str) -> Dict[str, Any]:
        """验证备份文件完整性"""
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_name}")

        try:
            # 尝试解压并读取文件头
            with gzip.open(backup_path, 'rb') as f:
                # 读取前1KB检查是否为有效的SQL文件
                header = f.read(1024).decode('utf-8', errors='ignore')

                is_valid = (
                    'PostgreSQL database dump' in header or
                    'CREATE TABLE' in header or
                    'INSERT INTO' in header
                )

            return {
                "valid": is_valid,
                "backup_name": backup_name,
                "verified_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error("verify_backup_error", error=str(e))
            return {
                "valid": False,
                "backup_name": backup_name,
                "error": str(e),
                "verified_at": datetime.now().isoformat(),
            }


# 全局服务实例
backup_service = BackupService()


def get_backup_service() -> BackupService:
    """获取备份服务实例"""
    return backup_service

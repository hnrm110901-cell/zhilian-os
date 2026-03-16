"""
数据备份服务
"""

import asyncio
import gzip
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import structlog

logger = structlog.get_logger()

_BACKUP_DIR = os.getenv("BACKUP_DIR", "/tmp/zhilian_backups")
_DATABASE_URL = os.getenv("DATABASE_URL", "")
_MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", "10"))


class BackupService:
    """PostgreSQL 数据库备份服务（pg_dump + gzip）"""

    def __init__(self):
        self.backup_dir = Path(_BACKUP_DIR)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.max_backups = _MAX_BACKUPS

    async def create_backup(self, backup_type: str = "manual") -> Dict[str, Any]:
        """创建数据库备份（pg_dump → gzip）。

        Args:
            backup_type: 备份类型，如 "manual" / "auto"

        Returns:
            {"success": True, "backup_name": ..., "type": ..., "size_bytes": ...}

        Raises:
            Exception: 当 pg_dump 返回非零退出码时
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{backup_type}_{timestamp}.sql"
        backup_path = self.backup_dir / backup_name
        compressed_path = self.backup_dir / f"{backup_name}.gz"

        db_url = _DATABASE_URL
        cmd = f'pg_dump "{db_url}" -f "{backup_path}"'

        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"Backup failed: {stderr.decode()}")

        # 压缩备份文件
        with open(backup_path, "rb") as f_in:
            with gzip.open(str(compressed_path), "wb") as f_out:
                f_out.write(f_in.read())
        if backup_path.exists():
            backup_path.unlink(missing_ok=True)

        size_bytes = compressed_path.stat().st_size

        await self._cleanup_old_backups()

        logger.info("Backup created", backup_name=f"{backup_name}.gz", size_bytes=size_bytes)
        return {
            "success": True,
            "backup_name": f"{backup_name}.gz",
            "type": backup_type,
            "size_bytes": size_bytes,
        }

    async def list_backups(self) -> List[Dict[str, Any]]:
        """列出所有备份文件，按修改时间降序排列。"""
        files = list(self.backup_dir.glob("*.gz"))
        backups = []
        for f in files:
            # 从文件名解析类型：backup_{type}_{timestamp}.sql.gz
            parts = f.name.split("_")
            btype = parts[1] if len(parts) >= 2 else "unknown"
            stat = f.stat()
            backups.append(
                {
                    "name": f.name,
                    "type": btype,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups

    async def delete_backup(self, backup_name: str) -> Dict[str, Any]:
        """删除指定备份文件。

        Raises:
            FileNotFoundError: 备份文件不存在
        """
        backup_path = self.backup_dir / backup_name
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_name}")
        backup_path.unlink()
        return {"success": True, "backup_name": backup_name}

    async def verify_backup(self, backup_name: str) -> Dict[str, Any]:
        """验证备份文件是否有效（可读取且包含 PostgreSQL dump 标记）。"""
        backup_path = self.backup_dir / backup_name
        if not backup_path.exists():
            return {"valid": False, "backup_name": backup_name, "error": "File not found"}

        try:
            with gzip.open(str(backup_path), "rb") as f:
                header = f.read(1024)
            valid = b"PostgreSQL" in header or b"CREATE" in header
        except Exception as e:
            return {"valid": False, "backup_name": backup_name, "error": str(e)}

        return {"valid": valid, "backup_name": backup_name}

    async def _cleanup_old_backups(self) -> None:
        """保留最新 max_backups 个备份，删除多余的旧备份。"""
        backups = await self.list_backups()
        if len(backups) > self.max_backups:
            to_delete = backups[self.max_backups :]
            for backup in to_delete:
                await self.delete_backup(backup["name"])


backup_service = BackupService()

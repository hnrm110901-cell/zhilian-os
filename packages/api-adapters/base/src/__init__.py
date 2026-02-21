"""API适配器基础模块"""
from .adapter import BaseAdapter, APIError
from .mapper import DataMapper

__all__ = ["BaseAdapter", "APIError", "DataMapper"]

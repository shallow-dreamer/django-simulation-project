from typing import List, Optional, Union, Callable
from pathlib import Path
import hashlib
import os

class FilePathHandler:
    """文件路径处理器"""
    
    def __init__(self, path_join_func: Callable = None):
        self.path_join_func = path_join_func or os.path.join

    def _get_single_path(self, param, args, kwargs) -> Optional[str]:
        """获取单个路径参数"""
        if isinstance(param, int) and len(args) > param:
            return str(args[param])
        elif isinstance(param, str) and param in kwargs:
            return str(kwargs[param])
        return None

    def get_paths(self, file_params, args=None, kwargs=None) -> List[str]:
        """获取所有文件路径"""
        args = args or ()
        kwargs = kwargs or {}
        
        if isinstance(file_params, (str, int)):
            return self._handle_single_param(file_params, args, kwargs)
        elif isinstance(file_params, list):
            return self._handle_path_list(file_params, args, kwargs)
        elif isinstance(file_params, dict):
            return self._handle_path_dict(file_params, args, kwargs)
        return []

    def _handle_single_param(self, param, args, kwargs) -> List[str]:
        """处理单个参数"""
        path = self._get_single_path(param, args, kwargs)
        return [path] if path else []

    def _handle_path_list(self, params, args, kwargs) -> List[str]:
        """处理路径列表"""
        path_parts = []
        for param in params:
            part = self._get_single_path(param, args, kwargs)
            if part:
                path_parts.append(part)
        
        return [self.path_join_func(*path_parts)] if path_parts else []

    def _handle_path_dict(self, params, args, kwargs) -> List[str]:
        """处理路径字典"""
        path_parts = {'path': [], 'name': []}
        for param, param_type in params.items():
            value = self._get_single_path(param, args, kwargs)
            if value:
                path_parts[param_type].append(value)
        
        return self._combine_path_parts(path_parts)

    def _combine_path_parts(self, path_parts: dict) -> List[str]:
        """组合路径部分"""
        base_path = self.path_join_func(*path_parts['path']) if path_parts['path'] else ''
        filename = self.path_join_func(*path_parts['name']) if path_parts['name'] else ''
        
        if base_path and filename:
            return [self.path_join_func(base_path, filename)]
        elif base_path:
            return [base_path]
        elif filename:
            return [filename]
        return []

class FileHasher:
    """文件哈希处理器"""
    
    @staticmethod
    def get_file_hash(file_path: Union[str, Path]) -> Optional[str]:
        """获取文件内容的哈希值"""
        path = Path(file_path)
        if not path.exists():
            return None
            
        with open(path, 'rb') as f:
            file_hash = hashlib.md5()
            for chunk in iter(lambda: f.read(4096), b''):
                file_hash.update(chunk)
        return file_hash.hexdigest()

    @staticmethod
    def get_files_hash(file_paths: List[str]) -> Optional[str]:
        """获取多个文件的组合哈希值"""
        hashes = []
        for path in file_paths:
            file_hash = FileHasher.get_file_hash(path)
            if file_hash:
                hashes.append(file_hash)
        
        return '_'.join(hashes) if hashes else None 
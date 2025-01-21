from pathlib import Path
from typing import Optional, List, Any

class SubDirCacheMixin:
    """子目录缓存混入类"""
    
    def _get_sub_dir_path(self, sub_dirs: List[str]) -> Path:
        """获取子目录路径"""
        if not hasattr(self, '_dir'):
            raise NotImplementedError("Cache backend must have '_dir' attribute")
            
        current_dir = Path(self._dir)
        for sub_dir in sub_dirs:
            current_dir = current_dir / str(sub_dir)
            current_dir.mkdir(parents=True, exist_ok=True)
        return current_dir

    def _make_sub_dir_key(self, key: str, sub_dirs: Optional[List[str]] = None) -> str:
        """生成子目录下的键"""
        if not sub_dirs:
            return key
        return str(self._get_sub_dir_path(sub_dirs) / key)

    def get_with_sub_dirs(self, key: str, sub_dirs: List[str], default: Any = None) -> Any:
        """从子目录获取缓存"""
        full_key = self._make_sub_dir_key(key, sub_dirs)
        return self.get(full_key, default)

    def set_with_sub_dirs(self, key: str, value: Any, sub_dirs: List[str], timeout: Optional[int] = None) -> None:
        """在子目录设置缓存"""
        full_key = self._make_sub_dir_key(key, sub_dirs)
        self.set(full_key, value, timeout)

    def delete_with_sub_dirs(self, key: str, sub_dirs: List[str]) -> None:
        """从子目录删除缓存"""
        full_key = self._make_sub_dir_key(key, sub_dirs)
        self.delete(full_key)

    def clear_sub_dir(self, sub_dirs: List[str]) -> None:
        """清除子目录下的所有缓存"""
        dir_path = self._get_sub_dir_path(sub_dirs)
        if dir_path.exists():
            for cache_file in dir_path.glob('*'):
                if cache_file.is_file():
                    cache_file.unlink() 
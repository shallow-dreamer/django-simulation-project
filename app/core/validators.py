from typing import List
from django.core.exceptions import ValidationError
from django.core.files.base import File

class FileValidator:
    """文件验证器"""
    def __init__(self, max_size=None, allowed_extensions=None):
        self.max_size = max_size
        self.allowed_extensions = allowed_extensions

    def validate(self, file: File) -> List[str]:
        errors = []
        
        if self.max_size and file.size > self.max_size:
            errors.append(f"文件大小不能超过 {self.max_size} 字节")
            
        if self.allowed_extensions:
            ext = file.name.split('.')[-1].lower()
            if ext not in self.allowed_extensions:
                errors.append(f"不支持的文件类型: {ext}")
                
        return errors 
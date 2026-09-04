import sys
from pathlib import Path

# 确保 pytest 能导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

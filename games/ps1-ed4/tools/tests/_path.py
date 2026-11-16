import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))  # games/ps1-ed4/tools
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..")))  # 레포 루트(shared)

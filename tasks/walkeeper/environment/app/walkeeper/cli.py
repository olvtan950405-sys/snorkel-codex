import argparse
from pathlib import Path
from .planner import plan

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", default="/app/data")
    p.add_argument("--output", default="/app/out/recovery-plan.json")
    a = p.parse_args()
    try:
        plan(Path(a.inventory), Path(a.output))
        return 0
    except (OSError, ValueError) as e:
        print(f"walkeeper: {e}")
        return 2

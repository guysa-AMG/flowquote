"""Evaluation harness runner (PLAN.md §12)."""
import json
from pathlib import Path

def run_evaluation():
    truth_path = Path(__file__).parent / "truth.jsonl"
    if not truth_path.exists():
        print("No truth.jsonl found.")
        return
    
    print("Running evaluation against truth.jsonl...")
    count = 0
    with open(truth_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            count += 1
            print(f"Evaluated memo {data['memo_id']}")
    print(f"Evaluation complete. Total evaluated: {count} (TODO(measure): compute metrics).")

if __name__ == "__main__":
    run_evaluation()

"""Print the metrics and failures of an eval_mjlab result (.json)."""

import argparse
import json
from collections import Counter, defaultdict


def parse_args():
  parser = argparse.ArgumentParser(description="Summarize an eval_mjlab result (.json)")
  parser.add_argument("results_file", help="eval_mjlab output .json")
  parser.add_argument("--details", action="store_true", help="list every failure grouped by seconds of motion")
  return parser.parse_args()


def count_by_rule(failures):
  return Counter(rule for f in failures for rule in f["rules"])


def group_by_seconds(failures):
  groups = defaultdict(list)
  for f in failures:
    groups[int(f["time_s"])].append(f)
  return groups


def main():
  args = parse_args()
  with open(args.results_file) as f:
    results = json.load(f)

  print("Metrics:")
  for name, value in results["metrics"].items():
    print(f" {name}: {value:.4f}")

  failures = results["failures"]
  print(f"\nFailures: {len(failures)}")
  print("\nBy rules:")
  for rule, count in count_by_rule(failures).most_common():
    print(f" {rule}: {count}")

  print("\nBy seconds:")
  for second, fails in sorted(group_by_seconds(failures).items()):
    print(f" {second} s {len(fails)} failures")
    if args.details:
      for f in fails:
        print(f"    {f['time_s']} s (step {f['step']}) episode {f['episode']} {f['rules']}")


if __name__ == "__main__":
  main()

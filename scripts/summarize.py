import argparse
import json
from collections import Counter, defaultdict


def parse_args():
  parser = argparse.ArgumentParser(
    description="Summarize an evaluation results (.json)"
  )
  parser.add_argument("results_file", help="path to the results.json")
  parser.add_argument(
    "--details",
    action="store_true",
    help="list every failure grouped by seconds of motion",
  )
  return parser.parse_args()


def load_results(path):
  with open(path) as f:
    return json.load(f)


def count_by_rule(failures):
  all_rules = [rule for f in failures for rule in f["rules"]]
  return Counter(all_rules)


def group_by_seconds(failures):
  groups = defaultdict(list)
  for f in failures:
    groups[int(f["time_s"])].append(f)
  return groups


def main():
  args = parse_args()
  results = load_results(args.results_file)

  # print metrics
  print("Metrics:")
  for name, value in results["metrics"].items():
    print(f" {name}: {value:.4f}")

  # print failures:
  failures = results["failures"]
  print(f"\nFailures: {len(failures)}")
  print("\nBy rules:")

  rule_counts = count_by_rule(failures)
  for failure, count in rule_counts.most_common():
    print(f" {failure}: {count}")

  print("\nBy seconds:")
  groups = group_by_seconds(failures)
  for second, fails in sorted(groups.items()):
    print(f" {second} s {len(fails)} failures")
    if args.details:
      for f in fails:
        print(
          f"    {f['time_s']} s (step {f['step']}) episode {f['episode']} {f['rules']}"
        )


if __name__ == "__main__":
  main()

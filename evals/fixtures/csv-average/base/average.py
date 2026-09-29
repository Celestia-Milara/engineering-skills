import csv
from pathlib import Path
import sys


def average(path):
    values = [float(row[0]) for row in csv.reader(Path(path).read_text().splitlines())]
    return sum(values) / len(values)


if __name__ == "__main__":
    print(average(sys.argv[1]))

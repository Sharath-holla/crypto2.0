# ruff: noqa: E402, E501, E741, SIM115, B905
# Archived benchmark harness (measurement evidence); late imports are deliberate.
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "tests/phase7")
import pyarrow.parquet as pq
from test_pretraining_integration import _build_fold

tmp = pathlib.Path(tempfile.mkdtemp())
config, features, targets, universe, plan, fold = _build_fold(tmp)
gold_files = sorted((tmp / "gold").rglob("*.parquet"))
schema = pq.ParquetFile(gold_files[0]).schema_arrow
out = pathlib.Path(sys.argv[1])
pq.write_table(pq.ParquetFile(gold_files[0]).read().slice(0, 2000), out / "gold_sample.parquet")
cols = [(f.name, str(f.type)) for f in schema]
from collections import Counter

print(len(cols), Counter(t for _, t in cols))
print("train cols", len(fold.train.column_names), "rows", fold.train.num_rows)
extra = sorted(set(fold.train.column_names) - set(schema.names))
print("added by fold:", extra)
json.dump(cols, open(out / "gold_schema.json", "w"))

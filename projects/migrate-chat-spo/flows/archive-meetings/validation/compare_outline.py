import re, io

import os
HERE = os.path.dirname(os.path.abspath(__file__))
outline_path = os.path.join(HERE, "action_outline.txt")
extracted_path = os.path.join(HERE, "extracted_actions.txt")

with io.open(outline_path, encoding="utf-8") as f:
    outline_lines = f.readlines()

outline_names = {}
for line in outline_lines:
    m = re.match(r"\s*(\d+)\s+(\S+)", line)
    if m:
        outline_names[int(m.group(1))] = m.group(2)

with io.open(extracted_path, encoding="utf-8") as f:
    doc_lines = f.readlines()

doc_names = {}
for line in doc_lines:
    parts = line.rstrip("\n").split("\t")
    n = int(parts[0])
    doc_names[n] = parts[1]

print("outline entries:", len(outline_names))
print("doc entries:", len(doc_names))

mismatches = []
for n in range(1, 140):
    o = outline_names.get(n)
    d = doc_names.get(n)
    if o != d:
        mismatches.append((n, o, d))

print("mismatches:", len(mismatches))
for n, o, d in mismatches:
    print(n, "outline=", o, "doc=", d)

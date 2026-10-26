import re, io

import os
HERE = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(HERE, "..", "spec", "PA_Migrate_Teams_Meeting_Archive_To_SPO.txt")
with io.open(path, encoding="utf-8") as f:
    text = f.read()

start = text.index("## 4. アクション一覧")
end = text.index("## 5. 主要Compose式")
section4 = text[start:end]

lines = section4.split("\n")
results = []
for i, line in enumerate(lines):
    m = re.match(r"\[No\.(\d+)\]", line)
    if m:
        current_no = int(m.group(1))
        for j in range(i+1, min(i+5, len(lines))):
            m2 = re.match(r"アクション表示名:\s*(.+)", lines[j])
            if m2:
                results.append((current_no, m2.group(1).strip()))
                break

print("total extracted:", len(results))
nums = [r[0] for r in results]
expected_max = max(nums) if nums else 0
print(f"expected range 1..{expected_max} all present:", nums == list(range(1, expected_max + 1)))
missing = sorted(set(range(1, expected_max + 1)) - set(nums))
dupes = sorted(set([n for n in nums if nums.count(n) > 1]))
print("missing:", missing)
print("dupes:", dupes)

outp = os.path.join(HERE, "extracted_actions.txt")
with io.open(outp, "w", encoding="utf-8") as f:
    for n, name in results:
        f.write(str(n) + "\t" + name + "\n")

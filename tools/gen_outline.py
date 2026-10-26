# -*- coding: utf-8 -*-
"""definition.json から実行順のアクションアウトラインを生成する（v4）。
runAfter で位相ソートし、ネストはインデントで表現。operationId/type付き。"""
import json, io, sys

if len(sys.argv) != 3:
    print("usage: python gen_outline.py <definition.json> <output.txt>")
    sys.exit(1)
DEF, OUT = sys.argv[1], sys.argv[2]

flow = json.loads(open(DEF, encoding="utf-8").read())
d = flow["properties"]["definition"]
lines = []
counter = [0]

def order_container(container):
    """runAfterに基づく安定位相ソート"""
    names = list(container.keys())
    placed, result = set(), []
    guard = 0
    while len(result) < len(names) and guard < 10000:
        guard += 1
        for n in names:
            if n in placed:
                continue
            ra = container[n].get("runAfter", {})
            if all(t in placed for t in ra.keys()):
                result.append(n); placed.add(n)
    result += [n for n in names if n not in placed]
    return result

def walk(container, depth):
    for n in order_container(container):
        a = container[n]
        t = a.get("type", "?")
        extra = ""
        if t == "OpenApiConnection":
            h = a["inputs"]["host"]
            extra = f" [{h['connectionName']}/{h['operationId']}]"
        elif t == "InitializeVariable":
            v = a["inputs"]["variables"][0]
            extra = f" [{v['name']}:{v['type']}]"
        elif t in ("SetVariable", "AppendToArrayVariable", "AppendToStringVariable", "IncrementVariable"):
            extra = f" [{a['inputs']['name']}]"
        elif t == "Foreach":
            extra = f" [in: {str(a.get('foreach',''))[:70]}]"
        elif t == "Until":
            extra = f" [until: {str(a.get('expression',''))[:60]}]"
        ra = a.get("runAfter", {})
        ra_s = ",".join(f"{k}({'/'.join(v)})" for k, v in ra.items()) or "-"
        counter[0] += 1
        lines.append(f"{counter[0]:3d} {'  '*depth}{n}  <{t}>{extra}  runAfter: {ra_s}")
        if "actions" in a and isinstance(a["actions"], dict):
            walk(a["actions"], depth + 1)
        if t == "If" and "else" in a and "actions" in a.get("else", {}):
            lines.append(f"    {'  '*depth}[else]")
            walk(a["else"]["actions"], depth + 1)

lines.append("=== v4 アクションアウトライン（実行順・ネスト・通し番号=定義上の全アクション） ===")
# トリガー行は定義から読む（旧版は前案件の入力名をハードコードしており、
# 他フローのアウトラインに誤った入力名が出力されていた。2026-07-24 修正）
for _tname, _trig in d.get("triggers", {}).items():
    _props = _trig.get("inputs", {}).get("schema", {}).get("properties", {})
    _req = set(_trig.get("inputs", {}).get("schema", {}).get("required", []))
    _inputs = "/".join((p + "*" if p in _req else p) for p in _props) or "(なし)"
    lines.append(f"trigger: {_tname} ({_trig.get('type')}/{_trig.get('kind')}) inputs: {_inputs}  ※*=必須")
walk(d["actions"], 0)
lines.append(f"--- total actions: {counter[0]} ---")
open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"WROTE {OUT} ({counter[0]} actions)")

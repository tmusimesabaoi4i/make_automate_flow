# -*- coding: utf-8 -*-
"""
Power Automate 定義の汎用リンター（案件横断の共通ツール）。

案件ごとの validate_*.py に手書きでコピーしていた「どのフローにも当てはまる検査」を
1箇所へ集約したもの。**すべての案件の validate_*.py が本モジュールを import する**
（handbook/checklists/import_save_validation_checklist.md §A）。
2026-08-04 に全7フローへ適用済み（充足状況は `python tools/doc_audit.py` の C07 で確認できる）。

ここに集約している検査は、いずれも**実際にインポート／実行を失敗させた**事例から来ている。
案件ごとの手書き実装では同じ穴が再発するため、共通化して機械的に閉じている。

  L01 不正な '@' 位置                      … ネストした関数への @（インポート時 式パースエラー）
  L02 '@{...}' の中身が式でない            … 表示テキスト中の @{tenant} 等（インポート時 式パースエラー）
  L03 表示テキストに '@' がある            … L02 を構造的に防ぐ強い規則
  L04 $expand に対する $select の投影欠落  … 権限の無いリストを実体化して 403（実行時）
  L05 コネクタ出力の封筒参照               … outputs('X')?['field'] が常に null（実行時）
  L06 SetVariable 自己参照                 … 保存時 WorkflowRunActionInputsInvalidProperty
  L07 アクション名の全体重複               … インポート破損
  L08 runAfter の兄弟整合／状態値          … インポート破損
  L09 InitializeVariable の入れ子配置      … 保存不可
  L10 Foreach の並列オフ未設定             … 変数更新の競合
  L11 1式あたりの文字数 8,192 超           … Power Automate の公式上限（保存/実行不可）
  L12 アクション総数 500 超 / ネスト8超    … 同上。500未満でも多すぎると編集が重くなる
  L13 変数 250 超                          … 同上

使い方（CLI。展開形パッケージでも definition.json 単体でも可）:

    python tools/wdl_lint.py <package_dir | definition.json>

使い方（案件の validate_*.py から）:

    import sys, os
    sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "tools")))
    from wdl_lint import lint_definition
    errors += lint_definition(definition, raw)
"""
import json, os, re, sys
from collections import Counter

ENVELOPE_KEYS = ("body", "statusCode", "headers")
RUNAFTER_STATES = ("Succeeded", "Failed", "Skipped", "TimedOut")
INTERP_RE = re.compile(r"@\{([^}]*)\}")
EXPAND_RE = re.compile(r"\$expand=([A-Za-z0-9_,/]+)")
# コレクション取得の判定。単一リソース（`lists(guid'..')` / `GetByTitle('..')`）は末尾が ')'。
COLLECTION_RE = re.compile(r"/(lists|fields|views|items|webs|folders|files)$", re.IGNORECASE)
VAR_MUTATORS = ("SetVariable", "AppendToArrayVariable", "AppendToStringVariable",
                "IncrementVariable", "DecrementVariable")

# Power Automate のプラットフォーム上限（learn.microsoft.com/power-automate/limits-and-config
# 参照日 2026-08-03）。超えると保存・実行できない。
MAX_ACTIONS = 500
MAX_NESTING = 8
MAX_VARIABLES = 250
MAX_EXPR_CHARS = 8192
# 定義中に素で現れる JSON キー（式ではないので '@' 検査から除外する）
BAD_AT_ALLOWED = {"@odata.nextLink", "@odata.count", "@odata.context", "@odata.type", "@odata.id"}


# =========================================================================
# 字句ヘルパー（引用符を意識して走査する）
# =========================================================================
def scan_bad_at(s):
    """式先頭 / '@{' 補間 / 文字列リテラル内 以外の '@' の位置を返す"""
    bad, i, n, in_str = [], 0, len(s), False
    starts_expr = s.startswith("@")
    while i < n:
        c = s[i]
        if in_str:
            if c == "'":
                if i + 1 < n and s[i + 1] == "'":
                    i += 2
                    continue
                in_str = False
        else:
            if c == "'":
                in_str = True
            elif c == "@":
                if not ((i == 0 and starts_expr) or (i + 1 < n and s[i + 1] == "{")):
                    bad.append(i)
        i += 1
    return bad


def strip_literals(s):
    """式から単一引用符の文字列リテラルを取り除く。
    REST の URI 片（'..lists(guid'' や ''AddViewField(..'）を関数名と誤検出しないため。"""
    out, i, n, in_str = [], 0, len(s), False
    while i < n:
        c = s[i]
        if in_str:
            if c == "'":
                if i + 1 < n and s[i + 1] == "'":
                    i += 2
                    continue
                in_str = False
        else:
            if c == "'":
                in_str = True
            else:
                out.append(c)
        i += 1
    return "".join(out)


def collect_strings(node, path, out):
    if isinstance(node, dict):
        for k, v in node.items():
            collect_strings(v, "%s.%s" % (path, k), out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            collect_strings(v, "%s[%d]" % (path, i), out)
    elif isinstance(node, str):
        out.append((path, node))
    return out


def walk_actions(container, path, depth, out):
    """(name, action, path, depth) を再帰的に集める。else 分岐も辿る。"""
    for name, a in container.items():
        if not isinstance(a, dict):
            continue
        out.append((name, a, path, depth))
        if isinstance(a.get("actions"), dict):
            walk_actions(a["actions"], "%s/%s" % (path, name), depth + 1, out)
        if a.get("type") == "If" and isinstance(a.get("else"), dict):
            walk_actions(a["else"].get("actions", {}), "%s/%s[else]" % (path, name),
                         depth + 1, out)
    return out


# =========================================================================
# 検査本体
# =========================================================================
def lint_definition(definition, raw=None):
    """properties.definition を受け取り、エラーメッセージのリストを返す（0件なら合格）"""
    errors = []
    if raw is None:
        raw = json.dumps(definition, ensure_ascii=False)

    triggers = definition.get("triggers", {}) or {}
    actions = definition.get("actions", {}) or {}
    nodes = walk_actions(actions, "root", 0, [])
    by_name = {n: a for n, a, _, _ in nodes}
    conn_actions = {n for n, a, _, _ in nodes if a.get("type") == "OpenApiConnection"}

    strings = collect_strings({"triggers": triggers, "actions": actions}, "definition", [])

    # --- L01 / L02: '@' と '@{...}' ---
    # L01 は「式文字列（'@' で始まる）の中の不正な '@'」だけを見る。
    # 式でない普通の文字列に含まれる裸の '@'（メールアドレス・チャネルID・CSSの @page 等）は
    # Power Automate では単なるリテラルであり合法。Microsoft の実エクスポートにも存在する
    # （references/extracted/shared-mailbox-to-teams-notify-20260803 の mailboxAddress 等）。
    # 式でない文字列で危険なのは '@{' だけなので、そちらは L02 / L03 が担当する。
    for path, s in strings:
        if s in BAD_AT_ALLOWED:
            continue
        if s.startswith("@"):
            bad = scan_bad_at(s)
            if bad:
                errors.append("L01 不正な '@' 位置 %s at %s: %r" % (bad, path, s[:120]))
        for m in INTERP_RE.finditer(s):
            inner = m.group(1).strip()
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\(", inner):
                errors.append(
                    "L02 '@{...}' の中身が式（関数呼び出し）でない。インポート時に "
                    "Unable to parse template language expression になる at %s: %r"
                    % (path, s[:120]))

    # --- L03: トリガー入力の表示テキストに '@' を書かない ---
    for tname, tv in triggers.items():
        props = ((tv.get("inputs") or {}).get("schema") or {}).get("properties") or {}
        for key, spec in props.items():
            if not isinstance(spec, dict):
                continue
            for fld in ("title", "description"):
                if "@" in str(spec.get(fld, "")):
                    errors.append(
                        "L03 トリガー入力 %s の %s に '@' がある"
                        "（'@{' が式補間として解釈されインポートに失敗する）: %r"
                        % (key, fld, spec.get(fld)))

    # --- L04: $expand に対する $select の投影（コレクション列挙のときのみ） ---
    # 単一リソース（lists(guid'..') / GetByTitle('..')）への $expand は投影が無くても動く。
    # 実環境で成功した3実装（create_initialized_sharepoint_list / provision-archive-lists /
    # CreateKnowledgeList）がいずれも $select=Id,Title&$expand=RootFolder で動作している。
    # 危険なのはコレクション（_api/web/lists?...）で、アクセス権の無いシステムリストまで
    # 実体化しようとして 403 になる。
    for name, a, _, _ in nodes:
        if a.get("type") != "OpenApiConnection":
            continue
        uri = str((a.get("inputs", {}).get("parameters") or {}).get("parameters/uri", ""))
        if "$expand=" not in uri or "$select=" not in uri:
            continue
        path_part = uri.split("?", 1)[0]
        if not COLLECTION_RE.search(path_part):
            continue
        for m in EXPAND_RE.finditer(uri):
            for exp in m.group(1).split(","):
                exp = exp.strip()
                if exp and (exp + "/") not in uri:
                    errors.append(
                        "L04 %s は $expand=%s しているのに $select に '%s/<プロパティ>' の投影が無い"
                        "（アクセス権の無いリソースを実体化して 403 になりうる）: %r"
                        % (name, exp, exp, uri[:120]))

    # --- L05: コネクタ出力の封筒参照 ---
    for m in re.finditer(r"outputs\('([^']+)'\)\?\['([^']+)'\]", raw):
        act, field = m.group(1), m.group(2)
        if act in conn_actions and not field.startswith(ENVELOPE_KEYS):
            errors.append(
                "L05 コネクタ出力の body/ 欠落: outputs('%s')?['%s'] は常にnull"
                "（body('%s')?['%s'] が正）" % (act, field, act, field))

    # --- L06: SetVariable 自己参照 ---
    for name, a, _, _ in nodes:
        if a.get("type") != "SetVariable":
            continue
        var = (a.get("inputs") or {}).get("name")
        val = json.dumps((a.get("inputs") or {}).get("value"), ensure_ascii=False)
        if var and ("variables('%s')" % var) in val:
            errors.append("L06 SetVariable 自己参照（保存時 WorkflowRunActionInputsInvalidProperty）"
                          ": %s -> %s" % (name, var))

    # --- L07: アクション名の全体重複 ---
    names = [n for n, _, _, _ in nodes] + list(triggers.keys())
    dups = [n for n, c in Counter(names).items() if c > 1]
    if dups:
        errors.append("L07 アクション名の全体重複（Power Automateは全体一意を要求）: %s" % dups)

    # --- L08: runAfter の兄弟整合／状態値 ---
    def check_siblings(container, path):
        sib = set(container.keys())
        for n, a in container.items():
            if not isinstance(a, dict):
                continue
            ra = a.get("runAfter", {})
            if not isinstance(ra, dict):
                errors.append("L08 %s/%s: runAfter が dict でない" % (path, n))
                continue
            for target, states in ra.items():
                if target not in sib:
                    errors.append("L08 %s/%s: runAfter -> '%s' が同一コンテナの兄弟に存在しない"
                                  % (path, n, target))
                for st in (states or []):
                    if st not in RUNAFTER_STATES:
                        errors.append("L08 %s/%s: runAfter の状態値が不正: %s" % (path, n, st))
            if isinstance(a.get("actions"), dict):
                check_siblings(a["actions"], "%s/%s" % (path, n))
            if a.get("type") == "If" and isinstance(a.get("else"), dict):
                check_siblings(a["else"].get("actions", {}), "%s/%s[else]" % (path, n))

    check_siblings(actions, "root")

    # --- L09 / L10 ---
    for name, a, path, depth in nodes:
        if a.get("type") == "InitializeVariable" and depth > 0:
            errors.append("L09 InitializeVariable '%s' が入れ子(depth=%d)にある（トップレベル必須）"
                          % (name, depth))
        if a.get("type") == "Foreach":
            rep = (a.get("runtimeConfiguration", {}).get("concurrency", {}) or {}).get("repetitions")
            # 並列オフが必須なのは「変数を更新するループ」（handbook/rules/01）。
            # 変数を触らないループまで一律に落とさない。
            sub = walk_actions(a.get("actions", {}) or {}, name, 0, [])
            mutates = any(x.get("type") in VAR_MUTATORS for _, x, _, _ in sub)
            if mutates and rep != 1:
                errors.append("L10 %s: 変数を更新する Apply to each の並列オフ未設定"
                              "（repetitions=%r。Append/Increment が競合して件数が壊れる）"
                              % (name, rep))

    # --- L11 / L12 / L13: Power Automate のプラットフォーム上限 ---
    # 出典: learn.microsoft.com/power-automate/limits-and-config（参照日 2026-08-03）
    #   Actions per workflow 500 ／ Allowed nesting depth 8 ／ Variables per workflow 250
    #   Characters per expression 8,192
    # 超えると保存・実行できない。設計段階で気付けないため機械検査で閉じる。
    for spath, s in strings:
        if len(s) > MAX_EXPR_CHARS:
            errors.append("L11 式が %d 文字で上限 %d を超えている at %s: %r"
                          % (len(s), MAX_EXPR_CHARS, spath, s[:80]))
    if len(nodes) > MAX_ACTIONS:
        errors.append("L12 アクション総数 %d が上限 %d を超えている（子フローへの分割が必要）"
                      % (len(nodes), MAX_ACTIONS))
    depth_max = max([d for _, _, _, d in nodes], default=-1) + 1
    if depth_max > MAX_NESTING:
        errors.append("L12 ネスト深さ %d が上限 %d を超えている" % (depth_max, MAX_NESTING))
    var_names = set()
    for _, a, _, _ in nodes:
        if a.get("type") == "InitializeVariable":
            for v in (a.get("inputs", {}) or {}).get("variables", []) or []:
                var_names.add(v.get("name"))
    if len(var_names) > MAX_VARIABLES:
        errors.append("L13 変数 %d 個が上限 %d を超えている" % (len(var_names), MAX_VARIABLES))

    return errors


# =========================================================================
# Markdown の検査
#   ドキュメントに載せた REST 断片が「そのまま使える形」に見えて実は壊れている、
#   という罠を機械的に潰す。2026-08-03 に handbook の `$select=...,Hidden,...` を
#   コピーして投影を落とし、403 を出した実例があるため導入した。
# =========================================================================
MD_ABBREV = [
    (re.compile(r"\$(select|expand|filter|orderby)=[^\s`&|)]*(\.\.\.|…)"),
     "M01 クエリが '...' で省略されている（コピーすると壊れる）"),
    # `Func(...)` は引数のプレースホルダ（万国共通の表記）なので罠ではない。
    # 罠なのは「パスやクエリの一部が省略されている」形。直前が '(' のときは除外する。
    (re.compile(r"_api/[^\s`|)]*(?<!\()(\.\.\.|…)"), "M01 REST URI が '...' で省略されている"),
]


IGNORE_TOKEN = "wdl-lint:ignore"


def lint_markdown(text, path="(md)", ignore_lines=()):
    """Markdown 中の REST 断片を検査する。エラーメッセージのリストを返す。

    誤り例を教材として載せたい箇所は、行内または直前のコードフェンスに
    `wdl-lint:ignore` と書けば除外できる。
    （例:  ```text wdl-lint:ignore  … 403 になる形を示すブロック）
    """
    errors = []
    in_ignored_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            if in_ignored_fence:
                in_ignored_fence = False
            elif IGNORE_TOKEN in line:
                in_ignored_fence = True
            continue
        if in_ignored_fence or IGNORE_TOKEN in line or i in ignore_lines:
            continue
        for rx, label in MD_ABBREV:
            if rx.search(line):
                errors.append("%s at %s:%d: %s" % (label, path, i, line.strip()[:120]))
                break
        # M02: コレクション列挙の $expand に投影が無い
        for m in re.finditer(r"(_api/[^\s`|)]*\?[^\s`|)]*)", line):
            uri = m.group(1)
            if "$expand=" not in uri or "$select=" not in uri:
                continue
            if not COLLECTION_RE.search(uri.split("?", 1)[0]):
                continue
            for em in EXPAND_RE.finditer(uri):
                for exp in em.group(1).split(","):
                    exp = exp.strip()
                    if exp and (exp + "/") not in uri:
                        errors.append(
                            "M02 コレクション列挙の $expand=%s に $select の投影が無い"
                            "（403 になる形が文書に載っている） at %s:%d: %s"
                            % (exp, path, i, uri[:110]))
    return errors


def summarize(definition):
    """上限に対する余裕を返す（警告用。エラーではない）"""
    nodes = walk_actions(definition.get("actions", {}) or {}, "root", 0, [])
    strings = collect_strings({"actions": definition.get("actions", {}) or {},
                               "triggers": definition.get("triggers", {}) or {}}, "d", [])
    longest = max([len(s) for _, s in strings], default=0)
    return {"actions": len(nodes), "maxExpr": longest,
            "maxDepth": max([d for _, _, _, d in nodes], default=-1) + 1}


def load_definition(path):
    """展開形パッケージのディレクトリ、または definition.json のパスを受け取る"""
    if os.path.isdir(path):
        flows = os.path.join(path, "Microsoft.Flow", "flows")
        guids = [d for d in os.listdir(flows) if os.path.isdir(os.path.join(flows, d))]
        path = os.path.join(flows, guids[0], "definition.json")
    raw = open(path, encoding="utf-8-sig").read()
    doc = json.loads(raw)
    return doc.get("properties", {}).get("definition", doc), raw, path


def main():
    if len(sys.argv) < 2:
        print("usage: python wdl_lint.py <package_dir | definition.json | *.md> [...]")
        print("       python wdl_lint.py --all <repo_root>   リポジトリ全体を検査")
        return 1

    targets = sys.argv[1:]
    if targets[0] == "--all":
        root = targets[1] if len(targets) > 1 else "."
        targets = []
        # _legacy（歴史的スナップショット）と references/extracted（受領原本の展開・編集禁止）は
        # こちらで直せない読み取り専用資産のため既定で対象外。個別指定すれば検査できる。
        skip_dirs = (".git", "__pycache__", "node_modules", "_legacy", "extracted")
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in skip_dirs]
            for f in fn:
                if f == "definition.json" and "validation" + os.sep + "extracted" not in dp:
                    targets.append(os.path.join(dp, f))
                elif f.lower().endswith(".md"):
                    targets.append(os.path.join(dp, f))

    total = 0
    for target in targets:
        if target.lower().endswith(".md"):
            txt = open(target, encoding="utf-8").read()
            rel = os.path.relpath(target).replace(os.sep, "/")
            errs = lint_markdown(txt, rel)
        else:
            definition, raw, path = load_definition(target)
            rel = os.path.relpath(path).replace(os.sep, "/")
            errs = lint_definition(definition, raw)
        if errs:
            print("=== %s ===" % rel)
            for e in errs:
                print("   ", e)
        total += len(errs)
    print("-" * 70)
    print("対象 %d 件 / 指摘 %d 件" % (len(targets), total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())

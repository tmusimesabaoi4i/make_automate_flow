# -*- coding: utf-8 -*-
"""
文書整合性の監査ツール（リポジトリ全体・案件横断）。

Markdown・Skill・Agent・実装の間の「食い違い」を機械的に検出する。
定期監査（doc-audit Skill）の第1ステップとして実行し、指摘0件を維持する。

`tools/wdl_lint.py` との住み分け:
  wdl_lint  … Power Automate **定義とREST断片の正しさ**（保存・実行できるか）
  doc_audit … **文書体系の整合性**（参照先が実在するか・数値が合っているか）
二重管理を避けるため、両者の検査項目は重ならないようにしている。

検査項目:
  C01 相対リンクの有効性              … [text](path) の実在
  C02 インラインコードのパス参照       … `path/to/file` の実在（3基準で解決を試行）
  C03 Skill名・Agent名の整合           … frontmatter name ⇔ README / CLAUDE.md の索引
  C04 数値整合                        … エラー件数・Skill数・フロー数の記載 ⇔ 実際
  C05 error_catalog の分割閾値         … 12エラー超 / 60KB超（CLAUDE.md 運用メモ）
  C06 build_*.py / validate_*.py の実在 … 文書記載 ⇔ 実ファイル
  C07 wdl_lint の import 採用状況      … checklists §A の必須項目の充足
  C08 既知の陳腐化パス                 … 移動・改称済みパスの残存

使い方:

    python tools/doc_audit.py              # リポジトリ全体を検査
    python tools/doc_audit.py --json       # 結果をJSONで出力（DOCX生成・差分抽出用）

終了コード: 指摘0件=0 / 1件以上=1
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

# 歴史的記録・受領原本は「直せない資産」なので既定で対象外にする。
#   _legacy/                     旧構成の退避（CLAUDE.md: 退避のみ）
#   references/extracted/        受領原本の展開（編集禁止）
#   .claude/skills/*/references/ Skill同梱の参照資料（あれば）
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".pytest_cache", "_legacy", "extracted"}

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
CODE_RE = re.compile(r"`([^`\n]+)`")
FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)

# C02 でパスとみなす条件。拡張子付き、または末尾スラッシュのもののみを対象にする。
PATH_LIKE_RE = re.compile(r"^[A-Za-z0-9_./-]+$")
PATH_EXT_RE = re.compile(r"\.(md|py|json|txt|zip|docx)$")

# C08 移動・改称済みで、現行仕様として書いてはいけないパス。
#   (検出パターン, 正しい記述, 補足)
STALE_PATHS = [
    (re.compile(r"(?<![\w/])tests/wdl_eval\.py"), "tools/wdl_eval.py",
     "WDL式評価器は案件横断の共通ツールへ移動済み"),
    (re.compile(r"projects/migrate-chat-spo/references/"), "references/",
     "参照資料は2026-07-24にリポジトリ直下へ集約済み"),
]


def iter_markdown():
    """監査対象の Markdown を (絶対パス, リポジトリ相対パス) で列挙する"""
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in sorted(fn):
            if f.lower().endswith(".md"):
                p = os.path.join(dp, f)
                yield p, os.path.relpath(p, ROOT).replace(os.sep, "/")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# 「そのパスを現行仕様として使う」以外の文脈でパス名が出てくる行を除外するための語。
#   経緯の説明   … 「2026-07-24 に `projects/migrate-chat-spo/references/` から移動」
#   否定の宣言   … 「`.claude/rules/` は設けない（二重管理の回避）」
# どちらも「実在しないパスが書かれている」こと自体が正しいので、指摘しない。
HISTORY_WORDS = ("移動", "廃止", "旧", "以前", "かつて", "統合", "改称", "→",
                 "設けない", "作らない", "置かない", "存在しない", "使わない")
IGNORE_TOKEN = "doc-audit:ignore"


def is_history_line(line):
    """その行が『経緯の説明』または『否定の宣言』なら True（実在しないパスが載っていても誤りではない）"""
    return IGNORE_TOKEN in line or any(w in line for w in HISTORY_WORDS)


def is_historical(rel):
    """内容を修正できない／修正すべきでない文書か。

    - `references/` … 受領原本の解析証跡（CLAUDE.md: 編集禁止）
    - `validation/` 配下・`validation_report.md` … 当時の検証事実の記録。
      現行仕様ではないので、旧パスが残っていても直さない（改変すると証跡が壊れる）
    - `audit/findings/` … 過去の監査記録。「何が間違っていたか」を書き残すのが目的なので、
      誤ったパスを引用しているのが正しい（引用を検出して直すと記録が壊れる）
    """
    return (rel.startswith("references/")
            or rel.startswith("audit/findings/")
            or "/validation/" in rel
            or rel.endswith("validation_report.md")
            or rel.endswith("implementation_report.md"))


def project_root_of(abs_path):
    """projects/<案件>/ 配下ならその案件ルートを返す。案件文書は案件ルート基準の
    相対パス表記（`flows/...` `docs/...` `tests/...`）を使うため、この基準が要る。"""
    rel = os.path.relpath(abs_path, ROOT).replace(os.sep, "/").split("/")
    if len(rel) >= 2 and rel[0] == "projects":
        return os.path.join(ROOT, "projects", rel[1])
    return None


# =========================================================================
# C01 相対リンクの有効性
# =========================================================================
def check_links(findings):
    checked = 0
    for abs_path, rel in iter_markdown():
        base = os.path.dirname(abs_path)
        for m in LINK_RE.finditer(read(abs_path)):
            target = m.group(2).strip()
            if target.startswith(("http://", "https://", "#", "mailto:", "<")):
                continue
            checked += 1
            frag = target.split("#")[0]
            if not frag:
                continue
            if not os.path.exists(os.path.normpath(os.path.join(base, frag))):
                findings.append({
                    "check": "C01", "severity": "error", "file": rel,
                    "message": "相対リンクの参照先が存在しない: %s" % target,
                })
    return {"C01_links_checked": checked}


# =========================================================================
# C02 インラインコード中のパス参照
# =========================================================================
def all_real_paths():
    """リポジトリ内の実在パス（ファイル・ディレクトリ）をPOSIX表記の集合で返す。
    `source/` や `validation/extract_check.py` のようにフロー配下で使い回される
    「相対表記」を誤検出しないため、末尾一致でも解決できるようにする。"""
    out = set()
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in {".git", "__pycache__", "node_modules"}]
        for name in list(dn) + list(fn):
            p = os.path.relpath(os.path.join(dp, name), ROOT).replace(os.sep, "/")
            out.add(p)
    return out


def check_code_paths(findings, real_paths):
    unresolved = 0
    for abs_path, rel in iter_markdown():
        if is_historical(rel):
            continue
        base = os.path.dirname(abs_path)
        proj = project_root_of(abs_path)
        txt = read(abs_path)
        for m in CODE_RE.finditer(txt):
            s = m.group(1).strip()
            if "/" not in s or not PATH_LIKE_RE.match(s):
                continue
            lineno = txt.count("\n", 0, m.start()) + 1
            if is_history_line(txt.splitlines()[lineno - 1]):
                continue
            if not (PATH_EXT_RE.search(s) or s.endswith("/")):
                continue
            # 省略記法（`build/.../definition.json`）は解決対象にしない
            if "..." in s or "…" in s:
                continue
            # 先頭 '/' は URL 断片（`/_layouts/` `/l/message/`）でリポジトリ内パスではない
            if s.startswith("/"):
                continue
            # 単一セグメントのディレクトリ表記（`body/` `item/` `X/`）は
            # JSON パス・URL 断片であることがほとんどで、リポジトリ内パスを指さない
            if s.endswith("/") and s.count("/") == 1:
                continue
            cand = s.rstrip("/")
            # (1) 格納ディレクトリ / リポジトリルート / 案件ルート の3基準で解決
            bases = [base, ROOT] + ([proj] if proj else [])
            if any(os.path.exists(os.path.normpath(os.path.join(b, cand))) for b in bases):
                continue
            # (2) リポジトリ内のいずれかの実在パスの末尾と一致するか
            #     （フロー配下で使い回される相対表記を許容する）
            suffix = "/" + cand
            if any(p == cand or p.endswith(suffix) for p in real_paths):
                continue
            unresolved += 1
            findings.append({
                "check": "C02", "severity": "error", "file": rel, "line": lineno,
                "message": "コード表記のパスがリポジトリ内のどこにも存在しない: `%s`" % s,
            })
    return {"C02_unresolved": unresolved}


# =========================================================================
# C03 Skill名・Agent名の整合
# =========================================================================
def collect_skills_agents():
    skills, agents = {}, {}
    sk_dir = os.path.join(ROOT, ".claude", "skills")
    if os.path.isdir(sk_dir):
        for d in sorted(os.listdir(sk_dir)):
            f = os.path.join(sk_dir, d, "SKILL.md")
            if os.path.isfile(f):
                m = FRONTMATTER_NAME_RE.search(read(f))
                skills[d] = m.group(1) if m else None
    ag_dir = os.path.join(ROOT, ".claude", "agents")
    if os.path.isdir(ag_dir):
        for f in sorted(os.listdir(ag_dir)):
            if f.endswith(".md"):
                m = FRONTMATTER_NAME_RE.search(read(os.path.join(ag_dir, f)))
                agents[f[:-3]] = m.group(1) if m else None
    return skills, agents


def check_names(findings, skills, agents):
    # frontmatter の name とディレクトリ／ファイル名が一致すること
    for d, name in skills.items():
        if name is None:
            findings.append({"check": "C03", "severity": "error",
                             "file": ".claude/skills/%s/SKILL.md" % d,
                             "message": "frontmatter に name がない"})
        elif name != d:
            findings.append({"check": "C03", "severity": "error",
                             "file": ".claude/skills/%s/SKILL.md" % d,
                             "message": "frontmatter name '%s' がディレクトリ名 '%s' と一致しない"
                                        % (name, d)})
    for f, name in agents.items():
        if name is None:
            findings.append({"check": "C03", "severity": "error",
                             "file": ".claude/agents/%s.md" % f,
                             "message": "frontmatter に name がない"})
        elif name != f:
            findings.append({"check": "C03", "severity": "error",
                             "file": ".claude/agents/%s.md" % f,
                             "message": "frontmatter name '%s' がファイル名 '%s' と一致しない"
                                        % (name, f)})

    # 索引（README / CLAUDE.md）に全Skill・全Agentが載っていること
    for idx in ("README.md", "CLAUDE.md"):
        p = os.path.join(ROOT, idx)
        if not os.path.isfile(p):
            continue
        txt = read(p)
        for name in skills.values():
            if name and name not in txt:
                findings.append({"check": "C03", "severity": "error", "file": idx,
                                 "message": "Skill '%s' が索引に記載されていない" % name})
        for name in agents.values():
            if name and name not in txt:
                findings.append({"check": "C03", "severity": "error", "file": idx,
                                 "message": "Agent '%s' が索引に記載されていない" % name})

    # 索引に、実在しないSkill/Agent名が書かれていないこと
    known = set(filter(None, list(skills.values()) + list(agents.values())))
    for idx in ("README.md", "CLAUDE.md"):
        p = os.path.join(ROOT, idx)
        if not os.path.isfile(p):
            continue
        for m in re.finditer(r"\b(flow-[a-z-]+|knowledge-[a-z-]+|doc-[a-z-]+|package-auditor)\b",
                             read(p)):
            nm = m.group(1)
            if nm not in known:
                findings.append({"check": "C03", "severity": "error", "file": idx,
                                 "message": "実在しないSkill/Agent名が記載されている: %s" % nm})


# =========================================================================
# C04 数値整合 / C05 分割閾値
# =========================================================================
def count_error_sections():
    """error_catalog.md の実エラー節数。索引・追記方法・書式見本は数えない。"""
    p = os.path.join(ROOT, "handbook", "knowledge", "error_catalog.md")
    if not os.path.isfile(p):
        return 0, 0
    txt = read(p)
    heads = re.findall(r"^## (.+)$", txt, re.MULTILINE)
    excluded = ("索引", "追記方法", "エラー名またはコード")
    n = len([h for h in heads if not any(h.startswith(x) for x in excluded)])
    return n, len(txt.encode("utf-8"))


def count_flows():
    n = 0
    pdir = os.path.join(ROOT, "projects")
    for proj in sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []:
        fdir = os.path.join(pdir, proj, "flows")
        if os.path.isdir(fdir):
            n += len([d for d in os.listdir(fdir)
                      if os.path.isdir(os.path.join(fdir, d))])
    return n


def check_counts(findings, skills, n_err, err_bytes):
    n_flow, n_skill = count_flows(), len(skills)

    # 「既知N件のエラー」「既知Nエラー」「起きたNつのエラー」等を拾って実数と突き合わせる
    pat = re.compile(r"(?:既知|実際に発生した|起きた)[^\n]{0,12}?(\d+)\s*(?:件|つ|エラー)")
    for abs_path, rel in iter_markdown():
        if not (rel in ("README.md", "CLAUDE.md") or rel.startswith("handbook/rules/00")):
            continue
        for m in pat.finditer(read(abs_path)):
            got = int(m.group(1))
            if got != n_err:
                findings.append({
                    "check": "C04", "severity": "error", "file": rel,
                    "message": "エラー件数の記載 %d 件が error_catalog の実数 %d 件と一致しない"
                               % (got, n_err),
                })

    # C05 分割閾値（CLAUDE.md 運用メモ: 12エラー超 または 60KB超で分割検討）
    if n_err > 12 or err_bytes > 60 * 1024:
        findings.append({
            "check": "C05", "severity": "warn", "file": "handbook/knowledge/error_catalog.md",
            "message": "分割閾値に到達（%d エラー / %d bytes）。分割を検討する" % (n_err, err_bytes),
        })
    return {"errors": n_err, "error_catalog_bytes": err_bytes,
            "flows": n_flow, "skills": n_skill}


# =========================================================================
# C06 build_*.py / validate_*.py の実在 / C07 wdl_lint の採用
# =========================================================================
def collect_flow_scripts():
    """(案件, フロー, build相対パス, validate相対パス) を返す"""
    out = []
    pdir = os.path.join(ROOT, "projects")
    for proj in sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []:
        fdir = os.path.join(pdir, proj, "flows")
        if not os.path.isdir(fdir):
            continue
        for flow in sorted(os.listdir(fdir)):
            sdir = os.path.join(fdir, flow, "source")
            if not os.path.isdir(sdir):
                continue
            b = [f for f in sorted(os.listdir(sdir)) if f.startswith("build_") and f.endswith(".py")]
            v = [f for f in sorted(os.listdir(sdir)) if f.startswith("validate_") and f.endswith(".py")]
            out.append((proj, flow,
                        os.path.join(sdir, b[0]) if b else None,
                        os.path.join(sdir, v[0]) if v else None))
    return out


def check_scripts(findings, flows):
    for proj, flow, b, v in flows:
        base = "projects/%s/flows/%s/source" % (proj, flow)
        if b is None:
            findings.append({"check": "C06", "severity": "error", "file": base,
                             "message": "build_*.py が存在しない"})
        if v is None:
            findings.append({"check": "C06", "severity": "error", "file": base,
                             "message": "validate_*.py が存在しない（検証の正典が無い）"})


def check_wdl_lint_adoption(findings, flows):
    """checklists §A: 各案件の validate_*.py が tools/wdl_lint.py を import すること"""
    adopted, total = 0, 0
    for proj, flow, _b, v in flows:
        if v is None:
            continue
        total += 1
        if "wdl_lint" in read(v):
            adopted += 1
        else:
            findings.append({
                "check": "C07", "severity": "error",
                "file": os.path.relpath(v, ROOT).replace(os.sep, "/"),
                "message": "tools/wdl_lint.py を import していない"
                           "（handbook/checklists/import_save_validation_checklist.md §A）",
            })
    return {"wdl_lint_adopted": adopted, "wdl_lint_total": total}


# =========================================================================
# C08 既知の陳腐化パス
# =========================================================================
def check_stale_paths(findings):
    for abs_path, rel in iter_markdown():
        if is_historical(rel):
            continue
        txt = read(abs_path)
        lines = txt.splitlines()
        for rx, correct, note in STALE_PATHS:
            for m in rx.finditer(txt):
                line = txt.count("\n", 0, m.start()) + 1
                if is_history_line(lines[line - 1]):
                    continue
                findings.append({
                    "check": "C08", "severity": "error", "file": rel, "line": line,
                    "message": "陳腐化したパス '%s' が現行記述にある（正: %s。%s）"
                               % (m.group(0), correct, note),
                })


# =========================================================================
def main():
    findings, stats = [], {}
    skills, agents = collect_skills_agents()
    flows = collect_flow_scripts()
    n_err, err_bytes = count_error_sections()

    stats.update(check_links(findings))
    stats.update(check_code_paths(findings, all_real_paths()))
    check_names(findings, skills, agents)
    stats.update(check_counts(findings, skills, n_err, err_bytes))
    check_scripts(findings, flows)
    stats.update(check_wdl_lint_adoption(findings, flows))
    check_stale_paths(findings)

    stats["markdown_files"] = sum(1 for _ in iter_markdown())
    stats["agents"] = len(agents)

    if "--json" in sys.argv:
        json.dump({"stats": stats, "findings": findings},
                  sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 1 if findings else 0

    print("=" * 78)
    print(" 文書整合性監査 (tools/doc_audit.py)")
    print("=" * 78)
    print(" 対象Markdown %d / Skill %d / Agent %d / フロー %d / 既知エラー %d"
          % (stats["markdown_files"], stats["skills"], stats["agents"],
             stats["flows"], stats["errors"]))
    print(" 相対リンク検査 %d 件 / wdl_lint 採用 %d/%d"
          % (stats["C01_links_checked"], stats["wdl_lint_adopted"], stats["wdl_lint_total"]))
    print("-" * 78)

    by_check = {}
    for f in findings:
        by_check.setdefault(f["check"], []).append(f)
    for chk in sorted(by_check):
        print("[%s] %d 件" % (chk, len(by_check[chk])))
        for f in by_check[chk]:
            loc = "%s:%s" % (f["file"], f["line"]) if f.get("line") else f["file"]
            print("    %-5s %s" % (f["severity"], loc))
            print("          %s" % f["message"])
    print("-" * 78)
    print("指摘 %d 件" % len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

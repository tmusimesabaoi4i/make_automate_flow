# -*- coding: utf-8 -*-
"""
審査官名簿との突合ロジックの回帰テスト（オフライン）。

対象は sync-mail-to-list-with-examiner-directory の生成済み definition.json。
検出チェーンと同じく、**定義に実際に書かれている式そのもの**を tools/wdl_eval.py で評価する。

  python run_directory_match_tests.py

名簿は Scope_Load_Roster が1回だけ GET する。ここではその応答
（body('Get_Roster_Items')?['value']）をテスト側から差し込んで、
ループ内の Filter array / Compose がどう振る舞うかを確かめる。

【確認できること】
  推定した審査官名と名簿の中身を与えたときの、突合状態・採用行・列に入る値。
【確認できないこと】
  実機での REST 応答、SharePoint への保存結果、名簿リストの実在。要実環境確認。

氏名・メールアドレスはすべて**架空**。実在の値は書かない。
"""
import os, sys, io

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "tools")))
sys.path.insert(0, HERE)
from wdl_eval import Context                      # noqa: E402
# run_detection_tests が import 時に sys.stdout を UTF-8 で包む。
# ここで包み直すと、先のラッパーが回収されて下位のバッファが閉じられるため、
# **二重に包まない**（io は run_one の型注釈以外では使わないが import は残す）。
import run_detection_tests as RD                  # noqa: E402

assert io is not None

PKG = os.path.join(HERE, "..", "flows", "sync-mail-to-list-with-examiner-directory",
                   "source", "package")
DET_PREFIXES = RD.DET_PREFIXES + ("Compose_Dir_", "Filter_Dir_")


def row(full, last, first, email="", uid="", key="", active=True):
    """名簿1行。実際の列名（内部名）に合わせる。氏名・アドレスは架空。"""
    return {"FullName": full, "LastName": last, "FirstName": first,
            "Email": email, "TeamsUserId": uid, "SyncKey": key,
            "MemberStatus": "在籍" if active else "離脱", "IsActive": active}


AOKI = row("青木 健", "青木", "健", "aoki.k@example.com", "uid-aoki", "key-aoki")
AOKI2 = row("青木 一郎", "青木", "一郎", "aoki.i@example.com", "uid-aoki2", "key-aoki2")
KIRYU = row("桐生 慎太郎", "桐生", "慎太郎", "kiryu@example.com", "uid-kiryu", "key-kiryu")
# ゲスト等でメールが取れていない在籍者（名簿側の仕様上ありうる）
SHIRATORI = row("白鳥 花子", "白鳥", "花子", "", "uid-shiratori", "key-shiratori")
# 離脱者（行は残るが IsActive=false）
UJI_LEFT = row("宇治 一明", "宇治", "一明", "uji@example.com", "uid-uji", "key-uji", active=False)
# 表示名にスペースが無く LastName に全部入っている行（名簿側の分割規則で起こりうる）
NOSPACE = row("鵜飼和彦", "鵜飼和彦", "", "ukai@example.com", "uid-ukai", "key-ukai")

# (ID, 説明, 件名, 本文, 名簿の行, 名簿が読めたか, 期待値dict)
CASES = [
    # ---------------- 完全一致 ----------------
    ("M01", "フルネームが名簿と完全一致", "ご連絡",
     "担当審査官:青木健\n", [AOKI, KIRYU], True,
     {"status": "Matched", "name": "青木 健", "email": "aoki.k@example.com",
      "uid": "uid-aoki", "key": "key-aoki", "matched": "青木 健"}),
    ("M02", "推定側に空白が無くても突合できる（空白を除いて比較）", "ご連絡",
     "担当審査官:桐生慎太郎\n", [AOKI, KIRYU], True,
     {"status": "Matched", "name": "桐生慎太郎", "email": "kiryu@example.com",
      "matched": "桐生 慎太郎"}),
    ("M03", "名簿に同姓同名が2件（採用しない）", "ご連絡",
     "担当審査官:青木健\n",
     [AOKI, row("青木 健", "青木", "健", "aoki.dup@example.com", "uid-dup", "key-dup")], True,
     # 「青木健」は3文字なので検出側では姓のみ扱い。突合できないので分割もされない。
     {"status": "Ambiguous", "name": "青木健", "email": "", "uid": ""}),
    ("M04", "名簿に一致が無い", "ご連絡",
     "担当審査官:綾小路翔太\n", [AOKI, KIRYU], True,
     {"status": "NotFound", "name": "綾小路翔太", "email": ""}),

    # ---------------- 姓のみ → 名簿で補完 ----------------
    ("M05", "姓のみ＋名簿に該当1名（フルネームへ補完）", "ご連絡",
     "青木様\nお世話になっております。", [AOKI, KIRYU], True,
     {"status": "Matched", "name": "青木 健", "email": "aoki.k@example.com",
      "matched": "青木 健", "completion": "directory"}),
    ("M06", "姓のみ＋同姓が2名（補完しない）", "ご連絡",
     "青木様\nお世話になっております。", [AOKI, AOKI2], True,
     {"status": "Ambiguous", "name": "青木", "email": ""}),
    ("M07", "姓のみ＋名簿に該当なし", "ご連絡",
     "青木様\nお世話になっております。", [KIRYU], True,
     {"status": "NotFound", "name": "青木", "email": ""}),

    # ---------------- 名簿側の欠損・状態 ----------------
    ("M08", "在籍者だがメールアドレスが空", "ご連絡",
     "担当審査官:白鳥花子\n", [SHIRATORI], True,
     {"status": "Matched", "name": "白鳥 花子", "email": "", "uid": "uid-shiratori",
      "warn": "directory-email-empty"}),
    # 推定名は検出側の規則で「宇治 一明」に分割される（4文字は 2＋2）。突合はどちらでも効く。
    ("M09", "離脱者しか居ない（在籍者のみ対象なので突合しない）", "ご連絡",
     "担当審査官:宇治一明\n", [UJI_LEFT], True,
     {"status": "NotFound", "name": "宇治 一明", "email": ""}),
    ("M10", "名簿が空", "ご連絡",
     "担当審査官:青木健\n", [], True,
     {"status": "NotFound", "name": "青木健", "email": ""}),

    # ---------------- 突合しない／できない ----------------
    ("M11", "ひらがな推定名は突合しない", "ご連絡",
     "担当審査官:あおき\n", [AOKI], True,
     {"status": "NotFound", "name": "あおき", "email": ""}),
    ("M12", "審査官名が取れていない", "ご連絡",
     "お世話になっております。以上です。", [AOKI], True,
     {"status": "NoExaminer", "name": "", "email": ""}),
    ("M13", "名簿の取得に失敗（同期は止めない）", "ご連絡",
     "担当審査官:青木健\n", [], False,
     {"status": "RosterUnavailable", "name": "青木健", "email": "",
      "warn": "directory-unavailable"}),
    # 推定名「鵜飼 和彦」と名簿「鵜飼和彦」を、両方から空白を除いて突き合わせる
    ("M14", "名簿の氏名にスペースが無い行とも突合できる", "ご連絡",
     "担当審査官:鵜飼和彦\n", [NOSPACE], True,
     {"status": "Matched", "name": "鵜飼 和彦", "email": "ukai@example.com",
      "matched": "鵜飼和彦"}),
    ("M15", "フルネームが取れているときは姓では引かない（同姓の別人を拾わない）", "ご連絡",
     "担当審査官:青木健\n", [AOKI2], True,
     {"status": "NotFound", "name": "青木健", "email": ""}),
    # 同一人物が複数チャネル分の行として入っている場合。SyncKey が同じなので1人と扱う。
    ("M16", "同じ人物が複数行（SyncKeyが同一）なら曖昧にしない", "ご連絡",
     "担当審査官:青木健\n",
     [AOKI, row("青木 健", "青木", "健", "aoki.k@example.com", "uid-aoki", "key-aoki")], True,
     {"status": "Matched", "name": "青木 健", "email": "aoki.k@example.com",
      "key": "key-aoki"}),
    # SyncKey が空の行が複数あると同一性を確認できないため採用しない
    ("M17", "SyncKeyが空の行が複数あるときは採用しない", "ご連絡",
     "担当審査官:白鳥花子\n",
     [row("白鳥 花子", "白鳥", "花子", "a@example.com", "uid-a", ""),
      row("白鳥 花子", "白鳥", "花子", "b@example.com", "uid-b", "")], True,
     {"status": "Ambiguous", "name": "白鳥 花子", "email": ""}),
]


def run_one(subset, order, subject, body, roster_rows, roster_ready):
    ctx = Context(
        variables={"varItemBodyText": body, "varRosterReady": roster_ready},
        outputs={"Compose_Subject": subject, "Compose_Message_Id": "<test@example.com>",
                 "Compose_Sender": "sender@example.com"})
    # 名簿はループの前で1回だけ取得される。その応答をここで与える。
    ctx.bodies["Get_Roster_Items"] = {"value": list(roster_rows)}
    for name in order:
        a = subset[name]
        t = a.get("type")
        if t == "Compose":
            ctx.outputs[name] = RD.deep_eval(a["inputs"], ctx)
        elif t == "Query":
            src = RD.evaluate(a["inputs"]["from"], ctx)
            kept = []
            for el in (src or []):
                ctx.current_item = el
                if RD.evaluate(a["inputs"]["where"], ctx):
                    kept.append(el)
            ctx.current_item = None
            ctx.bodies[name] = kept
        else:
            raise ValueError("突合処理に想定外のアクション種別: %s (%s)" % (t, name))
    return ctx


def main():
    if not os.path.isdir(PKG):
        print("FATAL: パッケージ未生成。先に build_directory_flow.py を実行してください:", PKG)
        return 1
    flows = os.path.join(PKG, "Microsoft.Flow", "flows")
    guid = [d for d in os.listdir(flows) if os.path.isdir(os.path.join(flows, d))][0]
    import json
    with open(os.path.join(flows, guid, "definition.json"), encoding="utf-8") as f:
        definition = json.load(f)["properties"]["definition"]
    loop = RD.find_container(definition["actions"], "Foreach_Email")
    if loop is None:
        print("FATAL: Foreach_Email が見つからない")
        return 1
    subset = {n: a for n, a in loop["actions"].items() if n.startswith(DET_PREFIXES)}
    order = RD.topo(subset)

    print("=" * 78)
    print("審査官名簿との突合テスト（definition.json の式をそのまま評価）")
    print("検出＋突合アクション %d 件を評価順に実行する" % len(subset))
    print("=" * 78)

    # まず、検出チェーンが新フローでも無傷であることを確認する。
    # 名簿を空・未取得にすると突合は RosterUnavailable になり、
    # ExaminerName は本文からの推定結果（Compose_Ex_Final）のまま列に入る。
    det_pass = det_fail = 0
    for cid, desc, subject, body, expected in RD.CASES:
        try:
            ctx = run_one(subset, order, subject, body, [], False)
            ok = True
            if "ex" in expected:
                want = "" if expected["ex"] == RD.Q else expected["ex"]
                ok = ok and ctx.outputs.get("Compose_Ex_Final") == want
                # 名簿が使えないときは列に入る値も推定結果と一致する
                ok = ok and ctx.outputs.get("Compose_Dir_Name") == want
            if "app" in expected:
                want = "" if expected["app"] == RD.Q else expected["app"]
                ok = ok and ctx.outputs.get("Compose_App_Final") == want
            det_pass, det_fail = (det_pass + 1, det_fail) if ok else (det_pass, det_fail + 1)
            if not ok:
                print("FAIL [検出] %s %s -> ex=%r dir=%r"
                      % (cid, desc, ctx.outputs.get("Compose_Ex_Final"),
                         ctx.outputs.get("Compose_Dir_Name")))
        except Exception as e:                                   # noqa: BLE001
            det_fail += 1
            print("FAIL [検出] %s %s -> 例外: %s: %s" % (cid, desc, type(e).__name__, e))
    print("検出チェーンの回帰（新フローで再実行）: 合格 %d / 不合格 %d" % (det_pass, det_fail))
    print("-" * 78)

    passed, failed = 0, det_fail
    for cid, desc, subject, body, roster, ready, exp in CASES:
        try:
            ctx = run_one(subset, order, subject, body, roster, ready)
            res = ctx.outputs.get("Compose_Dir_Result") or {}
            diag = ctx.outputs.get("Compose_Detection_Diagnostics") or {}
            got = {
                "status": ctx.outputs.get("Compose_Dir_Status"),
                "name": ctx.outputs.get("Compose_Dir_Name"),
                "email": res.get("email"),
                "uid": res.get("teamsUserId"),
                "key": res.get("syncKey"),
                "matched": res.get("matchedName"),
                "completion": diag.get("completionSource"),
            }
            diffs = []
            for k, want in exp.items():
                if k == "warn":
                    if want not in (diag.get("warnings") or []):
                        diffs.append("    警告に %r が無い: %r" % (want, diag.get("warnings")))
                elif got.get(k) != want:
                    diffs.append("    %-10s 期待=%r / 実際=%r" % (k, want, got.get(k)))
            if diffs:
                failed += 1
                print("FAIL %s %s" % (cid, desc))
                for d in diffs:
                    print(d)
            else:
                passed += 1
                print("PASS %s %s" % (cid, desc))
        except Exception as e:                                   # noqa: BLE001
            failed += 1
            print("FAIL %s %s -> 例外: %s: %s" % (cid, desc, type(e).__name__, e))

    print("-" * 78)
    print("合格 %d / 不合格 %d（全 %d 件）" % (passed, failed, len(CASES)))
    print()
    print("※ 確認できないもの（要実環境確認）:")
    print("   - 名簿リストの実在と REST の応答形")
    print("   - 名簿が5,000件を超える場合の取りこぼし（ページング未実装）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

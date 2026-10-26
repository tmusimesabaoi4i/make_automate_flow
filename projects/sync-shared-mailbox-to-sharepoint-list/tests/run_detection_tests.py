# -*- coding: utf-8 -*-
"""
審査官名・出願番号の推定ロジックの回帰テスト（オフライン）。

生成済み definition.json から検出アクション（Compose_Det_* / Compose_App_* / Compose_Ex_* /
Filter_App_* / Filter_Ex_* / Compose_Detection_*）を名前で抽出し、
tools/wdl_eval.py で **定義に実際に書かれている式そのもの** を評価する。
設計書を読んで別実装したものを検証しているのではない。

  python run_detection_tests.py

【確認できること】
  件名・本文を入力したときに、検出チェーンが produce する審査官名・出願番号・信頼度。
【確認できないこと】
  Power Automate 実機での関数の挙動差、SharePointへの保存結果。要実環境確認。
"""
import json, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..", "tools")))
from wdl_eval import Context, evaluate   # noqa: E402

PKG = os.path.join(HERE, "..", "flows", "sync-mail-to-list-with-examiner-detection",
                   "source", "package")
DET_PREFIXES = ("Compose_Det_", "Compose_App_", "Compose_Ex_", "Filter_App_",
                "Filter_Ex_", "Compose_Detection_")

Q = "-"   # 期待値が空文字であることを表す

# (ID, 説明, 件名, 本文, 期待値dict)
CASES = [
    # ---------------- 出願番号（指示§14.3） ----------------
    ("A01", "件名に出願番号が1件", "特願2024-123456 の件について",
     "お世話になっております。よろしくお願いいたします。",
     {"app": "2024-123456"}),
    ("A02", "本文冒頭に出願番号", "ご連絡",
     "特願2024-123456 について、下記のとおりご連絡いたします。",
     {"app": "2024-123456"}),
    ("A03", "全角数字", "ご連絡",
     "出願番号 特願２０２４－１２３４５６ の件です。",
     {"app": "2024-123456"}),
    ("A04", "全角ハイフン", "ご連絡", "特願2024－123456 の件です。",
     {"app": "2024-123456"}),
    ("A05", "特願と数字の間に空白", "ご連絡", "特願 2024-123456 の件です。",
     {"app": "2024-123456"}),
    ("A06", "5桁の連番", "ご連絡", "特願2024-12345 の件です。",
     {"app": "2024-12345"}),
    ("A07", "同じ番号が複数回（一貫性ボーナス）", "ご連絡",
     "特願2024-123456 について。なお特願2024-123456 は先週提出済みです。",
     {"app": "2024-123456"}),
    ("A08", "引用メールに別の出願番号", "ご連絡",
     "特願2024-111111 の件です。\n-----Original Message-----\n"
     "差出人: someone\n特願2023-999999 についてご連絡しました。",
     {"app": "2024-111111"}),
    ("A09", "別件の近傍に別番号", "ご連絡",
     "出願番号 特願2024-111111 の件です。別件ですが特願2023-999999 もございます。",
     {"app": "2024-111111"}),
    ("A10", "出願番号が無い", "ご連絡", "お世話になっております。", {"app": Q}),
    ("A11", "特願はあるが番号形式でない", "ご連絡", "特願の件についてご連絡します。", {"app": Q}),

    # ---------------- 審査官名（指示§14.4） ----------------
    ("E01", "担当審査官：山田太郎", "ご連絡",
     "担当審査官:山田太郎\nよろしくお願いいたします。", {"ex": "山田 太郎"}),
    ("E02", "審査官 山田太郎 様", "ご連絡",
     "審査官 山田太郎 様\n\nお世話になっております。", {"ex": "山田 太郎"}),
    ("E03", "山田太郎 審査官", "ご連絡",
     "本日は山田太郎 審査官にご対応いただきました。", {"ex": "山田 太郎"}),
    ("E04", "部署名の次行に姓のみ", "ご連絡",
     "特許庁 審査第四部\n山田様\n\nお世話になっております。", {"ex": "山田"}),
    ("E05", "特許庁の山田太郎です（自己紹介）", "ご連絡",
     "特許庁の山田太郎です。標記の件についてご連絡します。", {"ex": "山田 太郎"}),
    ("E06", "現在と引用で異なる審査官名", "ご連絡",
     "担当審査官:山田太郎\nご連絡します。\n-----Original Message-----\n"
     "担当審査官:鈴木一郎\n前回のご連絡です。", {"ex": "山田 太郎"}),
    ("E07", "主担当と陪席審査官", "ご連絡",
     "担当審査官:山田太郎\n陪席審査官 鈴木一郎\n以上です。", {"ex": "山田 太郎"}),
    ("E08", "Cc欄に別の審査官名", "ご連絡",
     "担当審査官:山田太郎\nCc: 鈴木一郎 審査官\n以上です。", {"ex": "山田 太郎"}),
    ("E09", "弁理士名と審査官名が同居", "ご連絡",
     "担当審査官:山田太郎\n弁理士 佐藤次郎 様\n以上です。", {"ex": "山田 太郎"}),
    # 「山田様」から姓「山田」が採れるので、補完後に姓名の間へ空白が入る
    ("E10", "姓のみ＋フルネームが1件（補完される）", "ご連絡",
     "審査官 山田太郎 様\n\n山田様にご相談した件です。", {"ex": "山田 太郎"}),
    ("E11", "審査官名が無い", "ご連絡", "お世話になっております。以上です。", {"ex": Q}),
    ("E12", "組織名だけ（人名として採用しない）", "ご連絡",
     "特許庁 審査第四部\n\nお世話になっております。", {"ex": Q}),

    # ---------------- 正規化・スレッド分割 ----------------
    ("N01", "HTMLエンティティが復元される", "ご連絡",
     "担当審査官:山田太郎&nbsp;\n特願2024-123456 の件です。",
     {"ex": "山田 太郎", "app": "2024-123456"}),
    ("N02", "全角空白が半角化される", "ご連絡",
     "担当審査官:　山田太郎\n特願2024-123456", {"ex": "山田 太郎", "app": "2024-123456"}),
    ("N03", "全角コロンのラベル", "ご連絡",
     "担当審査官：山田太郎\n特願2024-123456", {"ex": "山田 太郎", "app": "2024-123456"}),
    ("N04", "定型誤記の補正（特許庁審査官）", "ご連絡",
     "特許庁審査官 山田太郎 様\n以上です。", {"ex": "山田 太郎"}),

    # ---------------- 併用・信頼度 ----------------
    ("C01", "件名に出願番号・本文に担当審査官", "特願2024-123456 について",
     "担当審査官:山田太郎\nよろしくお願いします。",
     {"app": "2024-123456", "ex": "山田 太郎", "review": False}),
    ("C02", "どちらも見つからない → 要確認", "ご連絡", "お世話になっております。",
     {"app": Q, "ex": Q, "review": True}),
    ("C03", "姓のみ（補完不可）→ 要確認", "ご連絡",
     "山田様\n\nお世話になっております。特願2024-123456 の件です。",
     {"app": "2024-123456", "review": True}),
    ("C04", "空の本文でも落ちない", "ご連絡", "", {"app": Q, "ex": Q}),
    ("C05", "空の件名・空の本文でも落ちない", "", "", {"app": Q, "ex": Q}),

    # ---------------- 件名からの抽出・件名と本文の競合 ----------------
    ("S01", "件名に担当審査官", "担当審査官：山田太郎",
     "標記の件についてご連絡します。", {"ex": "山田 太郎"}),
    ("S02", "件名と本文で出願番号が競合（件名を優先）", "特願2024-111111 について",
     "本文には特願2023-999999との記載があります。", {"app": "2024-111111"}),
    ("S03", "件名と引用本文で審査官が競合（件名を優先）", "担当審査官：山田太郎",
     "-----Original Message-----\n担当審査官：鈴木一郎", {"ex": "山田 太郎"}),

    # ---------------- 曖昧判定（要確認になること） ----------------
    ("B01", "同程度の主担当候補が2名", "ご連絡",
     "担当審査官：山田太郎\n担当審査官：鈴木一郎", {"review": True}),
    ("B02", "出願番号が同程度で2件", "ご連絡",
     "出願番号 特願2024-111111\n出願番号 特願2024-222222", {"review": True}),

    # ---------------- 除外対象しか存在しない（採用しないこと） ----------------
    ("X01", "陪席審査官しか存在しない", "ご連絡",
     "陪席審査官 鈴木一郎\n以上です。", {"ex": Q, "review": True}),
    ("X02", "Cc欄の審査官しか存在しない", "ご連絡",
     "Cc: 鈴木一郎 審査官\n以上です。", {"ex": Q, "review": True}),
    ("X03", "参加者欄の審査官しか存在しない", "ご連絡",
     "参加者：鈴木一郎 審査官\n以上です。", {"ex": Q, "review": True}),
    ("X04", "特許事務所所属者を審査官にしない", "ご連絡",
     "特許事務所所属 佐藤次郎 審査官\n以上です。", {"ex": Q, "review": True}),

    # ---------------- 審査官表現のバリエーション ----------------
    ("E13", "審査官補", "ご連絡",
     "審査官補 山田太郎 様\nよろしくお願いいたします。", {"ex": "山田 太郎"}),
    ("E14", "ひらがなの敬称さま", "ご連絡",
     "担当審査官：山田太郎さま\nよろしくお願いいたします。", {"ex": "山田 太郎"}),
    ("E15", "敬称が殿", "ご連絡",
     "審査官 山田太郎 殿\nよろしくお願いいたします。", {"ex": "山田 太郎"}),
    ("E16", "伝送システムの自己紹介", "ご連絡",
     "伝送システムの山田太郎でございます。", {"ex": "山田 太郎"}),

    # ---------------- 姓の補完 ----------------
    ("F01", "引用部分のフルネームで姓を補完", "ご連絡",
     "特許庁 審査第四部\n山田様\n-----Original Message-----\n担当審査官：山田太郎",
     {"ex": "山田 太郎"}),
    ("F02", "同姓のフルネームが複数あり補完不能", "ご連絡",
     "特許庁 審査第四部\n山田様\n-----Original Message-----\n"
     "山田太郎 審査官\n山田花子 審査官", {"ex": "山田", "review": True}),

    # ---------------- 姓名の間の半角スペース ----------------
    # 切れ目の根拠はまず**スレッド内の実データ**から採る。
    # 根拠が無い場合だけ、4文字ちょうどの氏名を 2＋2 で切る（5文字以上は切らない）。
    # 氏名はすべて架空のもの。
    ("G01", "署名の「特許庁＋姓」を根拠に姓名を分割", "面談の件",
     "青柳早紀子 審査官\n\nお世話になっております。\n\n"
     "特許庁\n審査第四部\n青柳\n", {"ex": "青柳 早紀子"}),
    ("G02", "引用部に空白付きの表記があればそれを採用", "ご連絡",
     "担当審査官：白鳥健之介\n-----Original Message-----\n審査官 白鳥 健之介 様\n",
     {"ex": "白鳥 健之介"}),
    ("G03", "3文字姓でも正しい位置で切る（2文字決め打ちなら誤る）", "ご連絡",
     "担当審査官：五十嵐悠一\n\n特許庁 五十嵐\n", {"ex": "五十嵐 悠一"}),
    ("G04", "根拠が無ければ切らない", "ご連絡",
     "担当審査官：桐生慎太郎\n", {"ex": "桐生慎太郎"}),
    # 5文字なので 2＋3／3＋2 のどちらとも決められず、根拠も曖昧なので切らない
    ("G05", "姓の候補が2種類あるので切らない", "ご連絡",
     "担当審査官：綾小路翔太\n\n特許庁 綾小\n特許庁 綾小路\n", {"ex": "綾小路翔太"}),
    ("G06", "自己紹介「特許庁の○○です」から姓を採って分割", "ご連絡",
     "担当審査官：相馬ゆかり\n\n特許庁の相馬です。よろしくお願いいたします。\n",
     {"ex": "相馬 ゆかり"}),
    ("G07", "1文字姓は切らない（既知の制約）", "ご連絡",
     "担当審査官：林一郎\n\n特許庁 林\n", {"ex": "林一郎"}),

    # ---------------- 罫線・部署名が名前の前に残る構造 ----------------
    # HTMLメールをテキスト化すると、注意書きの罫線と宛名が1行に潰れて入ってくる。
    # 人名は空白区切りの末尾1〜2トークンで、それより前は組織名——という構造で切り出す。
    # 部署名は伏せ字にしてある（実在の部署名も保存しない）。
    ("H01", "罫線＋部署名の後に氏名（空白なし）", "応答案のご確認のお願い",
     "＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊\n"
     "本メールはHTMLメールをテキスト化しているため、レイアウトが乱れる場合があります。\n"
     "＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊ 審査部門名称 相川直樹 審査官殿\n"
     "お世話になっております。弁理士の◯◯と申します。\n", {"ex": "相川 直樹"}),
    ("H02", "部署名の後に空白付きの氏名", "応答案の送付",
     "許庁 審査部門名称　東雲　実　様 お世話になっております。 弁理士の　◯◯　です。\n",
     {"ex": "東雲 実"}),
    ("H03", "部署名＋氏名＋審査官殿（罫線あり・敬称直結）", "補正案の送付",
     "＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊\n"
     "本メールはHTMLメールをテキスト化しているため、レイアウトが乱れる場合があります。\n"
     "＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊ 審査部門名称　矢代正明審査官殿\n"
     "特願2024-114145につきまして、補正案を作成しました。\n弁理士　◯◯\n",
     {"ex": "矢代 正明", "app": "2024-114145"}),
    ("H04", "組織名＋伝送システム＋審査官＋空白付き氏名", "補正書案の送付",
     "特許庁 審査部門名称　伝送システム 審査官　鵜飼　和彦　様\n"
     "いつもお世話になっております。◯◯の◯◯です。\n", {"ex": "鵜飼 和彦"}),
    ("H05", "敬称も役職も無い署名からフルネームを補完", "面接記録について",
     "特許庁 　尾花様\n　弁理士の◯◯です、お世話になります。\n"
     "-----Original Message-----\nFrom: 審査部門名称\n"
     "お世話になっております。特許庁の尾花です。\n本日は面接ありがとうございました。\n"
     "　特許庁審査部門名称　尾花　健\n", {"ex": "尾花 健"}),
    ("H06", "引用の末尾にだけフルネームがある", "面接審査のお願い",
     "宇治様 ◯◯株式会社の◯◯です。\n本日は誠にありがとうございました。\n"
     "-----Original Message-----\nFrom: 審査部門名称\n"
     "◯◯株式会社　◯◯様 特許庁の宇治です。\n本日はありがとうございました。\n"
     "-----Original Message-----\nFrom: ◯◯\n"
     "特許庁審査部門名称　宇治一明　様 ◯◯株式会社の◯◯と申します。\n",
     {"ex": "宇治 一明"}),

    # ---------------- 出願番号の境界 ----------------
    ("A12", "連番が4桁なので不正", "ご連絡", "特願2024-1234 の件です。", {"app": Q}),
    ("A13", "連番が7桁なので不正（先頭6桁を黙って採らない）", "ご連絡",
     "特願2024-1234567 の件です。", {"app": Q}),
    ("A14", "ハイフンなしなので不正", "ご連絡", "特願2024123456 の件です。", {"app": Q}),
    ("A15", "連番中のカンマを除去", "ご連絡", "特願2024-123,456 の件です。",
     {"app": "2024-123456"}),
    ("A16", "長音記号をハイフンとして正規化", "ご連絡", "特願2024ー123456 の件です。",
     {"app": "2024-123456"}),
    ("A17", "誤送信の番号を選ばない", "ご連絡",
     "本件は特願2024-111111です。先ほどの特願2023-999999は誤送信でした。",
     {"app": "2024-111111"}),

    # ---------------- 入力の頑健性 ----------------
    # 本来 HTML は Content Conversion がプレーンテキスト化してから渡される。
    # ここではタグが残って渡された場合でも壊れないことを確認する（保険）。
    ("N05", "HTMLタグが残っていても壊れない", "ご連絡",
     "<p>担当審査官：山田太郎</p><p>特願2024-123456 の件です。</p>",
     {"ex": "山田 太郎", "app": "2024-123456"}),
    ("N06", "brタグが残っていても壊れない", "ご連絡",
     "担当審査官：山田太郎<br>特願2024-123456", {"ex": "山田 太郎", "app": "2024-123456"}),
    ("N07", "タブと連続空白", "ご連絡",
     "担当審査官:\t  山田太郎\n特願2024-123456", {"ex": "山田 太郎", "app": "2024-123456"}),
    ("N08", "null入力でも落ちない", None, None, {"app": Q, "ex": Q, "review": True}),

    # ---------------- スレッド区切りのバリエーション ----------------
    # E06 は -----Original Message----- を見ている。ここは別の区切りを確認する。
    ("T01", "差出人ヘッダーで引用を分離", "ご連絡",
     "担当審査官：山田太郎\n差出人: previous@example.com\n担当審査官：鈴木一郎",
     {"ex": "山田 太郎"}),
    ("T02", "On ... wrote: 形式で引用を分離", "ご連絡",
     "担当審査官：山田太郎\nOn Mon, someone wrote:\n担当審査官：鈴木一郎",
     {"ex": "山田 太郎"}),

    # ---------------- 実メールの構造を再現した回帰テスト ----------------
    # 実データそのもの（氏名・住所）は保存しない。**構造だけ**を架空名で再現している。
    ("R01", "宛名ブロックの直後に差出人（弁理士）の署名がある", "面談記録の件",
     "特許庁\n審査第四部\n        山田　太郎　様\n\n\n"
     "先ほどはお電話にて、ありがとうございました。\n弁理士の佐藤です。\n\n"
     "面談記録、受け取りました。この内容で問題ございません。\n\n弁理士　佐藤\n",
     {"ex": "山田 太郎"}),
    ("R02", "引用部の文中「〜に加えて○○ 審査官が同席」を人名にしない", "面談記録の件",
     "特許庁\n審査第四部\n        山田　太郎　様\n\n"
     "先ほどはお電話にてありがとうございました。\n弁理士の佐藤です。\n\n"
     "> -----Original Message-----\n"
     "> なお、特許庁からは私（山田太郎）に加えて鈴木花子 審査官が同席いたします。\n",
     {"ex": "山田 太郎"}),
    ("R03", "引用記号付きの -----Original Message----- でも分離できる", "ご連絡",
     "担当審査官：山田太郎\n> -----Original Message-----\n> 担当審査官：鈴木一郎\n",
     {"ex": "山田 太郎"}),
    ("R04", "名前の後方に弁理士の署名があっても減点しない", "ご連絡",
     "審査官 山田太郎 様\n\nお世話になっております。\n弁理士の佐藤次郎です。\n",
     {"ex": "山田 太郎"}),

    # ================================================================
    # 補助資料（application_examiner_detection_algorithm_assist.md）由来
    # 氏名・部署名・社名はすべて架空。
    # ================================================================

    # ---------------- 資料§7.1 基本パターン ----------------
    ("P01", "特許庁 ○○ 様（PATTERN 1）", "ご連絡",
     "特許庁 逢坂様\n\nお世話になっております。", {"ex": "逢坂"}),
    ("P02", "特許庁 ○○部 ○○ 様（PATTERN 2）", "ご連絡",
     "特許庁 審査第四部 逢坂 誠一様\n\nお世話になっております。",
     {"ex": "逢坂 誠一", "diag": {"examinerNameType": "FullName"}}),
    ("P03", "特許庁 ○○部 ○○ 審査官（PATTERN 3）", "ご連絡",
     "特許庁 審査第四部 逢坂誠一 審査官\n\nお世話になっております。",
     {"ex": "逢坂 誠一"}),
    ("P04", "○○ 審査官殿（PATTERN 7）", "ご連絡",
     "逢坂 審査官殿\n\nお世話になっております。", {"ex": "逢坂"}),
    ("P05", "○○ ○○ 審査官（PATTERN 9・空白付きフルネーム）", "ご連絡",
     "逢坂 誠一 審査官\n\nお世話になっております。", {"ex": "逢坂 誠一"}),
    ("P06", "特許庁の○○です（PATTERN 10）", "ご連絡",
     "特許庁の逢坂です。標記の件でご連絡します。",
     {"ex": "逢坂", "diag": {"primaryExaminerEmail": "sender@example.com",
                            "primaryExaminerEmailEvidence": "self-introduction-in-current"}}),
    ("P07", "ひらがな姓の審査官表記（PATTERN 12）", "ご連絡",
     "おうさか 審査官殿\n\nお世話になっております。",
     {"ex": "おうさか", "review": True,
      "diag": {"examinerNameType": "HiraganaName", "ambiguityReason": "hiragana-unresolved",
               "warnings": ["hiragana-name"]}}),
    ("P08", "審査官補の表記", "ご連絡",
     "審査官補 逢坂誠一 様\nよろしくお願いいたします。", {"ex": "逢坂 誠一"}),

    # ---------------- 資料§7.2 スレッド ----------------
    ("Q01", "最新と引用で異なる審査官名（最新を採る）", "ご連絡",
     "担当審査官:逢坂誠一\nご連絡します。\n-----Original Message-----\n担当審査官:桐生慎\n",
     {"ex": "逢坂 誠一", "diag": {"sourceSection": "current", "examinerThreadDepth": 0}}),
    ("Q02", "最新は姓のみ・引用署名にフルネーム", "ご連絡",
     "逢坂様\nお世話になっております。\n-----Original Message-----\n"
     "特許庁 審査第四部 逢坂 誠一\n",
     {"ex": "逢坂 誠一", "diag": {"completionSource": "thread"}}),
    ("Q03", "最新と古い引用に同姓別人（補完しない）", "ご連絡",
     "逢坂様\nお世話になっております。\n-----Original Message-----\n"
     "逢坂誠一 審査官\n-----Original Message-----\n逢坂進 審査官\n",
     {"ex": "逢坂", "review": True,
      "diag": {"examinerNameType": "FamilyNameOnly", "completionSource": "none",
               "warnings": ["family-name-only"]}}),
    ("Q04", "引用が3階層（深いほど評価を下げる）", "ご連絡",
     "担当審査官:逢坂誠一\n-----Original Message-----\n担当審査官:桐生慎\n"
     "-----Original Message-----\n担当審査官:白鳥治\n",
     {"ex": "逢坂 誠一", "diag": {"examinerThreadDepth": 0}}),
    ("Q05", "転送ヘッダーの第三者名を審査官にしない", "ご連絡",
     "担当審査官:逢坂誠一\n-----Original Message-----\n"
     "From: 鵜飼 太郎\nTo: 白鳥 花子\n以上です。\n",
     {"ex": "逢坂 誠一"}),

    # ---------------- 資料§7.3 誤検出防止 ----------------
    ("V01", "弁理士名に「様」が付いている", "ご連絡",
     "担当審査官:逢坂誠一\n弁理士 桐生慎太郎 様\n以上です。", {"ex": "逢坂 誠一"}),
    ("V02", "出願人担当者名が宛名にある", "ご連絡",
     "出願人 桐生慎太郎 様\nお世話になっております。", {"ex": Q, "review": True}),
    ("V03", "参加者一覧に複数名", "ご連絡",
     "参加者：桐生慎太郎 審査官\n参加者：白鳥花子 審査官\n以上です。",
     {"ex": Q, "review": True}),
    # 資料§3.5「Ccに含まれることだけを理由に除外しない」。除外は**出現位置ごと**なので、
    # 本文に明示された審査官は Cc に同姓者がいても生き残る。
    ("V04", "Cc欄に審査官と同姓の人物がいても本文の審査官が勝つ", "ご連絡",
     "担当審査官:逢坂誠一\nCc: 逢坂一郎\n以上です。",
     {"ex": "逢坂 誠一", "diag": {"sourceSection": "current"}}),
    ("V05", "組織名を人名と誤認しない", "ご連絡",
     "特許庁 審査第四部\n\nお世話になっております。", {"ex": Q}),
    ("V06", "「審査官」の一般論的な用法", "ご連絡",
     "審査官の判断により拒絶理由が通知されることがあります。", {"ex": Q}),
    ("V07", "署名欄の外部企業担当者を審査官にしない", "ご連絡",
     "お世話になっております。\n\n株式会社かささぎ 桐生慎太郎\n以上です。",
     {"ex": Q, "review": True}),

    # ---------------- 資料§7.4 氏名補完 ----------------
    ("W01", "姓に対応するフルネームが1名のみ", "ご連絡",
     "逢坂様\n-----Original Message-----\n担当審査官:逢坂誠一\n",
     {"ex": "逢坂 誠一", "diag": {"completionSource": "thread"}}),
    ("W02", "同姓のフルネームが複数（補完しない）", "ご連絡",
     "逢坂様\n-----Original Message-----\n逢坂誠一 審査官\n逢坂進 審査官\n",
     {"ex": "逢坂", "diag": {"completionSource": "none"}}),
    ("W03", "ひらがな表記に対応する漢字があっても変換しない", "ご連絡",
     "担当審査官:おうさか\n-----Original Message-----\n逢坂誠一 審査官\n",
     {"ex": "おうさか", "review": True,
      "diag": {"examinerNameType": "HiraganaName", "completionSource": "none"}}),
    ("W04", "同じひらがな読みが複数あっても変換しない", "ご連絡",
     "担当審査官:おうさか\n-----Original Message-----\n逢坂誠一 審査官\n大坂進 審査官\n",
     {"ex": "おうさか", "review": True, "diag": {"examinerNameType": "HiraganaName"}}),
    ("W05", "スレッド内に証拠が無ければ補完しない", "ご連絡",
     "逢坂様\nお世話になっております。",
     {"ex": "逢坂", "diag": {"completionSource": "none"}}),
    ("W06", "補完不能なら姓のまま返す（フルネームを捏造しない）", "ご連絡",
     "特許庁 審査第四部\n逢坂様\n以上です。",
     {"ex": "逢坂", "review": True, "diag": {"examinerNameType": "FamilyNameOnly"}}),

    # ---------------- 資料§7.5 出願番号との関連 ----------------
    ("Y01", "件名と本文で異なる出願番号（件名を優先）", "特願2024-111111 の件",
     "本文には特願2023-999999 との記載があります。", {"app": "2024-111111"}),
    ("Y02", "最新と引用で異なる番号（最新を優先）", "ご連絡",
     "特願2024-111111 の件です。\n-----Original Message-----\n特願2023-999999 の件でした。",
     {"app": "2024-111111"}),
    ("Y03", "審査官と同じ区画に出願番号がある", "ご連絡",
     "担当審査官:逢坂誠一\n出願番号 特願2024-111111 の件です。\n"
     "-----Original Message-----\n担当審査官:桐生慎\n",
     {"ex": "逢坂 誠一", "app": "2024-111111",
      "diag": {"sourceSection": "current", "examinerThreadDepth": 0}}),
    ("Y04", "1通で複数案件が言及されている（要確認になる）", "ご連絡",
     "出願番号 特願2024-111111\n出願番号 特願2024-222222\nいずれもご確認ください。",
     {"review": True, "diag": {"warnings": ["application-ambiguous"]}}),
    ("Y05", "全角数字と全角ハイフン", "ご連絡",
     "特願２０２４－１１１１１１ の件です。", {"app": "2024-111111"}),
    ("Y06", "出願番号らしいが桁数が不正", "ご連絡",
     "特願2024-1234 の件です。", {"app": Q, "diag": {"warnings": ["application-not-found"]}}),
]


def load_definition():
    flows = os.path.join(PKG, "Microsoft.Flow", "flows")
    guid = [d for d in os.listdir(flows) if os.path.isdir(os.path.join(flows, d))][0]
    with open(os.path.join(flows, guid, "definition.json"), encoding="utf-8") as f:
        return json.load(f)["properties"]["definition"]


def find_container(actions, target):
    for name, a in actions.items():
        if name == target:
            return a
        if isinstance(a, dict):
            if isinstance(a.get("actions"), dict):
                r = find_container(a["actions"], target)
                if r is not None:
                    return r
            if isinstance(a.get("else"), dict):
                r = find_container(a["else"].get("actions", {}), target)
                if r is not None:
                    return r
    return None


def topo(subset):
    """runAfter（subset 内に限る）で位相ソートする"""
    names = list(subset.keys())
    placed, order, guard = set(), [], 0
    while len(order) < len(names) and guard < 10000:
        guard += 1
        for n in names:
            if n in placed:
                continue
            deps = [t for t in (subset[n].get("runAfter") or {}) if t in subset]
            if all(d in placed for d in deps):
                order.append(n)
                placed.add(n)
    if len(order) != len(names):
        raise ValueError("runAfter が循環している: %s" % [n for n in names if n not in placed])
    return order


def deep_eval(node, ctx):
    if isinstance(node, dict):
        return {k: deep_eval(v, ctx) for k, v in node.items()}
    if isinstance(node, list):
        return [deep_eval(v, ctx) for v in node]
    if isinstance(node, str):
        return evaluate(node, ctx)
    return node


def run_detection(subset, order, subject, body, message_id="<test@example.com>",
                  sender="sender@example.com"):
    # Compose_Sender は検出チェーンの外（item_seq）で作られる。
    # 診断が「自己紹介があるときだけ審査官のメールアドレスを載せる」ために参照するので、
    # ここで入力として与える。アドレスは架空のもの。
    ctx = Context(variables={"varItemBodyText": body},
                  outputs={"Compose_Subject": subject, "Compose_Message_Id": message_id,
                           "Compose_Sender": sender})
    for name in order:
        a = subset[name]
        t = a.get("type")
        if t == "Compose":
            ctx.outputs[name] = deep_eval(a["inputs"], ctx)
        elif t == "Query":
            src = evaluate(a["inputs"]["from"], ctx)
            where = a["inputs"]["where"]
            kept = []
            for el in (src or []):
                ctx.current_item = el
                if evaluate(where, ctx):
                    kept.append(el)
            ctx.current_item = None
            ctx.bodies[name] = kept
        else:
            raise ValueError("検出処理に想定外のアクション種別: %s (%s)" % (t, name))
    return ctx


def main():
    if not os.path.isdir(PKG):
        print("FATAL: パッケージ未生成。先に build_examiner_flow.py を実行してください:", PKG)
        return 1
    definition = load_definition()
    loop = find_container(definition["actions"], "Foreach_Email")
    if loop is None:
        print("FATAL: Foreach_Email が見つからない")
        return 1
    subset = {n: a for n, a in loop["actions"].items() if n.startswith(DET_PREFIXES)}
    order = topo(subset)

    print("=" * 78)
    print("審査官名・出願番号の推定テスト（definition.json の式をそのまま評価）")
    print("検出アクション %d 件を評価順に実行する" % len(subset))
    print("=" * 78)

    passed = failed = 0
    for cid, desc, subject, body, expected in CASES:
        try:
            ctx = run_detection(subset, order, subject, body)
            got_ex = ctx.outputs.get("Compose_Ex_Final", "")
            got_app = ctx.outputs.get("Compose_App_Final", "")
            got_rev = ctx.outputs.get("Compose_Det_NeedsReview")
            diffs = []
            if "ex" in expected:
                want = "" if expected["ex"] == Q else expected["ex"]
                if got_ex != want:
                    diffs.append("    審査官名: 期待=%r / 実際=%r" % (want, got_ex))
            if "app" in expected:
                want = "" if expected["app"] == Q else expected["app"]
                if got_app != want:
                    diffs.append("    出願番号: 期待=%r / 実際=%r" % (want, got_app))
            if "review" in expected and got_rev != expected["review"]:
                diffs.append("    要確認: 期待=%r / 実際=%r" % (expected["review"], got_rev))
            # 診断（採用根拠・氏名種別・区画・曖昧理由・警告）の突き合わせ。
            # 最終氏名だけでなく「なぜそう決めたか」を固定する（補助資料§7）。
            diag = ctx.outputs.get("Compose_Detection_Diagnostics") or {}
            for key, want in (expected.get("diag") or {}).items():
                got = diag.get(key)
                if key == "warnings":
                    # warnings は「含むこと」を確認する（順序と他の警告は問わない）
                    missing = [w for w in want if w not in (got or [])]
                    if missing:
                        diffs.append("    警告に不足: %r / 実際=%r" % (missing, got))
                elif got != want:
                    diffs.append("    %s: 期待=%r / 実際=%r" % (key, want, got))
            if diffs:
                failed += 1
                print("FAIL %s %s" % (cid, desc))
                for d in diffs:
                    print(d)
                print("     ex=%r app=%r conf=%r/%r"
                      % (got_ex, got_app,
                         ctx.outputs.get("Compose_Ex_Confidence"),
                         ctx.outputs.get("Compose_App_Confidence")))
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
    print("   - Power Automate 実機での関数の挙動差")
    print("   - SharePoint 列への保存結果、既定ビューの並び順")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

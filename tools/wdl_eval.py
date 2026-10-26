# -*- coding: utf-8 -*-
"""
Power Automate（ワークフロー定義言語 / WDL）式のミニ評価器（案件横断の共通ツール）。

目的は「definition.json に実際に書かれている式文字列そのもの」をオフラインで評価し、
URL解析などのロジックの正しさを実機を使わずに検証すること。
各案件の tests/ から import して使う（同一実装を案件ごとに複製しない）。

  import sys, os
  sys.path.insert(0, "<リポジトリルート>/tools")
  from wdl_eval import Context, evaluate, eval_condition

実装しているのは、本リポジトリのフローが実際に使う関数のサブセットのみ。汎用の実装ではない。
未実装の関数に出会うと ValueError を投げる（黙って誤評価しない）。

【この評価器で確認できること】
  URL文字列を入力したときに、定義中の式チェーンがどの値を produce するか。
【この評価器では確認できないこと】
  Power Automate 実機での関数の細かな挙動差・コネクタ応答・保存時検証・実行時エラー。
  実機の挙動は「要実環境確認」として扱う。

実装した関数のセマンティクスは docs/url_parsing_spec.md に根拠つきで記載する。
"""
import json
import urllib.parse


# =========================================================================
# トークナイザ
# =========================================================================
class Token(object):
    def __init__(self, kind, value, pos):
        self.kind, self.value, self.pos = kind, value, pos

    def __repr__(self):
        return "Token(%s,%r)" % (self.kind, self.value)


def tokenize(s):
    toks, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "'":
            # 単一引用符文字列。'' は引用符のエスケープ
            i += 1
            buf = []
            while i < n:
                if s[i] == "'":
                    if i + 1 < n and s[i + 1] == "'":
                        buf.append("'")
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(s[i])
                i += 1
            else:
                raise ValueError("閉じられていない文字列リテラル: %r" % s)
            toks.append(Token("STRING", "".join(buf), i))
            continue
        if c.isdigit() or (c == "-" and i + 1 < n and s[i + 1].isdigit()):
            j = i + 1
            while j < n and (s[j].isdigit() or s[j] == "."):
                j += 1
            text = s[i:j]
            toks.append(Token("NUMBER", float(text) if "." in text else int(text), j))
            i = j
            continue
        if c.isalpha() or c == "_" or c == "$":
            j = i
            while j < n and (s[j].isalnum() or s[j] in "_$"):
                j += 1
            toks.append(Token("IDENT", s[i:j], j))
            i = j
            continue
        if c in "()[],?.":
            toks.append(Token(c, c, i))
            i += 1
            continue
        raise ValueError("解釈できない文字 %r (位置 %d) in %r" % (c, i, s))
    toks.append(Token("EOF", None, n))
    return toks


# =========================================================================
# パーサ（再帰下降）
#   expr    := primary postfix*
#   primary := STRING | NUMBER | 'true'|'false'|'null' | IDENT '(' args ')'
#   postfix := '?' '[' expr ']' | '[' expr ']' | '.' IDENT
# =========================================================================
class Parser(object):
    def __init__(self, toks):
        self.toks, self.i = toks, 0

    def peek(self):
        return self.toks[self.i]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, kind):
        t = self.next()
        if t.kind != kind:
            raise ValueError("期待 %s だが %r" % (kind, t))
        return t

    def parse(self):
        node = self.parse_expr()
        if self.peek().kind != "EOF":
            raise ValueError("式の末尾に余分なトークン: %r" % self.peek())
        return node

    def parse_expr(self):
        node = self.parse_primary()
        while True:
            k = self.peek().kind
            if k == "?":
                self.next()
                self.expect("[")
                idx = self.parse_expr()
                self.expect("]")
                node = ("index", node, idx, True)
            elif k == "[":
                self.next()
                idx = self.parse_expr()
                self.expect("]")
                node = ("index", node, idx, False)
            elif k == ".":
                self.next()
                name = self.expect("IDENT").value
                node = ("index", node, ("lit", name), True)
            else:
                break
        return node

    def parse_primary(self):
        t = self.next()
        if t.kind == "STRING":
            return ("lit", t.value)
        if t.kind == "NUMBER":
            return ("lit", t.value)
        if t.kind == "IDENT":
            low = t.value.lower()
            if low in ("true", "false", "null") and self.peek().kind != "(":
                return ("lit", {"true": True, "false": False, "null": None}[low])
            self.expect("(")
            args = []
            if self.peek().kind != ")":
                args.append(self.parse_expr())
                while self.peek().kind == ",":
                    self.next()
                    args.append(self.parse_expr())
            self.expect(")")
            return ("call", t.value, args)
        raise ValueError("予期しないトークン: %r" % t)


# =========================================================================
# 関数実装（Power Automate のセマンティクスに合わせる）
# =========================================================================
def _is_empty(x):
    if x is None:
        return True
    if isinstance(x, (str, list, dict)):
        return len(x) == 0
    return False


def _to_str(x):
    if x is None:
        return ""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, (dict, list)):
        return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    return str(x)


def f_coalesce(*args):
    for a in args:
        if a is not None:
            return a
    return None


def f_first(coll):
    if coll is None or len(coll) == 0:
        return None
    return coll[0]


def f_last(coll):
    if coll is None or len(coll) == 0:
        return None
    return coll[-1]


def f_contains(coll, val):
    """WDL contains(): 文字列は大文字小文字を区別する"""
    if coll is None:
        return False
    if isinstance(coll, str):
        return _to_str(val) in coll
    if isinstance(coll, dict):
        return val in coll
    return val in coll


def f_endswith(s, suf):
    """WDL endsWith(): 大文字小文字を区別しない"""
    return _to_str(s).lower().endswith(_to_str(suf).lower())


def f_startswith(s, pre):
    return _to_str(s).lower().startswith(_to_str(pre).lower())


def f_split(s, sep):
    return _to_str(s).split(_to_str(sep))


def f_take(coll, n):
    n = int(n)
    if n <= 0:
        return [] if not isinstance(coll, str) else ""
    return coll[:n]


def f_union(*colls):
    """WDL union(): 重複を排除して結合（配列想定）"""
    out = []
    for c in colls:
        for v in (c or []):
            if v not in out:
                out.append(v)
    return out


def f_substring(s, start, length=None):
    """Power Automate の substring。開始位置は **文字列長より小さい**必要がある。

    実機のエラー文言（2026-08-04 に実環境で発生）:
      'The template language function 'substring' parameter is out of range:
       'start index' must be non-negative integer and should be less than the
       length of the string.'

    したがって **空文字に対する substring('', 0, 0) も失敗する**（0 < 0 が偽）。
    以前この評価器は start == len(s) を許容していたため、空文字ケースのテストが
    通ってしまい実機で初めて落ちた。実機に合わせて厳密にする。
    """
    s = _to_str(s)
    start = int(start)
    if start < 0 or start >= len(s):
        raise ValueError(
            "substring: 開始位置は0以上かつ文字列長より小さい必要がある "
            "(len=%d, start=%d)。空文字には substring を適用できない" % (len(s), start))
    if length is None:
        return s[start:]
    length = int(length)
    if length < 0 or start + length > len(s):
        raise ValueError("substring: 長さが範囲外 (len=%d, start=%d, length=%d)"
                         % (len(s), start, length))
    return s[start:start + length]


def f_sort(coll, key=None):
    """Power Automate の sort()。昇順のみ（降順は reverse() を併用する）。
    key を与えるとオブジェクト配列をそのプロパティで並べ替える。
    Power Automate に合わせ、キーの型が混在する場合は文字列として比較する。"""
    items = list(coll or [])
    if key is None:
        try:
            return sorted(items)
        except TypeError:
            return sorted(items, key=_to_str)
    def _k(x):
        v = x.get(key) if isinstance(x, dict) else None
        return v
    vals = [_k(x) for x in items]
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return sorted(items, key=_k)
    return sorted(items, key=lambda x: _to_str(_k(x)))


FUNCS = {
    # 文字列
    "concat": lambda *a: "".join(_to_str(x) for x in a),
    "trim": lambda s: _to_str(s).strip(),
    "split": f_split,
    "replace": lambda s, a, b: _to_str(s).replace(_to_str(a), _to_str(b)),
    "substring": f_substring,
    "length": lambda x: len(x) if x is not None else 0,
    "indexOf": lambda s, v: _to_str(s).find(_to_str(v)),
    "lastIndexOf": lambda s, v: _to_str(s).rfind(_to_str(v)),
    "endsWith": f_endswith,
    "startsWith": f_startswith,
    "join": lambda coll, sep: _to_str(sep).join(_to_str(x) for x in (coll or [])),
    "string": _to_str,
    "toLower": lambda s: _to_str(s).lower(),
    "toUpper": lambda s: _to_str(s).upper(),
    # 配列・オブジェクト
    "first": f_first,
    "last": f_last,
    "take": f_take,
    "union": f_union,
    "createArray": lambda *a: list(a),
    "sort": f_sort,
    "reverse": lambda coll: list(reversed(list(coll or []))),
    "json": lambda s: json.loads(s) if isinstance(s, str) else s,
    # 論理・比較
    "if": lambda c, a, b: a if c else b,
    "not": lambda b: not b,
    "and": lambda *a: all(a),
    "or": lambda *a: any(a),
    "equals": lambda a, b: a == b,
    "empty": _is_empty,
    "contains": f_contains,
    "greater": lambda a, b: a > b,
    "greaterOrEquals": lambda a, b: a >= b,
    "less": lambda a, b: a < b,
    "lessOrEquals": lambda a, b: a <= b,
    "coalesce": f_coalesce,
    # 数値
    "int": lambda x: int(x),
    "sub": lambda a, b: a - b,
    "add": lambda a, b: a + b,
    "mul": lambda a, b: a * b,
    # URI
    "uriComponent": lambda s: urllib.parse.quote(_to_str(s), safe=""),
    "decodeUriComponent": lambda s: urllib.parse.unquote(_to_str(s)),
}


class Context(object):
    """変数・アクション出力・トリガー本文を保持する評価コンテキスト"""

    def __init__(self, variables=None, outputs=None, bodies=None, trigger_body=None,
                 current_item=None, loop_items=None):
        self.variables = variables if variables is not None else {}
        self.outputs = outputs if outputs is not None else {}
        self.bodies = bodies if bodies is not None else {}
        self.trigger_body = trigger_body if trigger_body is not None else {}
        # Query（Filter array）/ Select の item() 評価用。ループ中だけ値が入る
        self.current_item = current_item
        # 名前付きループの items('<ループ名>') 評価用。{ループ名: 現在の要素}
        # 入れ子ループでは内側から item() ではなく items('名前') で外側を参照するため必要。
        self.loop_items = loop_items if loop_items is not None else {}


def _eval_node(node, ctx):
    kind = node[0]
    if kind == "lit":
        return node[1]
    if kind == "index":
        base = _eval_node(node[1], ctx)
        key = _eval_node(node[2], ctx)
        safe = node[3]
        if base is None:
            if safe:
                return None
            raise ValueError("null に対する索引アクセス: %r" % (key,))
        if isinstance(base, dict):
            return base.get(key) if safe else base[key]
        if isinstance(base, list):
            idx = int(key)
            if safe and (idx < 0 or idx >= len(base)):
                return None
            return base[idx]
        raise ValueError("索引アクセスできない型: %r" % type(base))
    if kind == "call":
        name, args = node[1], node[2]
        low = name.lower()
        if low == "variables":
            vname = _eval_node(args[0], ctx)
            if vname not in ctx.variables:
                raise ValueError("未初期化変数の参照: %s" % vname)
            return ctx.variables[vname]
        if low == "outputs":
            aname = _eval_node(args[0], ctx)
            if aname not in ctx.outputs:
                raise ValueError("未実行アクションの outputs 参照: %s" % aname)
            return ctx.outputs[aname]
        if low == "body":
            aname = _eval_node(args[0], ctx)
            if aname not in ctx.bodies:
                raise ValueError("未実行アクションの body 参照: %s" % aname)
            return ctx.bodies[aname]
        if low == "item":
            if ctx.current_item is None:
                raise ValueError("ループ外での item() 参照")
            return ctx.current_item
        if low == "items":
            lname = _eval_node(args[0], ctx)
            if lname not in ctx.loop_items:
                raise ValueError("ループ外での items('%s') 参照" % lname)
            return ctx.loop_items[lname]
        if low == "workflow":
            return {"run": {"name": "00000000-0000-0000-0000-000000000000"}}
        if low == "triggerbody":
            return ctx.trigger_body
        if low == "utcnow":
            return "2026-07-24T00:00:00.0000000Z"   # 決定的な値に固定（テスト再現性のため）
        vals = [_eval_node(a, ctx) for a in args]    # PA同様に引数を先行評価する
        for fname, fn in FUNCS.items():
            if fname.lower() == low:
                return fn(*vals)
        raise ValueError("未実装の関数: %s" % name)
    raise ValueError("未知のノード: %r" % (node,))


_CACHE = {}


def evaluate(expr, ctx):
    """'@' で始まる式文字列、または通常の文字列リテラルを評価する"""
    if not isinstance(expr, str):
        return expr
    if not expr.startswith("@"):
        return expr            # 補間 @{} は本フローの解析チェーンでは使用していない
    body = expr[1:]
    if body not in _CACHE:
        _CACHE[body] = Parser(tokenize(body)).parse()
    return _eval_node(_CACHE[body], ctx)


def eval_condition(expr_obj, ctx):
    """If アクションの expression（{"and":[{"equals":[a,b]}]} 形式）を評価する"""
    if isinstance(expr_obj, str):
        return bool(evaluate(expr_obj, ctx))
    if not isinstance(expr_obj, dict) or len(expr_obj) != 1:
        raise ValueError("解釈できない条件: %r" % (expr_obj,))
    op, operand = list(expr_obj.items())[0]
    if op == "and":
        return all(eval_condition(o, ctx) for o in operand)
    if op == "or":
        return any(eval_condition(o, ctx) for o in operand)
    if op == "not":
        return not eval_condition(operand, ctx)
    vals = [evaluate(o, ctx) for o in operand]
    if op == "equals":
        return vals[0] == vals[1]
    if op == "greater":
        return vals[0] > vals[1]
    if op == "less":
        return vals[0] < vals[1]
    raise ValueError("未実装の条件演算子: %s" % op)

# -*- coding: utf-8 -*-
"""
release/ の最新ZIPを再展開して source/package と完全一致することを確かめる。

  python validation/extract_check.py            release/ の最新ZIPを検査
  python validation/extract_check.py <zip>      指定のZIPを検査

検査の中身は shared/extract_check_lib.py（両フロー共通）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.abspath(os.path.join(FLOW, "..", "..", "shared")))

import extract_check_lib as lib  # noqa: E402

if __name__ == "__main__":
    sys.exit(lib.run(
        release_dir=os.path.join(FLOW, "release"),
        package_dir=os.path.join(FLOW, "source", "package"),
        out_path=os.path.join(HERE, "extract_check_result.txt"),
        zip_path=sys.argv[1] if len(sys.argv) > 1 else None,
        title="TeamsChannelMemberSync_Daily"))

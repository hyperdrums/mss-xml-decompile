"""逆生成した .cfg を、MSS Configurator の画面の言葉で一覧・比較する。"""
import argparse
import glob
import os
import re
import sys

import mssdc

# 画面定義（PFSOC_*.xml）に表示名が無いパラメータの表示名
PARTITION = {"CACHED_32BIT": "Cached 1GB", "CACHED_64BIT": "Cached 16GB",
             "NON_CACHED_32BIT": "Non-Cached 256MB", "NON_CACHED_64BIT": "Non-Cached 16GB"}
DDR_FILES = {"PFSOC_DDR3.xml", "PFSOC_DDR4.xml", "PFSOC_LPDDR3.xml", "PFSOC_LPDDR4.xml"}


def load_labels():
    lab = {}
    for f in glob.glob(os.path.join(mssdc.DATA, "PFSOC_*.xml")):
        s = open(f, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"<actel-cc:variantParameter ([^>]*)>", s):
            a = dict(re.findall(r'([\w:-]+)="([^"]*)"', m.group(1)))
            n, prompt = a.get("spirit:name"), a.get("spirit:prompt", "").strip().rstrip(":").strip()
            if not n or not prompt:
                continue
            grp = a.get("spirit:configGroups", "")
            page, _, sub = grp.partition("@")[2], None, grp.partition("@")[0].partition(":")[2]
            if os.path.basename(f) in DDR_FILES or page == "DDR Topology":
                page = "DDR Memory > " + page
            lab[n] = (page or "その他", sub, prompt)
    for k, name in PARTITION.items():
        lab[f"DDR_{k}_MEM_SIZE"] = ("Memory Partition", name, "Range")
        lab[f"DDR_{k}_MEM_UNIT"] = ("Memory Partition", name, "Range の単位")
        lab[f"DDR_{k}_PHY_OFFSET"] = ("Memory Partition", name, "Physical DDR Offset Address")
    lab["MSS_MANUAL_DDR_PHY_OFFSET_ENABLE"] = ("Memory Partition", "", "Setup Physical DDR Offset Address manually")
    lab["DIE"] = ("Device", "", "Die")
    lab["PACKAGE"] = ("Device", "", "Package")
    lab["DDR_TRACE_PHY_OFFSET"] = ("Memory Partition", "Trace", "Physical DDR Offset Address")
    return lab


LABELS = load_labels()

# 範囲（DDR・IO・メモリマップ・クロック・FIC）。それ以外はパラメータ名で出す
SCOPE = re.compile(r"^(Device|DDR Memory|Memory Partition|I/O Bank|I/O REFCLK|IO Configuration|Clocks|Fabric Interface)")


def where(n):
    page, sub, prompt = LABELS.get(n, ("(画面名未対応)", "", n))
    return page, sub, prompt


def show(n, v):
    lab = mssdc.label(n, v)
    return f"{v}（{lab}）" if lab and lab != v else v


def determinable(cfg, names, gen):
    """各パラメータを変えたとき XML が変わるか（= XML から値が決まるか）。"""
    _, base_xml, _ = gen.run(cfg)
    probes, owners = [], []
    for n in names:
        c = mssdc.candidates(n, cfg[n])
        if c:
            alts = [v for v in c if v != cfg[n]]
        else:
            p = mssdc.num_probe(n, cfg[n])
            v0, kind = mssdc.parse_num(cfg[n])
            alts = [p] if p else []
            if v0 is not None and kind != "hex":  # 小さく動かして幅があるかを見る
                small = mssdc.fmt_num(v0 + 1 if kind == "int" else (v0 * 1.02 if v0 else 0.01), kind, cfg[n])
                if small != cfg[n] and small not in alts:
                    alts.append(small)
        for v in alts:
            probes.append(dict(cfg, **{n: v}))
            owners.append((n, v))
    res = {}
    for (n, v), (eff, x, ok) in zip(owners, gen.many(probes)):
        r = res.setdefault(n, {"changed": False, "ok": 0, "small_same": False})
        if not ok:
            continue
        r["ok"] += 1
        if x != base_xml:
            r["changed"] = True
        elif mssdc.candidates(n, cfg[n]) is None and v != mssdc.num_probe(n, cfg[n])                 and mssdc.parse_num(cfg[n])[1] != "int":
            r["small_same"] = True
    out = {}
    for n in names:
        if gated_note(n, cfg):
            out[n] = gated_note(n, cfg)
            continue
        r = res.get(n, {"changed": False, "ok": 0, "small_same": False})
        if r["changed"]:
            out[n] = "幅あり" if r["small_same"] else "確定"
        elif r["ok"] == 0:
            out[n] = "確定（他の値は DRC エラー）"
        else:
            out[n] = "XML から決まらない"
    return out


DDR_PREFIX = {"DDR3": "DDR3_", "DDR3L": "DDR3_", "DDR4": "DDR4_", "LPDDR3": "LPDDR3_", "LPDDR4": "LPDDR4_"}


def in_scope(n, cfg=None):
    if not SCOPE.match(where(n)[0]):
        return False
    if cfg is not None:  # 選んでいない DDR の種類の設定は画面に出ないので除く
        m = re.match(r"^(DDR3|DDR4|LPDDR3|LPDDR4)_", n)
        if m and DDR_PREFIX.get(cfg.get("DDR_SDRAM_TYPE"), "") != m.group(1) + "_":
            return False
    return True


def gated_note(n, cfg):
    g = mssdc.gate_for(n)
    if g and any(cfg.get(k) != v for k, v in g.items()):
        return "自動計算（" + "、".join(where(k)[2] for k in g) + " がオフ）"
    return None


def md_table(rows, header):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(out)


def cmd_list(a):
    cfg = mssdc.read_cfg(a.cfg)
    gen = mssdc.Gen()
    names = sorted(n for n in cfg if in_scope(n, cfg))
    det = determinable(cfg, names, gen)
    rows = sorted((*where(n), show(n, cfg[n]), det[n], n) for n in names if det[n] != "XML から決まらない")
    und = sorted((*where(n), show(n, cfg[n]), n) for n in names if det[n] == "XML から決まらない")
    lines = [f"# {os.path.basename(a.cfg)}", "",
             "判定：確定＝XML から値が一意に決まる。幅あり＝近い値でも XML が同じになる（ns の丸めなど）ため、"
             "表の値はその範囲の 1 つ。", "",
             md_table(rows, ["画面", "グループ", "項目", "値", "判定", "パラメータ"]), "",
             "## XML から決まらない項目", "",
             "値を変えても XML が変わらない項目。表の値はベース（Icicle Kit の preset）のままで、元の設定は分からない。", "",
             md_table(und, ["画面", "グループ", "項目", "値（ベースのまま）", "パラメータ"])]
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(a.out)


def cmd_compare(a):
    c1, c2 = mssdc.read_cfg(a.cfg1), mssdc.read_cfg(a.cfg2)
    gen = mssdc.Gen()
    names = sorted(n for n in set(c1) & set(c2) if c1[n] != c2[n]
                   and (a.all or (in_scope(n, c1) or in_scope(n, c2))))
    d1, d2 = determinable(c1, names, gen), determinable(c2, names, gen)
    rows = []
    for n in names:
        if d1[n] == "XML から決まらない" and d2[n] == "XML から決まらない":
            continue
        note = "" if d1[n] == d2[n] == "確定" else f"{d1[n]} / {d2[n]}"
        rows.append((*where(n), show(n, c1[n]), show(n, c2[n]), note, n))
    rows.sort()
    lines = [f"# {os.path.basename(a.cfg1)} と {os.path.basename(a.cfg2)} の違い", "",
             "XML から値が決まらない項目（例：メモリパーティションの Range）は、両方とも決まらない場合は表に出さない。"
             "判定が空欄の行は、両方とも XML から値が確定している。", "",
             md_table(rows, ["画面", "グループ", "項目", os.path.basename(a.cfg1), os.path.basename(a.cfg2),
                             "判定", "パラメータ"])]
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(a.out, len(rows), "項目")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("list")
    p.add_argument("cfg")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(func=cmd_list)
    p = sp.add_parser("compare")
    p.add_argument("cfg1")
    p.add_argument("cfg2")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--all", action="store_true", help="範囲外のパラメータも出す")
    p.set_defaults(func=cmd_compare)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

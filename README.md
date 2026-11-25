# mss-xml-decompile

MSS Configurator が出力した XML（`*_mss_cfg.xml`）から、元の設定（`.cfg`）を逆生成するツール。
結果の `.cfg` は MSS Configurator で開けるので、画面で設定を確認できる。

## 仕組み

- MSS Configurator のバッチ生成（`pfsoc_mss.exe -GENERATE`、1 回 1〜2 秒）で `.cfg` から XML を作り、目的の XML と比べる。
- パラメータを 1 つずつ変えて、目的の XML との不一致が減る値を採用していく。
  - 選択肢・bool のパラメータは全候補を試す。
  - 数値のパラメータは 2 点の生成から線形に推定する。
- 生成した XML と目的の XML が全項目で一致すれば、逆生成した `.cfg` は「同じ XML になる設定」であることが確かめられたことになる。
- 生成結果は `cache/` に保存し、同じ `.cfg` は再生成しない。

## 限界

- 値を変えても XML が変わらない項目（例：使わない周辺の詳細設定）は、元の値が分からない。ベースの値のまま残る。
- ns 単位のタイミングなど、クロック数に丸めてから XML に入る項目は、範囲の中の 1 つの値になる。
- 画面の表示名は、MSS Configurator の画面定義（`PFSOC_*.xml` の `prompt`）から取っている。メモリパーティションの表示名は手で対応付けた。

## 使い方

Libero SoC 2025.2 の MSS Configurator を使う（場所は環境変数 `LIBERO_DIR` で変えられる）。

```
python mssdc.py decompile <XML> -o <出力.cfg>     # 逆生成。<出力.cfg>.residual.txt に残りの不一致
python report.py list <cfg> -o <一覧.md>          # 画面の言葉で一覧（DDR・IO・メモリパーティション・クロック・FIC）
python report.py compare <cfg1> <cfg2> -o <差分.md>  # 2 つの設定の違いを画面の言葉で
python mssdc.py flatdiff <XML1> <XML2>             # XML の項目単位の違い
```

並列数は環境変数 `MSSDC_WORKERS`（既定 14）。

## ライセンス

[MIT](LICENSE)

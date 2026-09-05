# ai-dev-template

AI主導開発の土台を、**どのリポジトリでも最新状態で**使うためのテンプレート。

Claude Code のプラグインと GitHub Actions の reusable workflow で配るので、
**各リポジトリには設定しか置かない**。テンプレート側を直せば全リポジトリに届く。

## 何が入っているか

「AIに任せる仕組み」と「**AIを止める仕組み**」をセットで持っているのが主旨。
片方だけ作ると、止められないものができる。

| 配るもの | 中身 | 追従 |
|---|---|---|
| プラグイン `ai-dev` | `reviewer` / `fixer` / `plan-reviewer`、`/plan` `/pr`、聖域ガード・保存時lintのフック | `/plugin update` |
| Reusable workflow | `ai-review.yml`（reviewer→fixer ループ）/ `guard.yml`（テスト弱体化検知）/ `docs-lint.yml` | `@main` 参照で自動 |
| `scripts/` | `docs_lint.py` / `check_test_weakening.sh`（workflowから実行。コピー不要） | 同上 |

## 自動レビューのループ

```text
PR が更新された
   |
   v
gate: このPRにAIレビューを回すか決める
   |
   +-- ドキュメントのみ / needs-human ラベルが付いている
   |     `-> スキップ（コストを払わない）
   |
   +-- ブランチが feature/plan-*
   |     `-> plan-reviewer が計画の抜けを指摘
   |         （非ゲート。CIは落とさない）
   |
   `-- 通常のPR
         |
         v
      reviewer が差分をレビューし、
      Critical / Major / Minor に分類して PR にコメント
         |
         v
      VERDICT は？
         |
         +-- PASS ......... CI緑。人間の Approve 待ち
         |
         +-- 抽出できない .. fail-closed でCIを落とす
         |
         `-- FAIL
              |
              +-- 聖域への指摘 / [ai-fix] が上限に到達
              |    `-> needs-human を付け自動修正を止める
              |
              `-- それ以外
                   `-> fixer が最小修正して [ai-fix] を push
                   `-> 先頭に戻り、再レビューされる
```

**指摘を人間がコピペで転記しない。** `fixer` が直接PRへpushするところまで自動になる。
人間に残るのは「要件を書く」「質問に答える」「Approveする」の3つ。

## AIを止める仕組み

| 止めるもの | 止め方 |
|---|---|
| 聖域（プロジェクトが指定した領域）の改変 | `fixer` は修正せず `needs-human` へ。ローカルでもフックが確認を挟む |
| テストの弱体化（アサーション削除・`skip`追加・期待値の実測合わせ） | `check_test_weakening.sh` が機械検知してBLOCK |
| 修正の無限ループ | `[ai-fix]` コミットが上限に達したら打ち切り、`concurrency` で古いランを破棄 |
| レビュー結果の取りこぼし | `VERDICT` を抽出できなければ **fail-closed でCIを落とす** |
| 聖域ガードの空振り | 聖域パスが実在しなければ `docs_lint` がエラーで落ちる |

最後の1つが要点で、**「設定し忘れてガードが効いていないことに気づかない」が一番危ない**。
それを機械的に潰してある。

## 使い方

[SETUP.md](SETUP.md) を参照。要点だけ:

```
1. /plugin marketplace add kosei-k/ai-dev-template
   /plugin install ai-dev
2. .claude/project.toml を書く（固有設定。唯一の必須ファイル）
3. .github/workflows/ に数行のワークフローを3本置く
4. CLAUDE.md を書く（ここだけは毎回ゼロから）
```

## 設計の前提

- **判断基準はテンプレートに持たせない。** 「何が最悪の欠陥か」はプロジェクトごとに違う。
  `reviewer` は自分の感覚ではなく、リポジトリ側の `.claude/04_quality/` と
  `CLAUDE.md` を読んで判定する
- **機械検査できる規約はチェックリストではなくlintに落とす。** レビュー観点に書くと
  人間もAIも見落とす
- **検証コマンドは1本にする。** 人間・`fixer`・フック・CIがすべて同じコマンドを叩くので、
  「どのコマンドで確かめるか」でAIが間違える余地が消える
- **止める仕組みを先に作る。** 落ちるテストが無い状態で自動修正エージェントを入れると、
  `fixer` は自分の修正が正しいか検証できない

## 由来

[credit-canary](https://github.com/kosei-k/credit-canary)（金融ストレス監視システム）で
実運用していた基盤から、ドメイン固有の部分を除いて切り出したもの。

# 導入手順

新しいリポジトリでAI主導開発の土台を使えるようにする。所要15分程度。

## 前提

次の3つが揃っていないと、AIレビューは動かない。**3つとも別物**なので、
1つでも欠けると起動時か実行時に失敗する。

| # | 必要なもの | 場所 | 欠けたときの症状 |
|---|---|---|---|
| 1 | **Claude Code の GitHub App** | https://github.com/apps/claude から**対象リポジトリに**インストール | `Claude Code is not installed on this repository` で失敗 |
| 2 | **`CLAUDE_CODE_OAUTH_TOKEN`** | リポジトリの Settings → Secrets and variables → Actions | 認証エラー |
| 3 | **呼び出し側の `permissions` 宣言** | 各ワークフローファイル（手順3を参照） | `startup_failure`。ジョブが起動すらしない |

1と2は別物である。**1はリポジトリへのアクセス許可、2は認証情報**で、両方要る。

## 1. プラグインを入れる

Claude Code で:

```
/plugin marketplace add kosei-k/ai-dev-template
/plugin install ai-dev
```

これで次が使えるようになる。**リポジトリにファイルは増えない。**

| 種類 | 中身 |
|---|---|
| エージェント | `reviewer` / `fixer` / `plan-reviewer` |
| コマンド | `/plan` / `/pr` |
| フック | 聖域ガード（`PreToolUse`）・保存時lint（`PostToolUse`） |

更新はテンプレート側を直して `/plugin update`。全リポジトリに同じものが届く。

## 2. 固有設定を書く

`project.toml.example` を `.claude/project.toml` としてコピーし、自分のリポジトリに合わせる。

```bash
curl -o .claude/project.toml \
  https://raw.githubusercontent.com/kosei-k/ai-dev-template/main/project.toml.example
```

**最低限、次の2つは必ず設定する。**

- `[project] check_command` — 人間・AI・CIが共通で叩く検証コマンド
- `[[sanctuary.rule]]` — AIが単独で変更してはいけない領域

**`[[sanctuary.rule]]` の `path` が実在しないと、docs_lint がエラーで落ちる。**
「設定し忘れてガードが空振りしているのに気づかない」ことを防ぐための仕様。
聖域が無いプロジェクトなら、`[[sanctuary.rule]]` ごと書かなければよい。

## 3. ワークフローを3ファイル置く

いずれも中身は数行で、ロジックはテンプレート側にある。

`.github/workflows/ai-review.yml`:

```yaml
name: AI Review
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review, unlabeled]
concurrency:
  group: ai-review-${{ github.event.pull_request.number }}
  cancel-in-progress: true
jobs:
  ai-review:
    # 呼び出し側で権限を明示する。**これが無いと起動に失敗する**
    # （reusable workflow は呼び出し側の権限を超える権限を要求できないため）
    permissions:
      contents: write        # fixer が [ai-fix] コミットを push する
      pull-requests: write   # レビュー結果をPRにコメントする
      issues: write          # needs-human ラベルを付ける
      id-token: write
    uses: kosei-k/ai-dev-template/.github/workflows/ai-review.yml@main
    with:
      check_command: mise run check
      sanctuary_paths: 'config/config\.toml|src/rules\.py'
    secrets:
      claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
```

`sanctuary_paths` は `.claude/project.toml` の聖域と同じものを正規表現で書く
（GitHub Actions からはTOMLを読めないため、ここだけ二重に書く必要がある）。

`.github/workflows/guard.yml`:

```yaml
name: Guard
on:
  pull_request:
    types: [opened, synchronize, reopened]
jobs:
  guard:
    permissions:
      contents: read
      issues: write          # ESCALATE時に needs-human ラベルを付ける
      pull-requests: write
    uses: kosei-k/ai-dev-template/.github/workflows/guard.yml@main
    with:
      tests_glob: 'tests/*.py'
      impl_glob: 'src/*.py'
```

> **重要**: 呼び出し側の `permissions:` は省略できない。省略するとリポジトリ既定
> （多くの場合 read のみ）が適用され、**呼び出される側が要求する write 権限を
> 満たせずワークフローが起動失敗する**（`startup_failure`）。
> 単独のワークフローなら `permissions:` で昇格できるが、reusable workflow は
> **呼び出し側の権限を上限とする**ため、呼び出し側で明示する必要がある。

`.github/workflows/docs-lint.yml`（受け入れケース台帳を使う場合）:

```yaml
name: Docs Lint
on: [pull_request]
jobs:
  docs-lint:
    uses: kosei-k/ai-dev-template/.github/workflows/docs-lint.yml@main
```

## 4. ローカルでも同じ検査を走らせる

CIとローカルで違うコマンドを叩くと、AIが「どちらで確かめるか」で間違える。
タスクランナーに1本だけ入口を作り、そこから呼ぶ。

```toml
# mise.toml
[tasks.docs-lint]
run = "python3 <(curl -sL https://raw.githubusercontent.com/kosei-k/ai-dev-template/main/scripts/docs_lint.py)"

[tasks.check]
depends = ["lint", "test", "docs-lint"]
```

ネットワークに依存させたくない場合は、`scripts/docs_lint.py` をvendorしてもよい
（その場合はテンプレート側の更新が自動では届かなくなる）。

## 5. `CLAUDE.md` を書く

**ここだけは毎回ゼロから書く。** プロジェクトの正典であり、流用するものではない。

エージェントが読むので、最低限これらを書いておく。

- このプロジェクトで**何が最悪の欠陥か**（`reviewer` の Critical の基準になる）
- アーキテクチャと、ロジックの置き場所のルール
- **AIを止める境界** — 何をAIに変更させないか、なぜか
- 落とし穴（実際に踏んだもの）

## 6. 判断基準のドキュメントを置く

`reviewer` は自分の感覚で品質を判断せず、これらを読む。
`docs/` にある雛形をコピーして、プロジェクトに合わせて書き換える。

| コピー元 | コピー先 | 中身 |
|---|---|---|
| `docs/04_quality/01_review_checklist.md` | `.claude/04_quality/01_review_checklist.md` | 項目IDを振ったレビュー観点。**機械検査済みの項目には印を付ける**（CIが見るものをAIに指摘させない） |
| `docs/04_quality/02_severity.md` | `.claude/04_quality/02_severity.md` | Critical / Major / Minor の定義と**このプロジェクトでの具体例** |
| `docs/00_project/02_development_process.md` | `.claude/00_project/02_development_process.md` | Issue→Plan PR→実装PR の流れとトリガー表 |
| `docs/00_project/03_plan_template.md` | `.claude/00_project/03_plan_template.md` | 計画テンプレート。`plan-reviewer` が抜けを検出する基準になる |
| `docs/05_acceptance/00_policy.md` | `.claude/05_acceptance/00_policy.md` | 受け入れケースのID体系と、台帳への追加タイミング |

まとめて取得する場合:

```bash
mkdir -p .claude/{00_project,04_quality,05_acceptance,06_adr,07_plans}
git clone --depth 1 https://github.com/kosei-k/ai-dev-template /tmp/ai-dev-template
cp -r /tmp/ai-dev-template/docs/00_project/*   .claude/00_project/
cp -r /tmp/ai-dev-template/docs/04_quality/*   .claude/04_quality/
cp -r /tmp/ai-dev-template/docs/05_acceptance/* .claude/05_acceptance/
```

**コピーしたら「これは雛形です」の行を消し、自分のプロジェクトの内容に書き換えること。**

## 7. 動作確認

**わざと欠陥を含むPRを1本作って、止まることを確認する。** 止める仕組みが動くことを
確認しないまま自動修正ループを本番のPRに向けるのは危険。

- `reviewer` が Critical/Major を出し、`fixer` が直してPRにpushするか
- 聖域に該当する指摘のとき、`fixer` が起動せず `needs-human` が付くか
- テストに `skip` を足したPRで `guard` が BLOCK するか
- 聖域パスを実在しないものに書き換えたとき、`docs_lint` が落ちるか

## 導入後のディレクトリ

```
your-repo/
  .claude/
    project.toml              ← 固有設定（唯一の必須ファイル）
    04_quality/               ← 判断基準（reviewer が読む）
    05_acceptance/            ← 受け入れケース台帳（任意）
    00_project/               ← プロセス文書（任意）
  .github/workflows/
    ai-review.yml             ← 数行
    guard.yml                 ← 数行
    docs-lint.yml             ← 数行
  CLAUDE.md                   ← 毎回ゼロから書く
```

エージェント本体・フック・スクリプトは**リポジトリに存在しない**。
プラグインと reusable workflow から供給される。

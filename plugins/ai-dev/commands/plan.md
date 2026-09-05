---
description: Issueから実装計画を立て、原則コード0行のPlan PRを作成する（承認はPRのマージで行う）
argument-hint: "<Issue番号>"
allowed-tools: Bash(gh issue view:*), Bash(gh issue comment:*), Bash(git *), Bash(gh pr create:*), Bash(gh pr view:*), Bash(mise run *), Bash(npm run *), Bash(make *), Read, Grep, Glob, Write, Edit
---

Issue #$ARGUMENTS から実装計画を立て、Plan PR を作成してください。
**このコマンドでは原則コードを1行も書きません。**

## 1. このリポジトリのルールを読む

- `.claude/project.toml` — `[plan] template` が計画テンプレートの場所
- `CLAUDE.md` — 最重要原則と「AIを止める境界」
- プロセス文書があれば、どの変更種別で Plan PR / ADR が必要かのトリガー表

Plan PR が不要な種別（多くの場合バグ修正・リファクタ）なら、その旨を報告して止まる。

## 2. Issueを読む

`gh issue view $ARGUMENTS` で本文・ラベルを確認する。

## 3. 既存コードの調査

変更対象の周辺と、関連する設計ドキュメントを読む。**既存の設計と矛盾しないか**を
この段階で確認する。

## 4. 不明点の確認

AskUserQuestion で最大3問にまとめて確認する。優先すべき観点:

- 判断の根拠（なぜその値・その方式なのか）が明確か
- **異常系の挙動**（失敗したとき・データが無いとき・全部落ちたとき）
- 後戻りが高くつく決定が含まれていないか

## 5. 計画の作成

計画テンプレートの形式で作成する。**異常系を実装前に文章で確定させること**が主眼。
「うまくいったとき」しか書かれていない計画は不完全。

- 配置先: 計画ディレクトリに `NN_<slug>.md`（連番は既存の最大値+1、2桁ゼロ埋め）
- 冒頭ヘッダ: `Status: planned` / `Issue: #$ARGUMENTS` / `PR: -`
- 後戻りが高くつく決定・複数案の比較を含む場合は ADR も作成（`Status: Proposed`）

## 6. 受け入れケースの列挙

**台帳ファイルには追加しない。** `docs_lint` はテスト未追加のIDを即座にエラーにするため、
Plan PRの時点では計画書内に列挙するだけに留める。台帳への追加は対応するテストと
同じ実装PRで行う。

## 7. 検証

`.claude/project.toml` の `[project] check_command`（またはdocs-lint単体）を実行する。

## 8. ブランチ作成とコミット

- `main` から `feature/plan-<slug>` ブランチを作成
  （この接頭辞で `plan-reviewer` が起動する）
- メッセージ形式: `docs: <日本語の要約>(Plan PR)`

## 9. プッシュとPR作成

- `git push -u origin feature/plan-<slug>`
- `gh pr create`。PR本文冒頭に `Refs #$ARGUMENTS`（`Closes` ではない）

## 10. 報告

Plan PR の URL を報告し、`plan-reviewer` が非ゲートで動くこと、
マージ後に `/pr` で実装PRに進めることを伝える。

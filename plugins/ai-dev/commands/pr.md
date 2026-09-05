---
description: 現在の作業ツリーの変更を実装PRとしてまとめる。DoDを確認してからpushする。
argument-hint: "[Issue番号]"
allowed-tools: Bash(git *), Bash(gh pr create:*), Bash(gh pr view:*), Bash(mise run *), Bash(npm run *), Bash(make *), Read, Grep, Glob
---

現在の作業ツリーの変更を実装PRとして作成してください。

## 1. 差分の確認

`git status` と `git diff` で変更内容を確認する。対応する計画があれば
`Status: in_progress` になっているか確認する。

## 2. DoD確認

`.claude/project.toml` を読み、次を確認する。

- `[project] check_command` が通るか
- 受け入れケース台帳に行が追加され、**対応するテストにIDコメントが入っているか**
  （台帳とテストは同じPRで揃える。片方だけだと `docs_lint` が落ちる）
- 計画の「実装PRで更新する」項目が更新されているか
- ドキュメントとコードが乖離していないか

通らない項目があれば**先に直す**。

## 3. コミット

意味のある単位でコミットする。**`[[sanctuary.rule]]` に該当する変更を含む場合は、
その変更に根拠があるか（ADR・PRの説明に書かれているか）を確認し、
無ければ人間に確認してから進める。**

## 4. プッシュとPR作成

- `git push -u origin <ブランチ名>`
- `gh pr create`。Issue番号が渡されていれば PR本文冒頭に `Closes #<番号>`
- PR本文には**何を変えたか**より**なぜそうしたか**と**どう検証したか**を書く

## 5. 報告

PR URL を報告し、`reviewer`→`fixer` のループと `guard` が自動で走ることを伝える。

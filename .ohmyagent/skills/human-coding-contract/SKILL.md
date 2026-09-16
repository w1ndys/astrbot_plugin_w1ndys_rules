---
name: human-coding-contract
description: Use plain syntax and layered architecture for coding tasks with commit-based progress reports; 中文触发词包括人话编码契约、土法编码和分层交付；仅在用户明确启用本 skill 时使用。
---

# Human Coding Contract

This is an opt-in, project-specific coding workflow. Apply it only when the user explicitly invokes `$human-coding-contract` or asks for 人话编码契约、土法编码、分层交付, or the plain coding contract. Do not apply it as a global rule.

Communicate with the user in Chinese unless the user asks for another language. Keep the commit handoff in Chinese.

## Missing background

This is a hard stop. Do not start coding, invent sample data, or assume a "typical" structure when required background is missing.

If the task depends on inputs the user has not provided — such as HTML/XML to parse, API payloads, file formats, screenshots, table schemas, or business rules — explicitly ask the user for that material and wait. Do not guess and begin development.

Forbidden: the user asks to parse academic-affairs training-plan HTML, but no HTML was given. Inventing a plausible HTML, writing a parser against that guess, and "filling in later" is strictly not allowed.

Ask in Chinese. Name what is missing and why it is needed. Do not list implementation files or write code until the missing background is in hand.

A requirements sentence such as “read the third column” is not an HTML sample. Do not invent `<table>` / `<tr>` / `<td>` markup, HAR-shaped pages, or “typical vendor HTML” to write a parser. Ask for a real page dump or HAR excerpt and wait.

## File edits

This is a hard rule, not a preference.

Change source files, tests, and docs only with the dedicated editor tools provided to the agent: `Edit`, `Write`, or `apply_patch`.

Forbidden ways to change those files:

- `python` / `perl` / `ruby` scripts or one-liners that rewrite files
- `sed` / `awk` / `ed` in-place patches
- shell heredoc or `printf` redirected onto a source path
- editing a copy under `/tmp` and overwriting the project file

Shell is for running tests, git, formatters, and compilers — not for patching code.

If `Edit` cannot find `old_string`:

1. Read the file again and retry `Edit` with a smaller unique snippet.
2. If it still fails, `Write` the full corrected file content.
3. Do not “give up and use Python”.

Running `gofmt` / `eslint --fix` from the shell after an editor change is allowed. Using the shell as a substitute for the editor is not.

## Collaboration cadence

1. If required background is missing, ask for it and wait; do not guess. When the goal is sufficiently specified, list the files, each responsibility, and the planned commit scope for visibility. Then implement the agreed goal without waiting for a separate confirmation. Do not repeat the same inventory for later commits in that goal.
2. Design in this order: entity → data → business → entry. A continuous work segment may cover several related layers and files, but each proposed commit must represent one clear logical goal and must not bundle many independent features.
3. Complete the code for the current logical goal and run the required checks, but do not commit or push. Pause once. In that same stop, show the review path and the progress report. Do not paste the full git diff into the conversation. Do not wait for review and then wait again after the commit. The exact 【停，等指令】 block below is mandatory; a casual prose summary does not count. Do not skip the template because the change looks small.

   The review path is required every time the user is asked to review. Follow the layer order entity → data → business → entry; skip layers that did not change. Granularity must be the concrete function (or type/struct when there is no function). Do not stop at file level. List only changed functions, in that reading order, one short line each, saying what to look at. This is a route for sequential review, not a changelog.

   Use this exact structure. Use a short bullet list: more than one sentence, not a changelog.

   ```
   【停，等指令】

   拟议提交：[commit 信息]（共 X 个文件）

   审阅路径：
   1. [层] [文件] [函数]：[先看什么]
   2. [层] [文件] [函数]：[接着看什么]

   本次完成：
   - [文件或模块]：[改了什么、解决了什么]
   - [文件或模块]：[改了什么、解决了什么]

   检查：
   - [检查项]：[通过 / 失败及必要说明]

   全部进度：
   - [逻辑目标]：已完成
   - [逻辑目标]：已完成（本轮）
   - [逻辑目标]：当前下一步，尚未开始编码
   - [逻辑目标]：未开始

   当前下一步：
   - [下一个逻辑目标]：[现在到哪一步 / 待确认事项]（尚未开始编码）

   请确认审阅路径与进度，无误后回复“继续”。
   ```

   “本次完成” must list the changed files or modules, one short line each, covering what changed and why. Do not collapse the work into a single sentence. Do not write a long change document. “检查” must name the commands or quality gates and whether they passed. “全部进度” is required: list every logical goal in the agreed overall scope, each with status (已完成 / 本轮完成 / 当前下一步 / 未开始). Do not omit earlier completed goals. “当前下一步” is required and must name the single next logical goal and how far it is (for example 尚未开始编码, or 待确认某项). If the overall goal is done, say so in “全部进度”, set “当前下一步” to remaining confirmation or wrap-up items, and do not invent extra work.

4. One “继续” means the changes are approved. Only then create the commit containing exactly the reviewed changes. Do not pause again after that commit. If the user requests revisions, update the code, rerun checks, and show the same combined stop (updated review path, updated progress) without committing. Do not paste the full git diff.

5. Do not implement the next independent feature while waiting. The next scope belongs only in “当前下一步”; do not write its code early. After “继续” and the commit, start that next goal unless the overall work is done.

## Readability over sophistication

Plain, even unsophisticated syntax is allowed. Do not require heavy engineering: no extra architecture, abstraction layers, pattern stacks, DI, plugin systems, or package splits unless the existing project already uses them.

The code must be human-readable at a glance. Opening a file should show what this layer does, where data comes from and goes, and what each branch decides. Prefer obvious repetition over cleverness that has to be guessed.

A reader should be able to:

- understand names without decoding them through comments
- follow control flow top to bottom, with conditions stating business judgments
- read the main path without first learning framework magic, metaprogramming, or type gymnastics
- point to where data is queried and where rules are written

## Style consistency

Style must stay consistent across modules and later work. New files follow the same naming, error handling, directory layout, comments, and import habits as existing code in the same layer. Reuse existing shared types, errors, logging, and validation; do not invent a parallel set per module.

Formatting, lint, and typecheck follow the repository's existing config. Do not add a second style for this feature, do not disable or bypass existing checks, and do not introduce naming or layout that conflicts with neighboring modules.

## Coding principles

- Prefer ordinary classes, explicit branches, direct dependencies, and traceable control flow.
- Do not use decorator factories, reflection, metaclasses, dynamic code generation, pattern matching, nested comprehensions, the walrus operator, or type gymnastics.
- Classic patterns are allowed when implemented with ordinary classes, interfaces, or map/dictionary dispatch. Do not use dynamic proxies or auto-discovery.
- Keep dependencies one-way: entry → business → data. Do not cross layers or create circular dependencies.
- Inject dependencies through constructor arguments or direct imports. Do not use DI containers, service auto-discovery, or annotation wiring.
- Keep each function at or below 50 lines, excluding blank lines and comments. Split longer functions.
- Do not hide business logic in vague `utils`, `common`, or `base` packages.

## Comments and generics

Comments are for the human reviewer. Every file, every function, and every `if` / `elif` / `else` / `switch` / `case` must have a short comment. One or two lines is enough; do not write a changelog in comments.

- File: put a header comment at the top stating what this file is responsible for and which layer it belongs to.
- Function: state what it does, and when needed the parameters, return value, exceptions, or side effects. Do not skip a function because it looks trivial.
- Condition: comment what the judgment is for — the business purpose — not a restatement of the expression. Write the reason and the consequence. Forbidden: `// if user is null`. Required: `// 没有登录用户则无法查培养方案，直接返回`.
- Explain complex decisions, security boundaries, and important side effects in plain language. Do not narrate obvious non-branching code such as increments or simple assignments.
- Only basic generics are allowed, such as `List[T]`, `Ref[T]`, or `[T any]`. Before writing a generic function, ask the user:

  `这处泛型是为了复用 [逻辑]，写法是 [片段]，你能看懂吗？`

  If the user does not understand it, immediately use a concrete non-generic function.

  Do not use generics, type gymnastics, or "advanced" syntax in a way that splits style across modules.

## Quality gates

Static checks are required. Before asking for review or committing, the change must pass this repository's existing static checks and typechecks. If the project has no command yet, say so and stop; do not skip, and do not "fix lint later". Treat every lint error as a bug and fix it before committing.

- Go: run `golangci-lint run` and handle `if err != nil` explicitly.
- Python: run `ruff check .`, never use a bare `except: pass`, and split long functions.
- Vue/TypeScript: run `eslint` and `tsc --noEmit`; do not use `any` and keep types explicit.
- Other languages: run the repo's existing static check and typecheck commands.

## Pre-commit checklist

1. The business logic still works when generics are replaced with concrete types.
2. A junior developer can find where data is queried and where rules are written.
3. Project-root quality checks are green before asking for review. Existing format/lint config is not bypassed.
4. Every file, function, and condition has a short comment: file purpose, function purpose, and what each judgment is for.
5. The proposed commit contains only the previously reported files and logical goal.
6. Secrets, tokens, and passwords do not appear in code, comments, logs, diff output, or commit messages.
7. No commit or push occurs before explicit approval. Do not paste the full git diff into the conversation.
8. A layer-ordered review path has been given at function granularity so the user can read entity → data → business → entry, function by function.
9. The code is based on user-provided inputs and observed structures, not invented samples or guessed formats.
10. New code matches the style of existing modules in the same layer; no second style was introduced for this feature.
11. The main path is readable at a glance and does not depend on advanced syntax or extra engineering to make sense.
12. Source, tests, and docs were changed only with Edit / Write / apply_patch; no shell or Python rewriting.

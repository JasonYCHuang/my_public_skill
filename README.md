# My Public Skills

個人維護的 Claude Code skills 集合，供自己與同事使用。

## 使用方式

把想用的 skill 資料夾複製到 `~/.claude/skills/` 底下即可：

```bash
cp -r skills/<skill-name> ~/.claude/skills/
```

或是 clone 整個 repo 後建立 symlink：

```bash
git clone <this-repo-url>
ln -s "$(pwd)/51_skill_my_public/skills/<skill-name>" ~/.claude/skills/<skill-name>
```

## 目錄結構

```
skills/
  <skill-name>/
    SKILL.md      # 必要，skill 的說明與觸發時機
    ...           # 其他輔助檔案（scripts、references 等，視需要）
```

## 新增 skill

1. 在 `skills/` 底下建立新資料夾，資料夾名稱即為 skill 名稱（kebab-case）。
2. 建立 `SKILL.md`，包含 frontmatter（`name`、`description`）與使用說明。
3. 視需要加入輔助檔案。

@echo off
echo ========== 开始清理 Git 历史 ==========

echo 1. 创建孤儿分支...
git checkout --orphan clean-branch

echo 2. 添加所有文件...
git add -A

echo 3. 提交代码...
git commit -m "Initial commit"

echo 4. 删除旧的 main 分支...
git branch -D main

echo 5. 重命名为 main...
git branch -m main

echo 6. 强制推送到远程...
git push origin main --force

echo 7. 清理本地引用...
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo 8. 验证结果...
git log --oneline --all

echo ========== 清理完成 ==========
pause
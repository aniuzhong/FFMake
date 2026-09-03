# legacy/20260903-ci-mingw-gcc

归档分支（2026-09-03 冻结）。保存两套已停用的构建资产：

1. **GitHub 托管构建管线**：`.github/workflows/{build,release,docker}.yml`
   + `docker/Dockerfile`（多阶段 CI 镜像）。因托管 runner 成本/时长归档；
   恢复方式：把上述文件搬回 master，跑一次 docker.yml 发布 ghcr 镜像即可。
   冷构建基线：双腿各约 3 小时（8 核级 runner）。
2. **MinGW GCC 三元组（mingw-x86_64）**：已冻结的 gcc 路线（gcc 9.3/binutils
   2.34 天花板），被 mingw-x86_64-llvm 取代。triplets.py、deps.json
   overrides 与 lock.json 闭包段在此分支完整保留。

主分支（master）只维护 Kylin V10 本地构建（linux-x86_64 原生 +
mingw-x86_64-llvm 交叉）。

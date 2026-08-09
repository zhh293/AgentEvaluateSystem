# 已废弃：Dockerfile 独立部署协议

Dockerfile-first 和用户 `agent-eval.yaml` 协议已由 [Agent 项目提交与评估协议 v2](AGENT_PROJECT_PROTOCOL.md) 取代。

新提交必须分别上传源码包、Docker Compose、Runtime Config 和 Interface Spec。单服务与多服务统一由 Compose 声明。如果 Compose 服务使用本地 `build`，Dockerfile 仍应放在源码包中，但它只是服务镜像的构建细节，不是独立提交或运行协议。

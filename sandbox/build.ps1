$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
docker build -t agenteval/sandbox:readonly -f "$root/Dockerfile.readonly" $root
docker build -t agenteval/sandbox:writable -f "$root/Dockerfile.writable" $root
docker build -t agenteval/sandbox:highrisk -f "$root/Dockerfile.highrisk" $root
docker build -t agenteval/http-invoker:latest -f "$root/Dockerfile.http-invoker" $root
docker build -t agenteval/egress-proxy:latest -f "$root/Dockerfile.egress-proxy" $root

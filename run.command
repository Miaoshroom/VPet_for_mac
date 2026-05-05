#!/bin/zsh

set -e

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "未检测到 uv。"
  echo
  echo "请先在终端执行下面的命令安装 uv："
  echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo
  echo "安装完成后，重启终端或重新双击 run.command。"
  echo
  read "unused?按回车键退出..."
  exit 1
fi

mkdir -p "$HOME/Library/Logs"
nohup uv run --python 3.12 --with-requirements requirements.txt python main.py \
  > "$HOME/Library/Logs/VPet_for_mac.log" 2>&1 &

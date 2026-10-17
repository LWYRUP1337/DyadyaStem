#!/bin/bash
export MSYS_NO_PATHCONV=1

echo "Инициализация Garage S3..."
NODE_ID=$(docker compose exec garage //garage status | grep -oE '[a-f0-9]{64}' | head -n 1)

if [ -n "$NODE_ID" ]; then
  docker compose exec garage //garage layout assign "$NODE_ID" -z zone1 -c 10G
  docker compose exec garage //garage layout apply --version 1
  docker compose exec garage //garage key import GK2ade727f030bfc7d6a156c42 d603fb8e91da1aee1509a10e04e7e9ecbc71e1d2f45a0162a1ebcbcb3ad06fe9 --name dyadya_key
  docker compose exec garage //garage bucket create dyadyastem
  docker compose exec garage //garage bucket allow dyadyastem --key dyadya_key --read --write
  echo "Garage S3 готов!"
fi



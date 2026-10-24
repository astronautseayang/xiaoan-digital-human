#!/usr/bin/env bash
source /home/yyy/digital-human/deploy-env.sh
mkdir -p /home/yyy/.config/systemd/user
ln -sf "$BASE/services/human-face.service" /home/yyy/.config/systemd/user/human-face.service
systemctl --user daemon-reload
systemctl --user start human-face

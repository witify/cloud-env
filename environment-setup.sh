#!/bin/bash
# Paste this in the cloud environment dialog, under Setup script. To force a new snapshot, change this number: 1
CLOUD_ENV_VERSION=v1.6.0
rm -rf /opt/cloud-env
git clone --quiet --depth 1 --branch "$CLOUD_ENV_VERSION" https://github.com/witify/cloud-env /opt/cloud-env || exit 1
bash /opt/cloud-env/setup.sh
exit 0

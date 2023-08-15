# syntax=docker/dockerfile:1.4

#
# meta arguments
#

# build 0: specification of base version
ARG NDT_BUILDER_VERSION=1.18

# build 1: set app in builder
ARG APP_NAME=netrics
ARG ORG_NAME=internet-equity

# build 1: specification of builder version
ARG BUILDER_VERSION=latest

#
# build 0: build ndt7 client
#
FROM golang:${NDT_BUILDER_VERSION} AS ndt7-build

ARG NDT_CLIENT_VERSION=0.8.0

RUN <<PKG-CONF
#!/bin/bash
set -euo pipefail

# ensure apt caching configuration for (future) PKG-INSTALL stanza(s)
rm -f /etc/apt/apt.conf.d/docker-clean

cat << KEEP-CACHE > /etc/apt/apt.conf.d/keep-cache
Binary::apt::APT::Keep-Downloaded-Packages "true";
KEEP-CACHE
PKG-CONF

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked <<PKG-INSTALL
#!/bin/bash
export DEBIAN_FRONTEND=noninteractive

set -euo pipefail

apt update

apt upgrade --yes
PKG-INSTALL

RUN <<NDT7-BUILD
#!/bin/bash
set -euo pipefail

curl --silent --location https://github.com/m-lab/ndt7-client-go/archive/v${NDT_CLIENT_VERSION}.tar.gz | tar -zxf -

cd ndt7-client-go-${NDT_CLIENT_VERSION}

env GO111MODULE=on go install ./cmd/ndt7-client
NDT7-BUILD

#
# build 1: netrics
#

FROM ghcr.io/internet-equity/fate-builder:${BUILDER_VERSION}

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked <<PKG-INSTALL
#!/usr/bin/bash
export DEBIAN_FRONTEND=noninteractive

set -euo pipefail

#
# cache of /var/lib/apt -- though populated in *this* build by builder's ONBUILD instructions --
# may not function correctly and we must assume that it *may* be empty.
#
# as such, we'll use this cache -- hoping that, when it's used, it'll speed up operations, at
# the same time as it keeps these files *out* of the image itself -- but we'll *ensure* that
# the directory is populated (by "update") *here*
#
apt update

# (the speedtest-cli script runs "update" ... but not *consistently* prior to some of its
# "install" commands)
curl --silent https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | bash

apt install --yes --no-install-recommends \
  bind9-dnsutils \
  iputils-ping \
  net-tools \
  nmap \
  scamper \
  speedtest \
  traceroute
PKG-INSTALL

COPY --from=ndt7-build /go/bin/ndt7-client /usr/local/bin/

CMD ["netrics.d", "--foreground"]

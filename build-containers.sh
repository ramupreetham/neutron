#!/bin/bash
# Copyright 2019 Kaloom, Inc.  All rights reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# Usage:  build-containers.sh 


RPM_VERSION=$(ls build/networking_kaloom/dist/ | grep noarch | cut -d'-' -f2)
NEUTRON_KALOOM_VERSION=$(echo ${RPM_VERSION} | cut -d. -f1,2)
NEUTRON_KALOOM_RELEASE=$(echo ${RPM_VERSION} | cut -d. -f3)

cp build/networking_kaloom/dist/networking_kaloom-*.noarch.rpm docker/openstack-neutron-server-kaloom/
echo "RPM version $RPM_VERSION to be installed on rhos container"

echo "Building local container rhosp13/openstack-neutron-server-kaloom-plugin:${NEUTRON_KALOOM_VERSION}.${NEUTRON_KALOOM_RELEASE}"
docker build --no-cache=true docker/openstack-neutron-server-kaloom/ \
    --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
    --build-arg VCS_REF=$(git rev-parse HEAD) \
    --build-arg KALOOM_VERSION=${NEUTRON_KALOOM_VERSION} \
    --build-arg KALOOM_RELEASE=${NEUTRON_KALOOM_RELEASE} \
    --build-arg RPM_USER=${RPM_REPO_USER} \
    --build-arg RPM_TOKEN=${RPM_REPO_TOKEN} \
    --build-arg RPM_URL=$(curl -u ${RPM_REPO_USER}:${RPM_REPO_TOKEN} --silent "https://api.github.com/repos/kaloom/neutron/releases" | grep -Po '"url": "\K.*?(?=")' | grep assets | tail -1) \
    -t rhosp13/openstack-neutron-server-kaloom-plugin:${RPM_VERSION}

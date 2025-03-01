#!/bin/bash
# Copyright 2018 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

NAME="python-google-compute-engine"
VERSION="20190729.00"

working_dir=${PWD}
if [[ $(basename "$working_dir") != $NAME ]]; then
  echo "Packaging scripts must be run from top of package dir."
  exit 1
fi

# Build dependencies.
sudo apt-get -y install python-all python-setuptools python3-all \
  python3-setuptools python-pytest python3-pytest python-mock python-boto

# DEB creation tools.
sudo apt-get -y install debhelper devscripts build-essential

rm -rf /tmp/debpackage
mkdir /tmp/debpackage
tar czvf /tmp/debpackage/${NAME}_${VERSION}.orig.tar.gz  --exclude .git \
  --exclude packaging --transform "s/^\./${NAME}-${VERSION}/" .

pushd /tmp/debpackage
tar xzvf ${NAME}_${VERSION}.orig.tar.gz

cd ${NAME}-${VERSION}

cp -r ${working_dir}/packaging/debian ./

debuild -us -uc

#!/usr/bin/python
# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Retrieve and store user provided metadata scripts."""

import functools
import re
import socket
import tempfile
import time

from google_compute_engine import metadata_watcher
from google_compute_engine.compat import httpclient
from google_compute_engine.compat import urlerror
from google_compute_engine.compat import urlrequest
from google_compute_engine.compat import urlretrieve


def _RetryOnUnavailable(func):
  """Function decorator template to retry on a service unavailable exception."""

  @functools.wraps(func)
  def Wrapper(*args, **kwargs):
    final_exception = None
    for _ in range(3):
      try:
        response = func(*args, **kwargs)
      except (httpclient.HTTPException, socket.error, urlerror.URLError) as e:
        final_exception = e
        time.sleep(5)
        continue
      else:
        return response
    raise final_exception
  return Wrapper


@_RetryOnUnavailable
def _UrlOpenWithRetry(request):
  """Call urlopen with retry."""
  return urlrequest.urlopen(request)


@_RetryOnUnavailable
def _UrlRetrieveWithRetry(url, dest):
  """Call urlretrieve with retry."""
  return urlretrieve.urlretrieve(url, dest)


class ScriptRetriever(object):
  """A class for retrieving and storing user provided metadata scripts."""
  token_metadata_key = 'instance/service-accounts/default/token'
  # Cached authentication token to be used when downloading from bucket.
  token = None

  def __init__(self, logger, script_type):
    """Constructor.

    Args:
      logger: logger object, used to write to SysLog and serial port.
      script_type: string, the metadata script type to run.
    """
    self.logger = logger
    self.script_type = script_type
    self.watcher = metadata_watcher.MetadataWatcher(logger=self.logger)

  def _DownloadAuthUrl(self, url, dest_dir):
    """Download a Google Storage URL using an authentication token.

    If the token cannot be fetched, fallback to unauthenticated download.

    Args:
      url: string, the URL to download.
      dest_dir: string, the path to a directory for storing metadata scripts.

    Returns:
      string, the path to the file storing the metadata script.
    """
    dest_file = tempfile.NamedTemporaryFile(dir=dest_dir, delete=False)
    dest_file.close()
    dest = dest_file.name

    self.logger.info(
        'Downloading url from %s to %s using authentication token.', url, dest)

    if not self.token:
      response = self.watcher.GetMetadata(
          self.token_metadata_key, recursive=False, retry=False)

      if not response:
        self.logger.info(
            'Authentication token not found. Attempting unauthenticated '
            'download.')
        return self._DownloadUrl(url, dest_dir)

      self.token = '%s %s' % (
          response.get('token_type', ''), response.get('access_token', ''))

    try:
      request = urlrequest.Request(url)
      request.add_unredirected_header('Metadata-Flavor', 'Google')
      request.add_unredirected_header('Authorization', self.token)
      content = _UrlOpenWithRetry(request).read().decode('utf-8')
    except Exception as e:
      self.logger.warning('Could not download %s. %s.', url, str(e))
      return None

    with open(dest, 'w') as f:
      f.write(content)

    return dest

  def _DownloadUrl(self, url, dest_dir):
    """Download a script from a given URL.

    Args:
      url: string, the URL to download.
      dest_dir: string, the path to a directory for storing metadata scripts.

    Returns:
      string, the path to the file storing the metadata script.
    """
    dest_file = tempfile.NamedTemporaryFile(dir=dest_dir, delete=False)
    dest_file.close()
    dest = dest_file.name

    self.logger.info('Downloading url from %s to %s.', url, dest)
    try:
      _UrlRetrieveWithRetry(url, dest)
      return dest
    except (httpclient.HTTPException, socket.error, urlerror.URLError) as e:
      self.logger.warning('Could not download %s. %s.', url, str(e))
    except Exception as e:
      self.logger.warning('Exception downloading %s. %s.', url, str(e))
    return None

  def _DownloadScript(self, url, dest_dir):
    """Download the contents of the URL to the destination.

    Args:
      url: string, the URL to download.
      dest_dir: string, the path to a directory for storing metadata scripts.

    Returns:
      string, the path to the file storing the metadata script.
    """
    # Check for the preferred Google Storage URL format:
    # gs://<bucket>/<object>
    if url.startswith(r'gs://'):
      # Convert the string into a standard URL.
      url = re.sub('^gs://', 'https://storage.googleapis.com/', url)
      return self._DownloadAuthUrl(url, dest_dir)

    header = r'http[s]?://'
    domain = r'storage\.googleapis\.com'

    # Many of the Google Storage URLs are supported below.
    # It is prefered that customers specify their object using
    # its gs://<bucket>/<object> url.
    bucket = r'(?P<bucket>[a-z0-9][-_.a-z0-9]*[a-z0-9])'

    # Accept any non-empty string that doesn't contain a wildcard character
    obj = r'(?P<obj>[^\*\?]+)'

    # Check for the Google Storage URLs:
    # http://<bucket>.storage.googleapis.com/<object>
    # https://<bucket>.storage.googleapis.com/<object>
    gs_regex = re.compile(r'\A%s%s\.%s/%s\Z' % (header, bucket, domain, obj))
    match = gs_regex.match(url)
    if match:
      return self._DownloadAuthUrl(url, dest_dir)

    # Check for the other possible Google Storage URLs:
    # http://storage.googleapis.com/<bucket>/<object>
    # https://storage.googleapis.com/<bucket>/<object>
    #
    # The following are deprecated but checked:
    # http://commondatastorage.googleapis.com/<bucket>/<object>
    # https://commondatastorage.googleapis.com/<bucket>/<object>
    gs_regex = re.compile(
        r'\A%s(commondata)?%s/%s/%s\Z' % (header, domain, bucket, obj))
    match = gs_regex.match(url)
    if match:
      return self._DownloadAuthUrl(url, dest_dir)

    # Unauthenticated download of the object.
    return self._DownloadUrl(url, dest_dir)

  def _GetAttributeScripts(self, attribute_data, dest_dir):
    """Retrieve the scripts from attribute metadata.

    Args:
      attribute_data: dict, the contents of the attributes metadata.
      dest_dir: string, the path to a directory for storing metadata scripts.

    Returns:
      dict, a dictionary mapping metadata keys to files storing scripts.
    """
    script_dict = {}
    attribute_data = attribute_data or {}
    metadata_key = '%s-script' % self.script_type
    metadata_value = attribute_data.get(metadata_key)
    if metadata_value:
      self.logger.info('Found %s in metadata.', metadata_key)
      with tempfile.NamedTemporaryFile(
          mode='w', dir=dest_dir, delete=False) as dest:
        dest.write(metadata_value.lstrip())
        script_dict[metadata_key] = dest.name

    metadata_key = '%s-script-url' % self.script_type
    metadata_value = attribute_data.get(metadata_key)
    if metadata_value:
      self.logger.info('Found %s in metadata.', metadata_key)
      downloaded_dest = self._DownloadScript(metadata_value, dest_dir)
      if downloaded_dest is None:
        self.logger.warning('Failed to download metadata script.')
      script_dict[metadata_key] = downloaded_dest

    return script_dict

  def GetScripts(self, dest_dir):
    """Retrieve the scripts to execute.

    Args:
      dest_dir: string, the path to a directory for storing metadata scripts.

    Returns:
      dict, a dictionary mapping set metadata keys with associated scripts.
    """
    metadata_dict = self.watcher.GetMetadata() or {}

    try:
      instance_data = metadata_dict['instance']['attributes']
    except KeyError:
      instance_data = None
      self.logger.warning('Instance attributes were not found.')

    try:
      project_data = metadata_dict['project']['attributes']
    except KeyError:
      project_data = None
      self.logger.warning('Project attributes were not found.')

    return (self._GetAttributeScripts(instance_data, dest_dir)
            or self._GetAttributeScripts(project_data, dest_dir))

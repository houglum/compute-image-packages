#!/usr/bin/python
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

"""Utilities that are distro specific for use on SUSE 12."""

import os
import subprocess

from google_compute_engine import constants
from google_compute_engine.distro_lib import helpers
from google_compute_engine.distro_lib import ip_forwarding_utils
from google_compute_engine.distro_lib import utils


class Utils(utils.Utils):
  """Utilities used by Linux guest services on SUSE 12."""

  network_path = constants.LOCALBASE + '/etc/sysconfig/network'

  def EnableIpv6(self, interfaces, logger, dhclient_script=None):
    """Configure the network interfaces for IPv6 using dhclient.

    Args:
      interface: string, the output device names for enabling IPv6.
      logger: logger object, used to write to SysLog and serial port.
      dhclient_script: string, the path to a dhclient script used by dhclient.
    """
    pass

  def EnableNetworkInterfaces(self, interfaces, logger, dhclient_script=None):
    """Enable the list of network interfaces.

    Args:
      interfaces: list of string, the output device names to enable.
      logger: logger object, used to write to SysLog and serial port.
      dhclient_script: string, the path to a dhclient script used by dhclient.
    """
    interfaces_to_up = [i for i in interfaces if i != 'eth0']
    if interfaces_to_up:
      logger.info('Enabling the Ethernet interfaces %s.', interfaces_to_up)
      self._WriteIfcfg(interfaces_to_up, logger)
      self._Ifup(interfaces_to_up, logger)

  def _WriteIfcfg(self, interfaces, logger):
    """Write ifcfg files for multi-NIC support.

    Overwrites the files. This allows us to update ifcfg-* in the future.
    Disable the network setup to override this behavior and customize the
    configurations.

    Args:
      interfaces: list of string, the output device names to enable.
      logger: logger object, used to write to SysLog and serial port.
    """
    for interface in interfaces:
      interface_config = os.path.join(
          self.network_path, 'ifcfg-%s' % interface)
      interface_content = [
          '# Added by Google.',
          'STARTMODE=hotplug',
          'BOOTPROTO=dhcp',
          'DHCLIENT_SET_DEFAULT_ROUTE=yes',
          'DHCLIENT_ROUTE_PRIORITY=10%s00' % interface,
          '',
      ]
      with open(interface_config, 'w') as interface_file:
        interface_file.write('\n'.join(interface_content))
      logger.info('Created ifcfg file for interface %s.', interface)

  def _Ifup(self, interfaces, logger):
    """Activate network interfaces.

    Args:
      interfaces: list of string, the output device names to enable.
      logger: logger object, used to write to SysLog and serial port.
    """
    ifup = ['/usr/sbin/wicked', 'ifup', '--timeout', '1']
    try:
      subprocess.check_call(ifup + interfaces)
    except subprocess.CalledProcessError:
      logger.warning('Could not activate interfaces %s.', interfaces)

  def HandleClockSync(self, logger):
    """Sync the software clock with the hypervisor clock.

    Args:
      logger: logger object, used to write to SysLog and serial port.
    """
    helpers.CallHwclock(logger)

  def IpForwardingUtils(self, logger, proto_id=None):
    """Get system IP address configuration utilities.

    Args:
      logger: logger object, used to write to SysLog and serial port.
      proto_id: string, the routing protocol identifier for Google IP changes.
    """
    return ip_forwarding_utils.IpForwardingUtilsIproute(logger, proto_id)

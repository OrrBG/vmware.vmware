# -*- coding: utf-8 -*-

# Copyright: (c) 2023, Ansible Cloud Team (@ansible-collections)
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
#

# Note: This utility is considered private, and can only be referenced from inside the vmware.vmware collection.
#       It may be made public at a later date

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import traceback

try:
    import requests
    REQUESTS_IMP_ERR = None
except ImportError:
    REQUESTS_IMP_ERR = traceback.format_exc()

try:
    from vmware.vapi.vsphere.client import create_vsphere_client
    from com.vmware.vapi.std_client import DynamicID
    VSPHERE_IMP_ERR = None
except ImportError:
    VSPHERE_IMP_ERR = traceback.format_exc()

try:
    from requests.packages import urllib3
    HAS_URLLIB3 = True
except ImportError:
    try:
        import urllib3
        HAS_URLLIB3 = True
    except ImportError:
        HAS_URLLIB3 = False

from ansible.module_utils._text import to_native
from ansible_collections.vmware.vmware.plugins.module_utils.clients._errors import (
    ApiAccessError,
    MissingLibError
)


class VmwareRestClient():
    def __init__(self, connection_params):
        self.check_requirements()
        self.api_client = self.connect_to_api(connection_params)

        self.library_service = self.api_client.content.Library
        self.library_item_service = self.api_client.content.library.Item

        self.tag_service = self.api_client.tagging.Tag
        self.tag_association_service = self.api_client.tagging.TagAssociation
        self.tag_category_service = self.api_client.tagging.Category

    def check_requirements(self):
        """
        Check all requirements for this client are satisfied
        """
        if REQUESTS_IMP_ERR:
            raise MissingLibError('requests', REQUESTS_IMP_ERR)
        if VSPHERE_IMP_ERR:
            raise MissingLibError(
                'vSphere Automation SDK', VSPHERE_IMP_ERR,
                url='https://code.vmware.com/web/sdk/7.0/vsphere-automation-python'
            )

    def connect_to_api(self, connection_params):
        """
        Connect to the vCenter/ESXi client using the REST SDK. This creates a service instance
        which can then be used programmatically to make calls to vCenter or ESXi
        Args:
            connection_params: dict, A dictionary with different authentication or connection parameters like
                               username, password, hostname, etc. The full list is found in the method below.
        Returns:
            Authenticated REST client instance

        """
        hostname = connection_params.get('hostname')
        username = connection_params.get('username')
        password = connection_params.get('password')
        port = connection_params.get('port', 443)
        validate_certs = connection_params.get('validate_certs')
        http_proxy_host = connection_params.get('http_proxy_host')
        http_proxy_port = connection_params.get('http_proxy_port')
        http_proxy_protocol = connection_params.get('http_proxy_protocol')

        self.__validate_required_connection_params(hostname, username, password)

        session = requests.Session()

        self.__configure_session_ssl_context(session, validate_certs)
        self.__configure_session_proxies(session, http_proxy_host, http_proxy_port, http_proxy_protocol)
        return self.__create_client_connection(session, hostname, username, password, port)

    def __validate_required_connection_params(self, hostname, username, password):
        """
        Validate the user provided the required connection parameters and throw an error
        if they were not found. Usually the module/plugin validation will do this first so
        this is more of a safety/sanity check.
        """
        if not hostname:
            raise ApiAccessError((
                "Hostname parameter is missing. Please specify this parameter in task or "
                "export environment variable like 'export VMWARE_HOST=ESXI_HOSTNAME'"
            ))

        if not username:
            raise ApiAccessError((
                "Username parameter is missing. Please specify this parameter in task or "
                "export environment variable like 'export VMWARE_USER=ESXI_USERNAME'"
            ))

        if not password:
            raise ApiAccessError((
                "Password parameter is missing. Please specify this parameter in task or "
                "export environment variable like 'export VMWARE_PASSWORD=ESXI_PASSWORD'"
            ))

    def __configure_session_ssl_context(self, session, validate_certs):
        session.verify = validate_certs

        if not validate_certs:
            if HAS_URLLIB3:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def __configure_session_proxies(self, session, http_proxy_host, http_proxy_port, http_proxy_protocol):
        if all([http_proxy_host, http_proxy_port, http_proxy_protocol]):
            http_proxies = {
                http_proxy_protocol: (
                    "{%s}://{%s}:{%s}" %
                    http_proxy_protocol, http_proxy_host, http_proxy_port
                )
            }

            session.proxies.update(http_proxies)

    def __create_client_connection(self, session, hostname, username, password, port):
        msg = "Failed to connect to vCenter or ESXi API at %s:%s" % (hostname, port)
        try:
            client = create_vsphere_client(
                server="%s:%s" % (hostname, port),
                username=username,
                password=password,
                session=session
            )
        except requests.exceptions.SSLError as e:
            msg += " due to SSL verification failure"
            raise ApiAccessError("%s : %s" % (msg, to_native(e)))
        except Exception as e:
            raise ApiAccessError("%s : %s" % (msg, to_native(e)))

        if client is None:
            raise ApiAccessError("Failed to login to %s" % hostname)

        return client

    def get_tags_by_vm_moid(self, vm_moid):
        """
        Get a list of tag objects attached to a virtual machine
        Args:
            vm_moid: the VM MOID to use to gather tags

        Returns:
            List of tag objects associated with the given virtual machine
        """
        dobj = DynamicID(type='VirtualMachine', id=vm_moid)
        return self.get_tags_for_dynamic_id_obj(dobj=dobj)

    def get_tags_by_host_moid(self, host_moid):
        """
        Get a list of tag objects attached to an ESXi host
        Args:
            host_moid: the Host MOID to use to gather tags

        Returns:
            List of tag objects associated with the given host
        """
        dobj = DynamicID(type='HostSystem', id=host_moid)
        return self.get_tags_for_dynamic_id_obj(dobj=dobj)

    def get_tags_for_dynamic_id_obj(self, dobj):
        """
        Return tag objects associated with a DynamicID object.
        Args:
            dobj: Dynamic object
        Returns:
            List of tag objects associated with the given object
        """
        tags = []
        if not dobj:
            return tags

        tag_ids = self.tag_association_service.list_attached_tags(dobj)
        for tag_id in tag_ids:
            tags.append(self.tag_service.get(tag_id))

        return tags

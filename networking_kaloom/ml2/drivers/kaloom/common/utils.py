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

from neutron_lib.plugins import directory
from neutron_lib import context as nctx
from networking_kaloom.ml2.drivers.kaloom.db import kaloom_db
from oslo_db import exception as db_exc
from eventlet import greenthread
from oslo_log import log
from xml.sax.saxutils import escape
import netaddr

LOG = log.getLogger(__name__)

def xmlescape(data):
    #escapes &, <, > by default and also ', " as dict provided.
    return escape(data, entities={
        "'": "&apos;",
        "\"": "&quot;"
    })

def _get_network_name(network_id):
    ctx = nctx.get_admin_context()
    return directory.get_plugin().get_network(ctx, network_id)['name'] 

def _kaloom_nw_name(prefix, network_id):
    """Generate an kaloom specific name for this network.

    Use a unique name so that OpenStack created networks
    can be distinguishged from the user created networks
    on Kaloom vFabric. This serves for node_id of nw.
    """
    return prefix + network_id

def _kaloom_gui_nw_name(prefix, network_id, name):
    """Generate an kaloom specific name for this network.

    Use a unique name so that OpenStack created networks
    can be distinguishged from the user created networks
    on Kaloom vFabric. xml control characters such as:
    ", <, >, &, ' are escaped to result valid xml request later.
    """
    return prefix + network_id + '.' + xmlescape(name)

def _kaloom_router_name(prefix, router_id, name):
    """Generate an kaloom specific name for this router.

    Use a unique name so that OpenStack created routers
    can be distinguishged from the user created routers
    on Kaloom vFabric. Replace spaces with underscores for CLI compatibility
    """
    return prefix + router_id + '.' + name.replace(' ', '_')


def tp_operation_lock(host, network_id):
    """ concurrent attachments, detachments, attachments/detachments, detachments/attachments 
    of neutron ports on same (host, network_id) pair conflicts with vfabric TP attach/detach.
    Concurrent attachments of multiple neutron ports on the same host/network should result in single
    TP attachment. While concurrent detachments of multiple neutron ports of the same host/network occuring,
    last neutron port delete should result in the TP detach. On concurrent attachments and detachments of multiple
    neutron ports on the same host/network, TP attachment should remain until there is single neutron port remained.

    This is applied simply by using lock mechanism on tp_operation per host/network_id. Any attach and detach neutron port
    requires to acquire the lock.
    """
    tries = 1 
    iterations = 10
    retry_interval = 0.5
    while tries <= iterations:
           try:
               kaloom_db.create_tp_operation(host, network_id)
               LOG.debug('tp_operation_lock acquired for host=%s, network_id=%s on tries %s', host, network_id, tries)
               return True
           except db_exc.DBDuplicateEntry as e:
               tries += 1
               greenthread.sleep(retry_interval)
    LOG.warning('tp_operation_lock is not acquired for host=%s, network_id=%s on tries %s', host, network_id, tries-1)
    return False


def tp_operation_unlock(host, network_id):
    kaloom_db.delete_tp_operation(host, network_id)
    LOG.debug('tp_operation_unlock for host=%s, network_id=%s', host, network_id)

def get_overlapped_subnet(given_ip_cidr, existing_ip_cidrs):
    given_net = netaddr.IPNetwork(given_ip_cidr)
    overlapped_ip_cidrs=[]
    for ip_cidr in existing_ip_cidrs:
        existing_net = netaddr.IPNetwork(ip_cidr)
        if given_net in existing_net or existing_net in given_net:
            overlapped_ip_cidrs.append(ip_cidr)
    return overlapped_ip_cidrs

#command pattern for reversible operations
# receiver
class vfabric_operation_reversible:
    def __init__(self, vfabric, do_operation, undo_operation):
        self.vfabric = vfabric
        self.do_operation = do_operation
        self.undo_operation = undo_operation

    def execute(self, *args, **kwargs):
        method = getattr(self.vfabric, self.do_operation)
        return method(*args, **kwargs)

    def undo(self, *args, **kwargs):
        method = getattr(self.vfabric, self.undo_operation)
        return method(*args, **kwargs)

# command
class Command:
    def __init__(self, receiver, *args, **kwargs):
        self.receiver = receiver
        self.args = args
        self.kwargs = kwargs
    def execute(self):
        return self.receiver.execute(*self.args, **self.kwargs)
    def undo(self):
        return self.receiver.undo(*self.args, **self.kwargs)

# invoker
class Invoker:
    def __init__(self):
        self.history = []
    def execute(self, command):
        resp = command.execute()
        self.history.append(command)
        return resp
    def undo(self):
        while len(self.history) > 0:
           command = self.history.pop()
           try:
              command.undo()
           except:
              pass

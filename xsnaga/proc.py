# Copyright 2013 Johan Rydberg.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Functionality for managing processes."""

import datetime
import random
import shortuuid
from xsnaga.model import Proc


class RandomPlacementPolicy(object):
    """Random placement policy."""

    def __init__(self, log, store):
        self.log = log
        self.store = store

    def allocate(self, app, name):
        """Allocate a hypervisor for process C{name} of C{app}."""
        # Here we should do this neat thingy to distribute stuff
        # evenly, and to amke sure that the same process do not run on
        # the same hypervisor.  But for now we only alloc on a random
        # hypervisor.
        hypervisors = list(self.store.items)
        if not hypervisors:
            raise ValueError()
        hypervisor = random.choice(hypervisors)
        return hypervisor


class ProcFactory(object):
    """Process factory - spawn and stop procs."""

    def __init__(self, log, clock, proc_store, policy, hypervisor_service,
                 callback_url):
        self.log = log
        self.clock = clock
        self.proc_store = proc_store
        self.policy = policy
        self.hypervisor_service = hypervisor_service
        self.callback_url = callback_url

    def spawn_proc(self, app, deploy, name, command):
        hypervisor = self.policy.allocate(app, name)
        proc = self.proc_store.create(app, name, deploy,
                                      shortuuid.uuid(),
                                      hypervisor)
        try:
            controller = self.hypervisor_service.get(hypervisor.host)
            controller.spawn_proc(proc, app, self.callback_url(proc),
                                  deploy.image, command, deploy.config)
        except Exception:
            self.proc_store.set_state(proc, u'abort')
            raise

    def stop_proc(self, proc):
        """Stop (but not remove) the given process."""
        # fixme: check state ...
        self.proc_store.set_state(proc, u'stop')
        try:
            controller = self.hypervisor_service.get(hypervisor.id)
            controller.stop_proc(proc)
        except Exception:
            self.log.error(
                "failed to remove proc %s from hypervisor" % (proc,))
            self.proc_store.set_state(proc, u'abort')

    def kill_proc(self, proc):
        """Remove the proc completely."""
        self.proc_store.remove(proc)

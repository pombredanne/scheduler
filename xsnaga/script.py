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

import logging
import os

from storm.locals import Store, create_database
from gevent import pywsgi, pool
from glock.clock import Clock
from xsnaga.store import ProcStore, AppStore, DeployStore, HypervisorStore
from xsnaga.hypervisor import HypervisorController, HypervisorClient
from xsnaga.api import (API, AppResource, DeployResource,
                        HypervisorResource, ProcResource)
from xsnaga.handler import (OldDeployHandler, ExpiredProcHandler,
                            ScaleHandler, LostProcHandler)
from xsnaga.health import HealthStore
from xsnaga.proc import ProcFactory, RandomPlacementPolicy
from pyee import EventEmitter


HEALTH_THRESHOLD = 2
HEALTH_CHECK_INTERVAL = 30


def main():
    options = os.environ
    format = '%(levelname)-8s %(name)s: %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=format)
    store = Store(create_database(options['DATABASE']))
    clock = Clock()
    eventbus = EventEmitter()
    proc_store = ProcStore(clock, store)
    app_store = AppStore(store)
    deploy_store = DeployStore(clock, store)
    hypervisor_store = HypervisorStore(store)
    health_store = HealthStore(clock, HEALTH_THRESHOLD)

    def hypervisor_client_factory(model):
        return HypervisorClient(logging.getLogger(
                'hypervisor.client[%s]' % (model.host,)),
                clock, HEALTH_CHECK_INTERVAL, proc_store,
                health_store, model)

    hypervisor_controller = HypervisorController(
        eventbus, hypervisor_store, hypervisor_client_factory)
    hypervisor_controller.start()
    policy = RandomPlacementPolicy(logging.getLogger('placement.random'),
                                   hypervisor_store)
    environ = {'SERVER_NAME': options.get('SERVER_NAME', 'localhost'),
               'SERVER_PORT': str(options['PORT'])}

    api = API(logging.getLogger('api'), environ)
    proc_factory = ProcFactory(logging.getLogger('proc.factory'),
                               clock, eventbus, proc_store, policy,
                               api.callback_url)
    api.add('apps', AppResource(api.log, api.url, app_store))
    api.add('deploys', DeployResource(api.log, api.url, app_store,
                                      deploy_store))
    api.add('hypervisor', HypervisorResource(api.log, api.url, eventbus,
                                             hypervisor_store,
                                             health_store))
    api.add('procs', ProcResource(api.log, api.url, app_store, proc_store,
                                  proc_factory))

    handlers = []
    handlers.append(OldDeployHandler(logging.getLogger('handler.old-deploy'),
                                     clock, 3, proc_store, proc_factory))
    handlers.append(ExpiredProcHandler(logging.getLogger('handler.expired'),
                                       clock, 3, proc_store, proc_factory))
    handlers.append(ScaleHandler(logging.getLogger('handler.scale'),
                                 clock, 5, app_store, proc_store, proc_factory,
                                 pool.Pool(5)))
    handlers.append(LostProcHandler(logging.getLogger('handler.lost'),
                                    clock, 7, proc_store, 120))
    for handler in handlers:
        handler.start()
    logging.info("Start serving requests on %d" % (int(options['PORT'])))
    pywsgi.WSGIServer(('', int(options['PORT'])), api).serve_forever()


if __name__ == '__main__':
    main()

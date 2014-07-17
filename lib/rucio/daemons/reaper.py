# Copyright European Organization for Nuclear Research (CERN)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Vincent Garonne, <vincent.garonne@cern.ch>, 2012-2014
# - Cedric Serfon, <cedric.serfon@cern.ch>, 2013

'''
Reaper is a daemon to manage file deletion.
'''

import logging
import sys
import threading
import time
import traceback

from rucio.core import monitor
from rucio.core import rse as rse_core
from rucio.core.message import add_message
from rucio.core.replica import list_unlocked_replicas, update_replicas_states, delete_replicas
from rucio.core.rse_counter import get_counter
from rucio.db.constants import ReplicaState
from rucio.rse import rsemanager as rsemgr
from rucio.common.config import config_get
from rucio.common.exception import SourceNotFound, ServiceUnavailable
from rucio.common.utils import chunks


logging.getLogger("requests").setLevel(logging.CRITICAL)

logging.basicConfig(stream=sys.stdout,
                    level=getattr(logging, config_get('common', 'loglevel').upper()),
                    format='%(asctime)s\t%(process)d\t%(levelname)s\t%(message)s')

graceful_stop = threading.Event()


def __check_rse_usage(rse, rse_id):
    """
    Internal method to check RSE usage and limits.

    :param rse_id: the rse name.
    :param rse_id: the rse id.

    :returns : max_being_deleted_files, needed_free_space, used, free.
    """
    max_being_deleted_files, needed_free_space, used, free = None, None, None, None

    # Get RSE limits
    limits = rse_core.get_rse_limits(rse=rse, rse_id=rse_id)
    if not limits and 'MinFreeSpace' not in limits and 'MaxBeingDeletedFiles' not in limits:
        return max_being_deleted_files, needed_free_space, used, free

    min_free_space = limits.get('MinFreeSpace')
    max_being_deleted_files = limits.get('MaxBeingDeletedFiles')

    # Get total space available
    usage = rse_core.get_rse_usage(rse=rse, rse_id=rse_id, source='srm')
    if not usage:
        return max_being_deleted_files, needed_free_space, used, free

    for u in usage:
        total = u['total']
        break

    # Get current used space
    cnt = get_counter(rse_id=rse_id)
    if not cnt:
        return max_being_deleted_files, needed_free_space, used, free
    used = cnt['bytes']

    # Get current amount of bytes and files waiting for deletion
    # being_deleted = rse_core.get_sum_count_being_deleted(rse_id=rse_id)

    free = total - used
    needed_free_space = min_free_space - free

    return max_being_deleted_files, needed_free_space, used, free


def reaper(rses, worker_number=1, total_workers=1, chunk_size=100, once=False, greedy=False, scheme=None):
    """
    Main loop to select and delete files.

    :param total_workers: The total number of workers.
    :param chunk_size: the size of chunk for deletion.
    :param once: If True, only runs one iteration of the main loop.
    :param greedy: If True, delete right away replicas with tombstone.
    :param rses: List of RSEs the reaper should work against. If empty, it considers all RSEs.
    :param scheme: Force the reaper to use a particular protocol, e.g., mock.
    """

    logging.info('Starting reaper')
    while not graceful_stop.is_set():
        for rse in rses:
            rse_info = rsemgr.get_rse_info(rse['rse'])
            rse_protocol = rse_core.get_rse_protocols(rse['rse'])

            if not rse_protocol['availability_delete']:
                logging.info('RSE %s is not available for deletion' % (rse_info['rse']))
                continue

            # Temporary hack to force gfal for deletion
            for protocol in rse_info['protocols']:
                if protocol['impl'] == 'rucio.rse.protocols.srm.Default':
                    protocol['impl'] = 'rucio.rse.protocols.gfal.Default'

            logging.info('Running on RSE %s' % (rse_info['rse']))
            try:

                needed_free_space, max_being_deleted_files = None, 10000
                if not greedy:
                    max_being_deleted_files, needed_free_space, used, free = __check_rse_usage(rse=rse['rse'], rse_id=rse['id'])
                    logging.info('Space usage for RSE %(rse)s: max_being_deleted_files, needed_free_space, used, free' % rse, max_being_deleted_files, needed_free_space, used, free)

                s = time.time()
                with monitor.record_timer_block('reaper.list_unlocked_replicas'):
                    replicas = list_unlocked_replicas(rse=rse['rse'], bytes=needed_free_space, limit=max_being_deleted_files)
                logging.debug('list_unlocked_replicas %s %s %s' % (rse['rse'], time.time() - s, len(replicas)))

                if not replicas:
                    logging.info('Reaper %s: nothing to do for %s' % (worker_number, rse['rse']))
                    continue

                p = rsemgr.create_protocol(rse_info, 'delete', scheme=None)
                for files in chunks(replicas, chunk_size):
                    logging.debug('Running on : %s' % str(files))
                    try:
                        s = time.time()
                        update_replicas_states(replicas=[dict(replica.items() + [('state', ReplicaState.BEING_DELETED), ('rse_id', rse['id'])]) for replica in files])

                        for replica in files:
                            replica['pfn'] = str(rsemgr.lfns2pfns(rse_settings=rse_info, lfns=[{'scope': replica['scope'], 'name': replica['name']}, ]).values()[0])
                            add_message('deletion-planned', {'scope': replica['scope'],
                                                             'name': replica['name'],
                                                             'file-size': replica['bytes'],
                                                             'url': replica['pfn'],
                                                             'rse': rse_info['rse']})

                        # logging.debug('update_replicas_states %s' % (time.time() - s))
                        monitor.record_counter(counters='reaper.deletion.being_deleted',  delta=len(files))

                        if not scheme:
                            try:
                                deleted_files = []
                                p.connect()
                                for replica in files:
                                    try:
                                        logging.debug('Deletion of %s on %s' % (replica['pfn'], rse['rse']))
                                        s = time.time()
                                        p.delete(replica['pfn'])
                                        monitor.record_timer('daemons.reaper.delete.%s.%s' % (p.attributes['scheme'], rse['rse']), (time.time()-s)*1000)
                                        duration = time.time() - s

                                        deleted_files.append({'scope': replica['scope'], 'name': replica['name']})

                                        add_message('deletion-done', {'scope': replica['scope'],
                                                                      'name': replica['name'],
                                                                      'rse': rse_info['rse'],
                                                                      'file-size': replica['bytes'],
                                                                      'url': replica['pfn'],
                                                                      'duration': duration})
                                    except SourceNotFound:
                                        err_msg = 'File %s on %s not found (already deleted ?).' % (replica['pfn'], rse['rse'])
                                        logging.warning(err_msg)
                                        add_message('deletion-failed', {'scope': replica['scope'],
                                                                        'name': replica['name'],
                                                                        'rse': rse_info['rse'],
                                                                        'file-size': replica['bytes'],
                                                                        'url': replica['pfn'],
                                                                        'reason': err_msg})
                                    except ServiceUnavailable, e:
                                        logging.error(str(e))
                                        add_message('deletion-failed', {'scope': replica['scope'],
                                                                        'name': replica['name'],
                                                                        'rse': rse_info['rse'],
                                                                        'file-size': replica['bytes'],
                                                                        'url': replica['pfn'],
                                                                        'reason': str(e)})
                                    except:
                                        logging.critical(traceback.format_exc())
                                        # add_message('deletion-failed', {'scope': replica['scope'],
                                        #                              'name': replica['name'],
                                        #                              'rse': rse_info['rse'],
                                        #                              'reason': str(traceback.format_exc())})
                            except ServiceUnavailable, e:
                                logging.error(str(e))
                            finally:
                                p.close()
                        s = time.time()
                        with monitor.record_timer_block('reaper.delete_replicas'):
                            delete_replicas(rse=rse['rse'], files=deleted_files)
                        logging.debug('delete_replicas %s %s %s' % (rse['rse'], len(files), time.time() - s))
                        monitor.record_counter(counters='reaper.deletion.done',  delta=len(files))
                    except:
                        logging.critical(traceback.format_exc())
            except:
                logging.critical(traceback.format_exc())

        if once:
            break
        time.sleep(60)

    logging.info('Graceful stop requested')
    logging.info('Graceful stop done')


def stop(signum=None, frame=None):
    """
    Graceful exit.
    """
    graceful_stop.set()


def run(total_workers=1, chunk_size=100, once=False, greedy=False, rses=[], scheme=None):
    """
    Starts up the reaper threads.

    :param total_workers: The total number of workers.
    :param chunk_size: the size of chunk for deletion.
    :param once: If True, only runs one iteration of the main loop.
    :param greedy: If True, delete right away replicas with tombstone.
    :param rses: List of RSEs the reaper should work against. If empty, it considers all RSEs.
    :param scheme: Force the reaper to use a particular protocol/scheme, e.g., mock.
    """
    print 'main: starting processes'

    if not rses:
        rses = rse_core.list_rses()

    # rses = [rse for rse in rses if rse['rse'] == 'NDGF-T1-RUCIOTEST_DATADISK']

    threads = list()
    nb_rses_per_worker = len(rses) / total_workers
    r = []
    for i in xrange(0, len(rses), nb_rses_per_worker):
        kwargs = {'worker_number': (i * nb_rses_per_worker) + 1,
                  'total_workers': total_workers,
                  'once': once,
                  'chunk_size': chunk_size,
                  'greedy': greedy,
                  'rses': rses[i:i + nb_rses_per_worker],
                  'scheme': scheme}
        r.extend(rses[i:i + nb_rses_per_worker])
        threads.append(threading.Thread(target=reaper, kwargs=kwargs))
    [t.start() for t in threads]
    while threads[0].is_alive():
        [t.join(timeout=3.14) for t in threads]

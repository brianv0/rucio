# Copyright European Organization for Nuclear Research (CERN)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Vincent Garonne, <vincent.garonne@cern.ch>, 2012

from json import dumps, loads
from requests.status_codes import codes

from rucio.client.baseclient import BaseClient
from rucio.common.utils import build_url


class ReplicationRuleClient(BaseClient):

    """ReplicationRuleClient class for working with replication rules"""

    BASEURL = 'rules'

    def __init__(self, rucio_host=None, auth_host=None, account=None, ca_cert=None, auth_type=None, creds=None, timeout=None):
        super(ReplicationRuleClient, self).__init__(rucio_host, auth_host, account, ca_cert, auth_type, creds, timeout)

    def add_replication_rule(self, dids, copies, rse_expression, weight=None, lifetime=None, grouping='dataset', account=None, locked=False):
        """
        :param dids:            The data identifier set.
        :param copies:          The number of replicas.
        :param rse_expression:  Boolean string expression to give the list of RSEs.
        :param weight:          If the weighting option of the replication rule is used, the choice of RSEs takes their weight into account.
        :param lifetime:        The lifetime of the replication rules (remaining time/duration).
        :param grouping:        all -  All files will be replicated to the same RSE.
                                dataset - All files in the same dataset will be replicated to the same RSE;
                                none - Files will be completely spread over all allowed RSEs without any grouping considerations at all.
        :param account:         The account.
        :param locked:          If the rule is locked, it cannot be deleted.

        """
        path = self.BASEURL + '/'
        url = build_url(self.host, path=path)
        data = dumps({'dids': dids, 'copies': copies, 'rse_expression': rse_expression,
                      'weight': weight, 'lifetime': lifetime, 'grouping': grouping,
                      'account': account, 'locked': locked})
        r = self._send_request(url, type='POST', data=data)
        if r.status_code == codes.created:
            return loads(r.text)
        else:
            exc_cls, exc_msg = self._get_exception(r.headers, r.status_code)
            raise exc_cls(exc_msg)

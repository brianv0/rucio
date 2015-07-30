# Copyright European Organization for Nuclear Research (CERN)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Vincent Garonne, <vincent.garonne@cern.ch>, 2015
# - Cedric Serfon, <cedric.serfon@cern.ch>, 2015

"""Index in rule_history on scope, name

Revision ID: 2f648fc909f3
Revises: 269fee20dee9
Create Date: 2015-07-21 13:04:18.896813

"""

# revision identifiers, used by Alembic.
revision = '2f648fc909f3'
down_revision = '269fee20dee9'

from alembic import op


def upgrade():
    op.create_index('RULES_HISTORY_SCOPENAME_IDX', 'rules_history', ['scope', 'name'])


def downgrade():
    op.drop_index('RULES_HISTORY_SCOPENAME_IDX', 'rules_history')
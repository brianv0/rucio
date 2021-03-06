# Copyright European Organization for Nuclear Research (CERN)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Martin Barisits, <martin.barisits@cern.ch>, 2016

"""Added child_rule_id column

Revision ID: 5f139f77382a
Revises: 1d1215494e95
Create Date: 2016-04-11 11:01:10.727941

"""

import sqlalchemy as sa

from alembic import context, op
from rucio.db.sqla.types import GUID


# revision identifiers, used by Alembic.
revision = '5f139f77382a'
down_revision = '1d1215494e95'


def upgrade():
    if context.get_context().dialect.name != 'sqlite':
        op.add_column('rules', sa.Column('child_rule_id', GUID()))
        op.add_column('rules_hist_recent', sa.Column('child_rule_id', GUID()))
        op.add_column('rules_history', sa.Column('child_rule_id', GUID()))
        op.create_foreign_key('RULES_CHILD_RULE_ID_FK', 'rules', 'rules', ['child_rule_id'], ['id'])
        op.create_index('RULES_CHILD_RULE_ID_IDX', 'rules', ['child_rule_id'])


def downgrade():
    if context.get_context().dialect.name != 'sqlite':
        op.drop_constraint('RULES_CHILD_RULE_ID_FK', 'rules')
        op.drop_index('RULES_CHILD_RULE_ID_IDX', 'rules')
        op.drop_column('rules', 'child_rule_id')
        op.drop_column('rules_hist_recent', 'child_rule_id')
        op.drop_column('rules_history', 'child_rule_id')

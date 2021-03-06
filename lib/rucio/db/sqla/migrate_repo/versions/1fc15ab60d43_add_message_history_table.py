# Copyright European Organization for Nuclear Research (CERN)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Mario Lassnig, <mario.lassnig@cern.ch>, 2015

"""add message_history table

Revision ID: 1fc15ab60d43
Revises: 4783c1f49cb4
Create Date: 2015-06-01 14:46:26.248843

"""

from alembic import op
import sqlalchemy as sa

from rucio.db.sqla.types import GUID

# revision identifiers, used by Alembic.
revision = '1fc15ab60d43'
down_revision = '4783c1f49cb4'


def upgrade():
    op.create_table('messages_history',
                    sa.Column('id', GUID()),
                    sa.Column('created_at', sa.DateTime),
                    sa.Column('updated_at', sa.DateTime),
                    sa.Column('event_type', sa.String(1024)),
                    sa.Column('payload', sa.String(4000)))


def downgrade():
    op.drop_table('messages_history')

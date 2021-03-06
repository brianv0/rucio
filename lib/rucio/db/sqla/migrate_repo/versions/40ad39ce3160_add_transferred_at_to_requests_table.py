# Copyright European Organization for Nuclear Research (CERN)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Vincent Garonne, <vincent.garonne@cern.ch>, 2015

"""add_transferred_at_to_requests_table

Revision ID: 40ad39ce3160
Revises: 2ba5229cb54c
Create Date: 2015-04-14 15:56:32.647375

"""

from alembic import op, context
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '40ad39ce3160'
down_revision = '2ba5229cb54c'


def upgrade():
    if context.get_context().dialect.name not in ('sqlite'):
        op.add_column('requests', sa.Column('transferred_at', sa.DateTime()))


def downgrade():
    if context.get_context().dialect.name not in ('sqlite'):
        op.drop_column('requests', 'transferred_at')

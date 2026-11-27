"""Paging for the SQL repositories' lists, with searching for lookup resources."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from sqlalchemy import Connection, Row, TextClause, TString, text, tstring

from app.core.list_options import NameSort, SortOrder
from app.repositories.lists import LookupResourceCriteria, PageCriteria, RecordPage

SQL_NAME_ORDER: Mapping[SortOrder, TextClause] = {
    SortOrder.ASC: text("lower(name), id"),
    SortOrder.DESC: text("lower(name) DESC, id DESC"),
}
# The sorts of every lookup resource that only sorts by name.
SQL_NAME_SORTS: Mapping[NameSort, Mapping[SortOrder, TextClause]] = {
    NameSort.NAME: SQL_NAME_ORDER
}


class SQLLists[Criteria: PageCriteria](ABC):
    """Fetches the pages of a list.

    Subclasses choose the records that match the criteria and the sort keys.
    """

    def __init__(self, connection: Connection) -> None:
        """Set up the lists.

        Args:
            connection: The connection the queries run on.
        """
        self._connection = connection

    def fetch_page(self, records: TString, criteria: Criteria) -> RecordPage[Row[Any]]:
        """Fetch one page of the records that match the criteria.

        Args:
            records: The repository's query for every record the list could
                hold. It must select every column the criteria and the sort
                keys use.
            criteria: Which of the records to fetch.

        Returns:
            The rows on the page, and how many records match in all.
        """
        matching = self._matching(records, criteria)
        count_matching = tstring(t"SELECT count(*) FROM ({matching})")
        total_items: int = self._connection.execute(count_matching).scalar_one()

        offset = (criteria.page - 1) * criteria.page_size

        # Also keeps an offset too large for PostgreSQL out of the query.
        if offset >= total_items:
            return RecordPage([], total_items)

        page_query = tstring(t"""
            SELECT * FROM ({matching})
            ORDER BY {self._order_by(criteria)}
            LIMIT {criteria.page_size} OFFSET {offset}
        """)
        rows = self._connection.execute(page_query).all()

        return RecordPage(rows, total_items)

    @abstractmethod
    def _matching(self, records: TString, criteria: Criteria) -> TString:
        """Build the query for the records that match the criteria.

        Args:
            records: The repository's query, as given to ``fetch_page``.
            criteria: Which of the records to fetch.

        Returns:
            The query, selecting every column of ``records``.
        """

    @abstractmethod
    def _order_by(self, criteria: Criteria) -> TextClause:
        """Choose the sort keys.

        Args:
            criteria: Which of the records to fetch.

        Returns:
            The sort keys, ending with one that is unique.
        """


class SQLLookupResourceLists[Sort: StrEnum](SQLLists[LookupResourceCriteria[Sort]]):
    """Fetches the pages of a lookup resource's list.

    The repository's query must select ``id``, ``name`` and ``archived_at``,
    which is ``NULL`` for records that are never archived, and every column
    the sort keys use.
    """

    def __init__(
        self,
        connection: Connection,
        sorts: Mapping[Sort, Mapping[SortOrder, TextClause]],
    ) -> None:
        """Set up the lists of one resource.

        Args:
            connection: The connection the queries run on.
            sorts: The sort keys for each direction of each of the resource's
                sorts, ending with ``id``.
        """
        super().__init__(connection)
        self._sorts = sorts

    def _matching(
        self, records: TString, criteria: LookupResourceCriteria[Sort]
    ) -> TString:
        return tstring(t"""
            SELECT * FROM ({records})
            WHERE ({criteria.q} = '' OR strpos(lower(name), lower({criteria.q})) > 0)
                AND CASE {criteria.archived}
                    WHEN 'false' THEN archived_at IS NULL
                    WHEN 'true' THEN archived_at IS NOT NULL
                    WHEN 'all' THEN true
                END
        """)

    def _order_by(self, criteria: LookupResourceCriteria[Sort]) -> TextClause:
        return self._sorts[criteria.sort][criteria.order]

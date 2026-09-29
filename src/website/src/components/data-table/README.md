# Data Tables

Use `DataTableToolbar` and `DataTable` for administrative list pages.

- `DataTableToolbar` provides the standard filter-card surface and padding; the consuming page owns vertical spacing and its filters, validation, and query behavior.
- `DataTable` provides the shared table surface, loading/empty states, theme colors, and embeds `DataTablePagination` when pagination is enabled. Column definitions remain in the consuming view.
- Use `DataTablePagination` on list views whose content is not an `el-table` (for example, the system event feed) so the footer remains consistent.
- Keep server pagination in the page: update its current page from `page-change`, then call the existing API. Put any page-size selector in the toolbar and keep its current API contract.
- Use `fill-height` and `height="100%"` only when the list should scroll inside the available page height.
- Use `selection-change` for selection state. Do not add business actions or API requests to the shared component.

Existing routes and response contracts are unchanged by this presentation layer.

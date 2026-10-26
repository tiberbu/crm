"""Partner Portal API module.

Provides endpoints for Partner Portal operations:
- Custom Year 1-5 pricing configuration for facilities
- Year 1-5 pricing search and retrieval
- Deal-won opt-in journey initiation
"""

from crm.partner_portal.deal import deal_won
from crm.partner_portal.pricing import (
	configure_facility_pricing,
	get_facility_pricing,
	set_facility_pricing,
)

__all__ = [
	"configure_facility_pricing",
	"deal_won",
	"get_facility_pricing",
	"set_facility_pricing",
]

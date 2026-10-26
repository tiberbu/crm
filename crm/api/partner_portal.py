"""CRM API partner portal router / re-export.

Enables both /api/method/crm.partner_portal.<func> and
/api/method/crm.api.partner_portal.<func>.
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

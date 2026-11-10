import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt

from crm.utils.value_express import level_key

CODE_RE = re.compile(r"^[A-Z0-9-]{4,32}$")
SIX_DIGITS_RE = re.compile(r"^\d{6}$")
IMMUTABLE_FIELDS = (
	"network",
	"applies_to",
	"value_type",
	"value",
	"max_tokens",
	"fixed_discount_percent",
	"targeting",
	"reward_by_level",
)
PLANS = ("Flex", "Fixed", "Both")


class CRMCoupon(Document):
	def before_save(self):
		# A claim can increment redeemed_count in the same transaction; re-read it under lock so a
		# plain admin save never writes a stale count.
		if not self.is_new():
			self.redeemed_count = cint(
				frappe.db.get_value("CRM Coupon", self.name, "redeemed_count", for_update=True)
			)

	def validate(self):
		self._normalise()
		self._apply_field_rules()
		self._enforce_immutability()
		self._reject_network_overlap()

	def _normalise(self):
		self.coupon_code = cstr(self.coupon_code or "").strip().upper()
		self.network = cstr(self.network or "").strip() or None
		self.targeting = cstr(self.targeting or "").strip() or None
		self.facility_levels = _normalise_facility_levels(self.facility_levels)

	def _apply_field_rules(self):
		self.applies_to = cstr(self.applies_to or "Flex").strip() or "Flex"
		if self.applies_to not in PLANS:
			frappe.throw(_("Applies To must be Flex, Fixed or Both."), frappe.ValidationError)
		by_level = cint(self.reward_by_level)
		if self.applies_to == "Flex":
			self.fixed_discount_percent = 0
		else:
			discount = flt(self.fixed_discount_percent)
			# With level rewards, 0 means "no discount for levels not listed" (P-118).
			if not (by_level and discount == 0) and not _valid_discount(discount):
				frappe.throw(
					_("For a Fixed plan the discount must be greater than 0% and at most 100%."),
					frappe.ValidationError,
				)
		if self.applies_to == "Fixed":
			# A Fixed-only coupon gives no tokens.
			self.value_type = None
			self.value = 0
			self.max_tokens = 0
		else:
			self._apply_token_rules()
		self._apply_level_rules()
		self._apply_common_rules()

	def _apply_level_rules(self):
		"""P-116/P-119: one row per level, each giving a valid benefit for the coupon's plan."""
		if not cint(self.reward_by_level):
			self.reward_by_level = 0
			self.set("level_rewards", [])
			return
		self.reward_by_level = 1
		if not self.get("level_rewards"):
			frappe.throw(
				_("Add at least one facility level, or turn off Reward by Facility Level."),
				frappe.ValidationError,
			)
		uses_flex = self.applies_to != "Fixed"
		uses_fixed = self.applies_to != "Flex"
		seen = set()
		for row in self.level_rewards:
			level = " ".join(cstr(row.facility_level).split())
			key = level_key(level)
			if not key:
				frappe.throw(_("Each level reward needs a facility level."), frappe.ValidationError)
			if key in seen:
				frappe.throw(
					_("{0} is listed more than once. Give each facility level one row.").format(level),
					frappe.ValidationError,
				)
			seen.add(key)
			row.facility_level = level
			if not uses_flex:
				row.flex_value = 0
			if not uses_fixed:
				row.fixed_discount_percent = 0
			flex, discount = flt(row.flex_value), flt(row.fixed_discount_percent)
			if flex and not _valid_token_value(self.value_type, flex):
				frappe.throw(
					_("{0}: {1}").format(level, _token_value_message(self.value_type)), frappe.ValidationError
				)
			if discount and not _valid_discount(discount):
				frappe.throw(
					_("{0}: the Fixed plan discount must be greater than 0% and at most 100%.").format(level),
					frappe.ValidationError,
				)
			if flex <= 0 and discount <= 0:
				frappe.throw(
					_("{0} gives nothing. Set its reward, or remove the row.").format(level),
					frappe.ValidationError,
				)

	def _apply_token_rules(self):
		if self.value_type not in ("flat_tokens", "percentage_of_purchase"):
			frappe.throw(
				_("Value type must be flat tokens or a percentage of the purchase."), frappe.ValidationError
			)

		value = flt(self.value)
		# With level rewards, 0 means "no tokens for levels not listed" (P-118).
		if not (cint(self.reward_by_level) and value == 0) and not _valid_token_value(self.value_type, value):
			frappe.throw(_token_value_message(self.value_type), frappe.ValidationError)

		if self.max_tokens is not None and self.max_tokens:
			if cint(self.max_tokens) < 1 or cint(self.max_tokens) > 1_000_000:
				frappe.throw(
					_("The token cap must be between 1 and 1,000,000, or 0 for no cap."),
					frappe.ValidationError,
				)
		else:
			self.max_tokens = 0

	def _apply_common_rules(self):
		if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
			frappe.throw(_("Valid To must be on or after Valid From."), frappe.ValidationError)

		if cint(self.max_redemptions) < 0:
			frappe.throw(
				_("Max redemptions cannot be negative. Use 0 for unlimited."), frappe.ValidationError
			)
		if cint(self.max_redemptions) < cint(self.redeemed_count):
			frappe.throw(
				_("Max redemptions cannot be set below the {0} already redeemed.").format(
					cint(self.redeemed_count)
				),
				frappe.ValidationError,
			)

		if cint(self.per_facility_limit or 1) != 1:
			frappe.throw(_("The per-facility limit is fixed at 1."), frappe.ValidationError)
		self.per_facility_limit = 1

		# Targeting is for CRM coupons (no network); a network coupon must not carry one.
		if self.network:
			self.targeting = None
			self.facility_levels = None
			self.coupon_code = None
		else:
			if not self.targeting:
				frappe.throw(
					_(
						"A CRM coupon needs a targeting mode (Assigned Facilities, Facility Level or Coupon Code)."
					),
					frappe.ValidationError,
				)
			if self.targeting == "Facility Level" and not cstr(self.facility_levels or "").strip():
				frappe.throw(
					_("Facility Level targeting needs at least one facility level."), frappe.ValidationError
				)
			if self.targeting == "Coupon Code" and not self.coupon_code:
				frappe.throw(_("Coupon Code targeting needs a coupon code."), frappe.ValidationError)
			if self.targeting != "Coupon Code" and self.coupon_code:
				frappe.throw(
					_("A coupon code is only allowed for Coupon Code targeting."), frappe.ValidationError
				)

		if self.coupon_code:
			if SIX_DIGITS_RE.match(self.coupon_code):
				frappe.throw(
					_("A coupon code cannot be six digits; that is reserved for partner IDs."),
					frappe.ValidationError,
				)
			if not CODE_RE.match(self.coupon_code):
				frappe.throw(
					_("The coupon code must be 4 to 32 characters using letters, numbers or dashes."),
					frappe.ValidationError,
				)

	def _has_redemptions(self) -> bool:
		return bool(frappe.db.exists("CRM Coupon Redemption", {"coupon": self.name}))

	def _enforce_immutability(self):
		if self.is_new() or not self._has_redemptions():
			return
		previous = frappe.db.get_value(
			"CRM Coupon",
			self.name,
			list(IMMUTABLE_FIELDS),
			as_dict=True,
		)
		if not previous:
			return
		changed = _level_rows(self.get("level_rewards")) != _level_rows(
			frappe.get_all(
				"CRM Coupon Level Reward",
				filters={"parent": self.name, "parenttype": "CRM Coupon", "parentfield": "level_rewards"},
				fields=["facility_level", "flex_value", "fixed_discount_percent"],
				order_by="idx asc",
			)
		)
		for field in IMMUTABLE_FIELDS:
			current = getattr(self, field)
			if changed or (cstr(current or "") or None) != (cstr(previous.get(field) or "") or None):
				frappe.throw(
					_(
						"This coupon has been used, so its value cannot be changed. To change it, revoke the coupon and create a new one."
					),
					frappe.ValidationError,
				)
				return

	def _reject_network_overlap(self):
		if not self.network or self.status == "Revoked":
			return
		# A revoked coupon does not block; only live (non-Revoked) coupons of the same network do.
		others = frappe.get_all(
			"CRM Coupon",
			filters={"network": self.network, "name": ["!=", self.name], "status": "Active"},
			fields=["valid_from", "valid_to"],
		)
		for other in others:
			if _windows_overlap(self.valid_from, self.valid_to, other.valid_from, other.valid_to):
				frappe.throw(
					_(
						"Another active coupon for this network already covers this window. Revoke or adjust it first."
					),
					frappe.ValidationError,
				)
				return


def _valid_discount(percent) -> bool:
	return 0 < flt(percent) <= 100


def _valid_token_value(value_type, value) -> bool:
	value = flt(value)
	if value_type == "flat_tokens":
		return 1 <= value <= 1_000_000 and int(value) == value
	return 0 < value <= 100


def _token_value_message(value_type):
	if value_type == "flat_tokens":
		return _("For a flat coupon the value must be a whole number of tokens between 1 and 1,000,000.")
	return _("For a percentage coupon the value must be greater than 0 and at most 100.")


def _level_rows(rows) -> list:
	"""Level rows as comparable tuples, ignoring order."""
	return sorted(
		(level_key(row.get("facility_level")), flt(row.get("flex_value")), flt(row.get("fixed_discount_percent")))
		for row in rows or []
	)


def _normalise_facility_levels(value):
	"""One trimmed, non-empty entry per facility level, case-insensitively (mirrors optin_admin)."""
	result = []
	seen = set()
	for line in cstr(value or "").splitlines():
		level = line.strip()
		key = level.casefold()
		if level and key not in seen:
			result.append(level)
			seen.add(key)
	return "\n".join(result)


def _windows_overlap(a_start, a_end, b_start, b_end) -> bool:
	"""Two validity windows overlap unless one clearly ends before the other starts. None = unbounded."""
	if a_end is not None and b_start is not None and a_end < b_start:
		return False
	if b_end is not None and a_start is not None and b_end < a_start:
		return False
	return True
